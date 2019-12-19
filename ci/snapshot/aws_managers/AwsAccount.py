import boto3
import botocore

from image_managers.ImageManager import ImageManager
from aws_managers.ParameterManager import ParameterManager
from aws_managers.PipelineManager import PipelineManager
from aws_managers.TemplatePackageManager import TemplatePackageManager
from aws_managers.CloudformationStack import Stacks
from secretst import Secrets

TEMPLATE_NAME_KEY = "template_name"
PARAMETER_KEYS_KEY = "parameter_keys"
PARAMETER_OVERRIDES_KEY = "parameter_overrides"

SNAPSHOT_ID_OVERRIDE_KEY = "SnapshotID"
BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY = "BuildToolsAccountId"
PROOF_ACCOUNT_ID_TO_ADD_KEY = "ProofAccountIdToAdd"
BUILD_TOOLS_IMAGE_ID_KEY = "build-tools-image-id"

UNEXPECTED_POLICY_MSG = "Someone has changed the bucket policy on the shared build account. " \
                              "There should only be one statement. Bucket policy should only be updated " \
                              "with CloudFormation template. Aborting!"
class AwsAccount:
    """
    This class is meant to represent an AWS account.
    """
    CAPABILITIES = ['CAPABILITY_NAMED_IAM']

    def __init__(self, profile,
                 proof_tools_image_filename=None,
                 build_tools_image_filename=None,
                 project_parameters_image_filename=None,
                 shared_tool_bucket_name=None):
        self.profile = profile
        self.session = boto3.session.Session(profile_name=profile)
        self.account_id = self.session.client('sts').get_caller_identity().get('Account')
        self.stacks = Stacks(self.session)
        self.s3 = self.session.client("s3")
        self.ecr = self.session.client("ecr")
        self.proof_tools_image = ImageManager(filename=proof_tools_image_filename) \
            if proof_tools_image_filename else None
        self.build_tools_image = ImageManager(filename=build_tools_image_filename) \
            if build_tools_image_filename else None
        self.project_parameters_image = ImageManager(filename=project_parameters_image_filename) \
            if project_parameters_image_filename else None
        self.secrets = Secrets(self.session)
        self.pipeline_client = self.session.client("codepipeline")
        # The tools bucket could either be in the target profile, or from another account
        self.shared_tool_bucket_name = shared_tool_bucket_name if shared_tool_bucket_name \
            else self.stacks.get_output('S3BucketName')

        self.parameter_manager = ParameterManager(profile, self.stacks,
                                                  tools_account_image=self.build_tools_image,
                                                  proof_account_image=self.proof_tools_image,
                                                  proof_account_project_parameters=self.project_parameters_image,
                                                  shared_tool_bucket_name=self.shared_tool_bucket_name)
        self.pipeline_manager = PipelineManager(profile)
        self.template_package_manager = TemplatePackageManager(self.profile,
                                                               self.parameter_manager,
                                                               self.shared_tool_bucket_name)



    @staticmethod
    def print_parameters(parameters):
        for param in parameters:
            print("  {:20}: {}".format(param['ParameterKey'], param['ParameterValue']))

    def _create_stack(self, stack_name, parameters, template_body=None, template_url=None):
        if template_body:
            self.stacks.get_client().create_stack(StackName=stack_name,
                                                  TemplateBody=template_body,
                                                  Parameters=parameters,
                                                  Capabilities=AwsAccount.CAPABILITIES)
        elif template_url:
            self.stacks.get_client().create_stack(StackName=stack_name,
                                                  TemplateURL=template_url,
                                                  Parameters=parameters,
                                                  Capabilities=AwsAccount.CAPABILITIES)
    def _update_stack(self, stack_name, parameters, template_body=None, template_url=None):
        if template_body:
            self.stacks.get_client().update_stack(StackName=stack_name,
                                                  TemplateBody=template_body,
                                                  Parameters=parameters,
                                                  Capabilities=AwsAccount.CAPABILITIES)
        elif template_url:
            self.stacks.get_client().update_stack(StackName=stack_name,
                                                  TemplateURL=template_url,
                                                  Parameters=parameters,
                                                  Capabilities=AwsAccount.CAPABILITIES)

    def _create_or_update_stack(self, stack_name, parameters, template_name, template_body=None,
                                template_url=None):
        if not template_body and not template_url:
            raise Exception("Must provide either the body of the template being deployed, "
                            "or a url to download it from S3")

        if self.stacks.get_status(stack_name) is None:
            print("\nCreating stack '{}' with parameters".format(stack_name))
            AwsAccount.print_parameters(parameters)
            print("Using " + template_name)
            self._create_stack(stack_name, parameters, template_body=template_body,
                               template_url=template_url)
        else:
            print("\nUpdating stack '{}' with parameters".format(stack_name))
            AwsAccount.print_parameters(parameters)
            print("Using " + template_name)
            self._update_stack(stack_name, parameters, template_body=template_body,
                               template_url=template_url)




    def deploy_stack(self, stack_name, template_name, parameter_keys,
                     s3_template_source=None, parameter_overrides=None):
        """
        Asynchronously deploy a single stack
        :param stack_name: Name of stack to deploy
        :param template_name: Filename of template
        :param parameter_keys: Parameters that need to be passed to template
        :param s3_template_source: True if we should get this template from S3, default is local
        :param parameter_overrides: User provided values for parameters
        :return:
        """
        template_url = None
        template_body = None
        if s3_template_source:
            template_url = self.template_package_manager\
                .get_s3_url_for_template(template_name, s3_template_source, parameter_overrides)
            print(template_url)

        else:
            template_body = open(template_name).read()
        parameters = self.parameter_manager.make_stack_parameters(parameter_keys, parameter_overrides)
        try:
            self._create_or_update_stack(stack_name, parameters, template_name, template_body=template_body,
                                         template_url=template_url)
        except botocore.exceptions.ClientError as err:
            code = err.response['Error']['Code']
            msg = err.response['Error']['Message']
            if code == 'ValidationError' and msg == 'No updates are to be performed.':
                print("Nothing to update")
            else:
                raise

    def deploy_stacks(self, stacks_to_deploy, s3_template_source=None, overrides=None):
        """
        Deploys several stacks asynchronously, and waits for them all to finish deploying.
        stacks_to_deploy should be a dictionary that maps stack names to
        template filenames, and parameters that must be passed to the template. Here is an example:
        PROOF_ACCOUNT_GITHUB_CLOUDFORMATION_DATA = {
        "github": {
                TEMPLATE_NAME_KEY: "github.yaml",
                PARAMETER_KEYS_KEY: ['S3BucketToolsName',
                                     'BuildToolsAccountId',
                                     'ProjectName',
                                     'SnapshotID',
                                     'GitHubRepository',
                                     'GitHubBranchName']
            }
        }
        This will deploy the github stack. The method will try to find each parameter from the following
        sources (in this order): overrides, snapshot file, project parameter file, output from a stack
        :param stacks_to_deploy: Dictionary as described above
        :param s3_template_source: Boolean, true if we should get template from S3. Default is to fetch local templates
        :param overrides: Any parameter values we would like to provide
        """
        stack_names = stacks_to_deploy.keys()
        if not self.stacks.stable_stacks(stack_names):
            print("Stacks not stable: {}".format(stack_names))
            return
        for key in stacks_to_deploy.keys():
            self.deploy_stack(key, stacks_to_deploy[key][TEMPLATE_NAME_KEY],
                              stacks_to_deploy[key][PARAMETER_KEYS_KEY],
                              s3_template_source=s3_template_source,
                              parameter_overrides=overrides)
        self.stacks.wait_for_stable_stacks(stack_names)


