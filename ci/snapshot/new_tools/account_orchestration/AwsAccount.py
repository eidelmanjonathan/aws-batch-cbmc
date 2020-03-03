import boto3
import botocore

from new_tools.aws_managers.LambdaManager import LambdaManager
from new_tools.aws_managers.CodebuildManager import CodebuildManager
from new_tools.aws_managers.key_constants import PIPELINES_KEY, PARAMETER_KEYS_KEY, TEMPLATE_NAME_KEY
from new_tools.aws_managers.ParameterManager import ParameterManager
from new_tools.aws_managers.PipelineManager import PipelineManager
from new_tools.aws_managers.CloudformationStacks import CloudformationStacks
from new_tools.image_managers.SnapshotManager import SnapshotManager
from new_tools.utilities.utilities import parse_json_file, str2bool, print_parameters
from secretst import Secrets

UNEXPECTED_POLICY_MSG = "Someone has changed the bucket policy on the shared build account. " \
                              "There should only be one statement. Bucket policy should only be updated " \
                              "with CloudFormation template. Aborting!"
VALIDATION_ERROR = 'ValidationError'
NO_UPDATES_MSG = 'No updates are to be performed.'
class AwsAccount:
    """
    This class is responsible for managing a Padstone CI AWS account. It exposes methods to deploy stacks,
    update environment variables and manage account snapshots
    """
    CAPABILITIES = ['CAPABILITY_NAMED_IAM']

    # Add __all__ to list public methods

    def __init__(self, profile,
                 shared_tool_bucket_name=None,
                 snapshot_id=None,
                 parameters_file=None,
                 packages_required=None,
                 snapshot_s3_prefix=None
                 ):
        self.profile = profile
        self.session = boto3.session.Session(profile_name=profile)
        self.account_id = self.session.client('sts').get_caller_identity().get('Account')
        self.stacks = CloudformationStacks(self.session)
        self.s3 = self.session.client("s3")
        self.ecr = self.session.client("ecr")
        self.secrets = Secrets(self.session)
        self.lambda_manager = LambdaManager(self.session)
        self.codebuild = CodebuildManager(self.session)
        self.pipeline_client = self.session.client("codepipeline")
        self.snapshot_s3_prefix = snapshot_s3_prefix

        self.parameters = parse_json_file(parameters_file) if parameters_file else None

        # The tools bucket could either be in the target profile, or from another account
        self.shared_tool_bucket_name = shared_tool_bucket_name if shared_tool_bucket_name \
            else self.stacks.get_output('S3BucketName')
        self.snapshot_manager = SnapshotManager(self.session,
                                                bucket_name=self.shared_tool_bucket_name,
                                                packages_required=packages_required,
                                                tool_image_s3_prefix=snapshot_s3_prefix)
        self.snapshot_id = snapshot_id

        self.snapshot = None
        if self.snapshot_id:
            self.snapshot = self.snapshot_manager.download_snapshot(self.snapshot_id)

        self.parameter_manager = ParameterManager(self.session, self.stacks,
                                                  snapshot_id=self.snapshot_id,
                                                  snapshot=self.snapshot,
                                                  shared_tools_bucket=self.shared_tool_bucket_name,
                                                  project_parameters=self.parameters)
        self.pipeline_manager = PipelineManager(self.session)

    def get_current_snapshot_id(self):
        if self.snapshot_id:
            return self.snapshot_id
        else:
            return self.parameter_manager.get_value("SnapshotID")

    def set_env_var(self, obj, a, b, bool_val):
        if not isinstance(bool_val, bool):
            raise Exception("Trying to set an env variable to illegal value")
        obj.set_env_var(a, b, str(bool_val))
        print(obj.get_env_var(a, b))

    def set_ci_operating(self, is_ci_operating):
        self.set_env_var(self.lambda_manager, 'webhook', 'ci_operational', is_ci_operating)

    def set_update_github(self, github_update):
        self.set_env_var(self.lambda_manager, 'batchstatus', 'ci_updating_status', github_update)
        self.set_env_var(self.codebuild, 'prepare', 'ci_updating_status', github_update)

    def download_and_set_snapshot(self, snapshot_id):
        self.snapshot_id = snapshot_id
        self.snapshot = self.snapshot_manager.download_snapshot(self.snapshot_id)
        self.parameter_manager = ParameterManager(self.session, self.stacks,
                                                  snapshot=self.snapshot,
                                                  snapshot_id=self.snapshot_id,
                                                  project_parameters=self.parameters,
                                                  shared_tools_bucket=self.shared_tool_bucket_name)



    def _create_stack(self, stack_name, parameters, template_body=None, template_url=None):
        if not template_url and not template_body:
            raise Exception("Must provide either template_url or template body")
        if template_url and template_body:
            raise Exception("Cannot provide both template url and template body")
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
        if not template_url and not template_body:
            raise Exception("Must provide either template_url or template body")
        if template_url and template_body:
            raise Exception("Cannot provide both template url and template body")
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
            print_parameters(parameters)
            print("Using " + template_name)
            self._create_stack(stack_name, parameters, template_body=template_body,
                               template_url=template_url)
        else:
            print("\nUpdating stack '{}' with parameters".format(stack_name))
            print_parameters(parameters)
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
        if s3_template_source:
            template_body = None
            template_url = self.get_s3_url_for_template(template_name, parameter_overrides)
            print("Using S3 template at url: {}".format(template_url))

        else:
            template_url = None
            template_body = open(template_name).read()
        print("RIGHT BEFORE: {}".format(self.parameter_manager.snapshot_id))
        parameters = self.parameter_manager.make_stack_parameters(parameter_keys, parameter_overrides)
        try:
            self._create_or_update_stack(stack_name, parameters, template_name, template_body=template_body,
                                         template_url=template_url)
        except botocore.exceptions.ClientError as err:
            code = err.response['Error']['Code']
            msg = err.response['Error']['Message']
            if code == VALIDATION_ERROR and msg == NO_UPDATES_MSG:
                print("Nothing to update")
            else:
                raise

    def get_update_github_status(self):
        return str2bool(self.parameter_manager.get_value("UpdateGithub"))

    def _trigger_pipelines(self, pipelines):
        for pipeline in pipelines:
            self.pipeline_manager.trigger_pipeline_async(pipeline)

    def _wait_for_pipelines(self, pipelines):
        for pipeline in pipelines:
            self.pipeline_manager.wait_for_pipeline_completion(pipeline)

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
            print("Check on status in AWS console, maybe there was a rollback?")
            return
        pipelines = []
        for key in stacks_to_deploy.keys():
            self.deploy_stack(key, stacks_to_deploy[key][TEMPLATE_NAME_KEY],
                              stacks_to_deploy[key][PARAMETER_KEYS_KEY],
                              s3_template_source=s3_template_source,
                              parameter_overrides=overrides)
            if PIPELINES_KEY in stacks_to_deploy[key].keys():
                pipelines.extend(stacks_to_deploy[key][PIPELINES_KEY])
        self.stacks.wait_for_stable_stacks(stack_names)
        self._wait_for_pipelines(pipelines)


    def trigger_and_wait_for_pipelines(self, pipelines):
        self._trigger_pipelines(pipelines)
        self._wait_for_pipelines(pipelines)

    def get_s3_url_for_template(self, template_name, parameter_overrides=None):
        snapshot_id = self.snapshot_id if self.snapshot_id else self.parameter_manager.get_value('SnapshotID', parameter_overrides=parameter_overrides)

        if not snapshot_id:
            raise Exception("Cannot fetch account templates from S3 with no snapshot ID")
        return ("https://s3.amazonaws.com/{}/{}snapshot-{}/{}"
                .format(self.shared_tool_bucket_name, self.snapshot_s3_prefix,
                        snapshot_id,
                        template_name))

