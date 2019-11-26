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

UNEXPECTED_POLICY_MSG = "Someone has changed the bucket policy on the shared build account. " \
                              "There should only be one statement. Bucket policy should only be updated " \
                              "with CloudFormation template. Aborting!"
class Cloudformation:
    CAPABILITIES = ['CAPABILITY_NAMED_IAM']

    def __init__(self, profile, snapshot_filename, project_params_filename=None, shared_tool_bucket_name = None):
        self.profile = profile
        self.session = boto3.session.Session(profile_name=profile)
        self.account_id = self.session.client('sts').get_caller_identity().get('Account')
        self.stacks = Stacks(self.session)
        self.s3 = self.session.client("s3")
        self.snapshot = Snapshot(filename=snapshot_filename)
        self.project_params = ProjectParams(filename=project_params_filename) if project_params_filename else None
        self.secrets = Secrets(self.session)
        self.pipeline_client = self.session.client("codepipeline")

        # The tools bucket could either be in the target profile, or from another account
        self.shared_tool_bucket_name = shared_tool_bucket_name if shared_tool_bucket_name \
            else self.stacks.get_output('S3BucketName')

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

    # This function gets any weird rule about parameters that we don't want to include anywhere else in the logic
    def _process_parameter_overrides(self, overrides, keys):
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

    def _get_s3_url_for_template(self, template_name, parameter_overrides = None):
        snapshot_id = parameter_overrides.get("SnapshotID")
        snapshot_id = snapshot_id if snapshot_id else self.snapshot.get_parameter('SnapshotID')

        if not snapshot_id:
            raise Exception("Cannot fetch templates from S3 with no snapshot ID")
        return ("https://s3.amazonaws.com/{}/snapshot/snapshot-{}/{}"
                         .format(self.shared_tool_bucket_name,
                                 snapshot_id,
                                 template_name))


    def deploy_stack(self, stack_name, template_name, parameter_keys,
                     s3_template_source=False, parameter_overrides=None):
        template_url = None
        template_body = None
        if s3_template_source:
            template_url = self._get_s3_url_for_template(template_name, parameter_overrides)
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

    def deploy_stacks(self, stacks_to_deploy, s3_template_source=False, overrides = None):
        stack_names = stacks_to_deploy.keys()
        if not self.stacks.stable_stacks(stack_names):
            print("Stacks not stable: {}".format(stack_names))
            # quit
        for key in stacks_to_deploy.keys():
            self.deploy_stack(key, stacks_to_deploy[key][TEMPLATE_NAME_KEY],
                              stacks_to_deploy[key][PARAMETER_KEYS_KEY],
                              s3_template_source=s3_template_source,
                              parameter_overrides=overrides)
        self.stacks.wait_for_stable_stacks(stack_names)


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
