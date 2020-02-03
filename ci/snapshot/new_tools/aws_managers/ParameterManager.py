import copy

import boto3

from new_tools.aws_managers.BucketPolicyManager import BucketPolicyManager

from secretst import Secrets


class ParameterManager:
    """
    This class manages which parameters we should pass to the various stacks we deploy. We have several different
    sources of data we use to populate our stack parameters so the purpose of this class is to simply expose an
    interface to easily get the parameters we need to deploy a stack
    """
    def __init__(self, profile, stacks,
                 snapshot=None,
                 snapshot_id=None,
                 proof_account_project_parameters=None,
                 shared_tool_bucket_name=None):
        self.session = boto3.session.Session(profile_name=profile)
        self.stacks = stacks
        self.secrets = Secrets(self.session)
        self.s3 = self.session.client("s3")
        self.snapshot = snapshot
        self.snapshot_id = snapshot_id
        self.proof_account_project_parameters = proof_account_project_parameters
        self.shared_tool_bucket_name = shared_tool_bucket_name
        self.bucket_policy_manager = BucketPolicyManager(profile, self.shared_tool_bucket_name)

    def get_value(self, key, parameter_overrides=None):
        """
        Returns the value we should associate with the given key. Draws from the following data sources in
        this order of preference:
        1) parameter_overrides
        2) current snapshot
        3) current project parameters,
        4) existing stack outputs
        5) existing stack secret values
        :param key:
        :param parameter_overrides:
        """
        parameter_overrides = parameter_overrides if parameter_overrides else {}
        parameter_overrides = self._process_parameter_overrides(parameter_overrides, key)

        if key == 'GitHubToken':
            key = 'GitHubCommitStatusPAT'
        # Return in order
        override_val = parameter_overrides.get(key) if parameter_overrides else None
        snapshot_val = self.snapshot.get_parameter(key) or self.snapshot.get(key) if self.snapshot else None
        proof_account_project_parameters_val = self.proof_account_project_parameters.get_parameter(key) \
            if self.proof_account_project_parameters else None
        if sum([bool(snapshot_val), bool(proof_account_project_parameters_val)]) > 1:
            raise Exception("Parameter has been set multiple times")
        try:
            return (
                override_val or
                snapshot_val or
                proof_account_project_parameters_val or
                self.stacks.get_output(key) or
                self.secrets.get_secret_value(key)[1]
            )
        except Exception:
            return None

    def get_value_from_stacks(self, key):
        return self.stacks.get_output(key)

    def _process_parameter_overrides(self, overrides, keys):
        #Rename with something descriptive
        """
        There are parameters that we don't pass directly to the templates as is. For example ProofAccountIds needs to
        include both the provided ID, but also all the IDs that have been allowed so far as well. Any weird domain
        specific rule like that should go here
        :param overrides: Current parameter overrides
        :param keys: The keys we are interested in from the overrides
        :return: new overrides where the values have been processed according the rules in this function
        """
        new_overrides = copy.deepcopy(overrides)
        # Only bucket policy, other two shouldn't be here
        if "S3BucketToolsName" in keys and "S3BucketToolsName" not in new_overrides.keys():
            new_overrides["S3BucketToolsName"] = self.shared_tool_bucket_name
        if "ProofAccountIds" in keys and "ProofAccountIds" not in new_overrides.keys():
            new_overrides["ProofAccountIds"] = self.bucket_policy_manager\
                .add_account_to_bucket_policy(overrides.get("ProofAccountIdToAdd"))
        if "SnapshotID" in keys and "SnapshotID" not in new_overrides.keys():
            new_overrides["SnapshotID"] = self.snapshot_id
        return new_overrides

    def make_stack_parameters(self, keys, parameter_overrides):
        """
        Produces the set of parameters used to deploy a stack with Cloudformation given the sources of data
        currently set in theo object
        :param keys: list of keys we want to find values for
        :param parameter_overrides: any overrides that should take precedence over existing sources
        :return:
        """
        parameter_overrides = parameter_overrides if parameter_overrides else {}
        parameter_overrides = self._process_parameter_overrides(parameter_overrides, keys)
        parameters = []

        for key in sorted(keys):
            if key in parameter_overrides.keys():
                value = parameter_overrides.get(key)
            else:
                value = self.get_value(key)
            if value is not None:
                parameters.append({"ParameterKey": key, "ParameterValue": value})
        return parameters
