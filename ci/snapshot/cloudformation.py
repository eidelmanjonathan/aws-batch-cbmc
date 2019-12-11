import copy
import json
import time

import boto3
import botocore
import botocore_amazon.monkeypatch

from stackst import Stacks
from project_params import ProjectParams
from snapshott import Snapshot
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
class Cloudformation:
    """
    This class will handle the end to end management of Cloudformation stacks, as well as Cloudformation templates,
    including retrieving and storing templates from/to S3 buckets, checking the status of resources and handling
    snapshot files
    """
    CAPABILITIES = ['CAPABILITY_NAMED_IAM']
    BUILD_TOOLS_IMAGE_S3_SOURCE = "BUILD_TOOLS_IMAGE_S3_SOURCE"
    PROOF_ACCOUNT_IMAGE_S3_SOURCE = "PROOF_ACCOUNT_IMAGE_S3_SOURCE"

    def __init__(self, profile, snapshot_filename=None, project_params_filename=None, shared_tool_bucket_name = None):
        self.profile = profile
        self.session = boto3.session.Session(profile_name=profile)
        self.account_id = self.session.client('sts').get_caller_identity().get('Account')
        self.stacks = Stacks(self.session)
        self.s3 = self.session.client("s3")
        self.ecr = self.session.client("ecr")
        self.snapshot = Snapshot(filename=snapshot_filename) if snapshot_filename else None
        self.snapshot_filename = snapshot_filename
        self.project_params = ProjectParams(filename=project_params_filename) if project_params_filename else None
        self.secrets = Secrets(self.session)
        self.pipeline_client = self.session.client("codepipeline")

        # The tools bucket could either be in the target profile, or from another account
        self.shared_tool_bucket_name = shared_tool_bucket_name if shared_tool_bucket_name \
            else self.stacks.get_output('S3BucketName')

    def load_local_snapshot(self, snapshot_id):
        self.snapshot_filename = "snapshot-{}/snapshot-{}.json".format(snapshot_id, snapshot_id)
        self.snapshot = Snapshot(filename=self.snapshot_filename)

    def _get_value(self, key):
        if key == 'GitHubToken':
            key = 'GitHubCommitStatusPAT'
        try:
            params_val = self.project_params.project_params.get(key) if self.project_params else None
            return (self.snapshot.get_param(key) or
                    params_val or
                    self.stacks.get_output(key) or
                    self.secrets.get_secret_value(key)[1])
            # pylint: disable=bare-except
            # botocore.errorfactory.ResourceNotFoundException may be thrown here,
            # but the exception to catch is client.exception.ResourceNotFoundException
            # according to https://github.com/boto/boto3/issues/1195
            # This should probably be done inside snapshott, stackt, and secrett
            # But see also
            # https://stackoverflow.com/questions/42975609/how-to-capture-botocores-nosuchkey-exception
        except:
            return None

    def _get_existing_bucket_policy_accounts(self):
        """
        Gets the AWS accounts that have read access to this S3 bucket. We are assuming that changes have only been made
        using these scripts and the CloudFormation template. If anything looks like it was changed manually, we fail
        :return: Account IDs that currently have read access to the bucket
        """
        try:
            result = self.s3.get_bucket_policy(Bucket=self.shared_tool_bucket_name)
        # FIXME: I couldn't seem to import the specific exception here
        except Exception:
            print("Could not find an existing bucket policy. Creating a new one")
            return []
        policy_json = json.loads(result["Policy"])

        if len(policy_json["Statement"]) > 1:
            raise Exception(UNEXPECTED_POLICY_MSG)

        policy = policy_json["Statement"][0]["Principal"]["AWS"]
        action = policy_json["Statement"][0]["Action"]
        if set(action) != {"s3:GetObject", "s3:ListBucket"}:
            raise Exception(UNEXPECTED_POLICY_MSG)

        if isinstance(policy, list):
            account_ids = list(map(lambda a: a.replace("arn:aws:iam::", "").replace(":root", ""), policy))
        else:
            account_ids = [policy.replace("arn:aws:iam::", "").replace(":root", "")]
        return account_ids

    def _process_parameter_overrides(self, overrides, keys):
        """
        There are parameters that we don't pass directly to the templates as is. For example ProofAccountIds needs to
        include both the provided ID, but also all the IDs that have been allowed so far as well. Any weird domain
        specific rule like that should go here
        :param overrides: Current parameter overrides
        :param keys: The keys we are interested in from the overrides
        :return: new overrides where the values have been processed according the rules in this function
        """
        new_overrides = copy.deepcopy(overrides)
        if "S3BucketToolsName" in keys and "S3BucketToolsName" not in new_overrides.keys():
            new_overrides["S3BucketToolsName"] = self.shared_tool_bucket_name
        if "ProofAccountIds" in keys and "ProofAccountIds" not in new_overrides.keys():
            existing_proof_accounts = self._get_existing_bucket_policy_accounts()
            existing_proof_accounts.append(overrides.get("ProofAccountIdToAdd"))
            existing_proof_accounts = list(set(existing_proof_accounts))
            new_overrides["ProofAccountIds"] =",".join(list(map(lambda p: "arn:aws:iam::{}:root".format(p), existing_proof_accounts)))
        return new_overrides



    def _make_parameters(self, keys, parameter_overrides):
        parameter_overrides = parameter_overrides if parameter_overrides else {}
        parameter_overrides = self._process_parameter_overrides(parameter_overrides, keys)
        parameters = []
        for key in sorted(keys):
            if key in parameter_overrides.keys():
                value = parameter_overrides.get(key)
            else:
                value = self._get_value(key)
            if value is not None:
                parameters.append({"ParameterKey": key, "ParameterValue": value})
        return parameters

    @staticmethod
    def print_parameters(parameters):
        for param in parameters:
            print("  {:20}: {}".format(param['ParameterKey'], param['ParameterValue']))

    def _create_stack(self, stack_name, parameters, template_body=None, template_url=None):
        if template_body:
            self.stacks.get_client().create_stack(StackName=stack_name,
                                                  TemplateBody=template_body,
                                                  Parameters=parameters,
                                                  Capabilities=Cloudformation.CAPABILITIES)
        elif template_url:
            self.stacks.get_client().create_stack(StackName=stack_name,
                                                  TemplateURL=template_url,
                                                  Parameters=parameters,
                                                  Capabilities=Cloudformation.CAPABILITIES)
    def _update_stack(self, stack_name, parameters, template_body=None, template_url=None):
        if template_body:
            self.stacks.get_client().update_stack(StackName=stack_name,
                                                  TemplateBody=template_body,
                                                  Parameters=parameters,
                                                  Capabilities=Cloudformation.CAPABILITIES)
        elif template_url:
            self.stacks.get_client().update_stack(StackName=stack_name,
                                                  TemplateURL=template_url,
                                                  Parameters=parameters,
                                                  Capabilities=Cloudformation.CAPABILITIES)

    def _create_or_update_stack(self, stack_name, parameters, template_name, template_body=None,
                                template_url=None):
        if not template_body and not template_url:
            raise Exception("Must provide either the body of the template being deployed, "
                            "or a url to download it from S3")

        if self.stacks.get_status(stack_name) is None:
            print("\nCreating stack '{}' with parameters".format(stack_name))
            Cloudformation.print_parameters(parameters)
            print("Using " + template_name)
            self._create_stack(stack_name, parameters, template_body=template_body,
                               template_url=template_url)
        else:
            print("\nUpdating stack '{}' with parameters".format(stack_name))
            Cloudformation.print_parameters(parameters)
            print("Using " + template_name)
            self._update_stack(stack_name, parameters, template_body=template_body,
                               template_url=template_url)

    def _get_s3_url_for_template(self, template_name, s3_template_source, parameter_overrides=None):
        if s3_template_source == Cloudformation.BUILD_TOOLS_IMAGE_S3_SOURCE:
            build_tools_image_id = parameter_overrides.get(BUILD_TOOLS_IMAGE_ID_KEY)
            if not build_tools_image_id:
                raise Exception("Cannot fetch build tool templates, no image id provided")
            return ("https://s3.amazonaws.com/{}/tool-account-images/image-{}/{}"
                         .format(self.shared_tool_bucket_name,
                                 build_tools_image_id,
                                 template_name))
        elif s3_template_source == Cloudformation.PROOF_ACCOUNT_IMAGE_S3_SOURCE:
            snapshot_id = parameter_overrides.get("SnapshotID")
            snapshot_id = snapshot_id if snapshot_id else self.snapshot.get_parameter('SnapshotID')

            if not snapshot_id:
                raise Exception("Cannot fetch proof account templates from S3 with no snapshot ID")
            return ("https://s3.amazonaws.com/{}/snapshot/snapshot-{}/{}"
                             .format(self.shared_tool_bucket_name,
                                     snapshot_id,
                                     template_name))


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
            template_url = self._get_s3_url_for_template(template_name, s3_template_source, parameter_overrides)
            print(template_url)

        else:
            template_body = open(template_name).read()
        parameters = self._make_parameters(parameter_keys, parameter_overrides)
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

    def trigger_pipeline(self, pipeline_name):
        self.pipeline_client.start_pipeline_execution(name=pipeline_name)
    def _is_pipeline_complete(self, pipeline_name):
        pipeline_state = self.pipeline_client.get_pipeline_state(name=pipeline_name)
        return all("latestExecution" in state.keys()
                       for state in pipeline_state["stageStates"]) \
               and not any(state["latestExecution"]["status"] == "InProgress"
                       for state in pipeline_state["stageStates"])

    def wait_for_pipeline_completion(self, pipeline_name):
        print("Waiting for build pipeline: {0}".format(pipeline_name))
        while not self._is_pipeline_complete(pipeline_name):
            time.sleep(1)
        print("Done waiting for build pipeline: {0}".format(pipeline_name))

    def get_current_snapshot_id(self):
        return self.stacks.get_output("SnapshotID")

    def get_proof_s3_bucket_name(self):
        return self.stacks.get_output("S3BucketProofs")

    def get_cloudfront_url(self):
        return self.stacks.get_output("CloudfrontUrl")

    def set_cloudfront_url(self, url):
        self.stacks.get_output()

    def take_most_recent(self, objects):
        return sorted(objects, key=lambda o: o["LastModified"], reverse=True)[0]

    def extract_snapshot_name_from_key(self, key_prefix, all_objects):
        matching_objs = filter(lambda o: key_prefix in o["Key"], all_objects)
        most_recent_key = self.take_most_recent(matching_objs)["Key"]
        return most_recent_key.replace(key_prefix, "")

    def get_docker_image_suffix_from_ecr(self):
        return self.ecr.list_images(repositoryName="cbmc")["imageIds"][0]["imageTag"].replace("ubuntu16-gcc-", "")


    def get_package_filenames_from_s3(self):
        object_contents = self.s3.list_objects(Bucket=self.shared_tool_bucket_name, Prefix="package/")["Contents"]
        batch_pkg = self.extract_snapshot_name_from_key("package/batch/", object_contents)
        cbmc_pkg = self.extract_snapshot_name_from_key("package/cbmc/", object_contents)
        lambda_pkg = self.extract_snapshot_name_from_key("package/lambda/", object_contents)
        viewer_pkg = self.extract_snapshot_name_from_key("package/viewer/", object_contents)
        template_pkg = self.extract_snapshot_name_from_key("package/template/", object_contents)
        return {
            "batch": batch_pkg,
            "cbmc": cbmc_pkg,
            "lambda": lambda_pkg,
            "viewer": viewer_pkg,
            "templates": template_pkg,
            "docker": self.get_docker_image_suffix_from_ecr()
        }

    def update_and_write_snapshot(self):
        package_filenames = self.get_package_filenames_from_s3()
        self.snapshot.snapshot["batch"] = package_filenames.get("batch")
        self.snapshot.snapshot["cbmc"] = package_filenames.get("cbmc")
        self.snapshot.snapshot["lambda"] = package_filenames.get("lambda")
        self.snapshot.snapshot["viewer"] = package_filenames.get("viewer")
        self.snapshot.snapshot["docker"] = package_filenames.get("docker")
        self.snapshot.snapshot["templates"] = package_filenames.get("templates")
        self.snapshot.write(self.snapshot_filename)
