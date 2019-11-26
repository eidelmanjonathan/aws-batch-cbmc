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


class Cloudformation:
    CAPABILITIES = ['CAPABILITY_NAMED_IAM']

    def __init__(self, profile, snapshot_filename, project_params_filename=None, shared_tool_bucket_name = None):
        self.session = boto3.session.Session(profile_name=profile)
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
            return (self.snapshot.get_param(key) or
                    self.project_params.project_params.get(key) or
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

    def _make_parameters(self, keys, parameter_overrides):
        parameter_overrides = parameter_overrides if parameter_overrides else {}
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

    def _get_s3_url_for_template(self, template_name):
        return ("https://s3.amazonaws.com/{}/snapshot/snapshot-{}/{}"
                         .format(self.shared_tool_bucket_name,
                                 self.snapshot.get_parameter('SnapshotID'),
                                 template_name))


    def deploy_stack(self, stack_name, template_name, parameter_keys,
                     s3_template_source=False, parameter_overrides=None):
        if s3_template_source:
            template_body = self._get_s3_url_for_template(template_name)
        else:
            template_body = open(template_name).read()
        parameters = self._make_parameters(parameter_keys, parameter_overrides)
        try:
            self._create_or_update_stack(stack_name, parameters, template_name, template_body)
        except botocore.exceptions.ClientError as err:
            code = err.response['Error']['Code']
            msg = err.response['Error']['Message']
            if code == 'ValidationError' and msg == 'No updates are to be performed.':
                print("Nothing to update")
            else:
                raise

    def deploy_stacks(self, stacks_to_deploy, s3_template_source=False):
        stack_names = stacks_to_deploy.keys()
        if not self.stacks.stable_stacks(stack_names):
            print("Stacks not stable: {}".format(stack_names))
        for key in stacks_to_deploy.keys():
            self.deploy_stack(key, stacks_to_deploy[key][TEMPLATE_NAME_KEY],
                              stacks_to_deploy[key][PARAMETER_KEYS_KEY],
                              s3_template_source=s3_template_source,
                              parameter_overrides=stacks_to_deploy[key].get(PARAMETER_OVERRIDES_KEY))
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
