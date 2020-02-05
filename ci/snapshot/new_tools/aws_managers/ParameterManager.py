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
        self.account_id = self.session.client('sts').get_caller_identity().get('Account')
        self.snapshot = snapshot
        self.snapshot_id = snapshot_id
        self.proof_account_project_parameters = proof_account_project_parameters.get(self.account_id) \
            if proof_account_project_parameters else None
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
        parameter_overrides = self._add_bucket_policy_param(parameter_overrides, key)

        if key == 'GitHubToken':
            key = 'GitHubCommitStatusPAT'
        override_val = parameter_overrides.get(key) if parameter_overrides else None
        if override_val:
            return override_val
        snapshot_val = self.snapshot.get(key) if self.snapshot else None
        if snapshot_val:
            return snapshot_val
        proof_account_project_parameters_val = self.proof_account_project_parameters.get(key) \
            if self.proof_account_project_parameters else None
        if proof_account_project_parameters_val:
            return proof_account_project_parameters_val
        stack_output = self.stacks.get_output(key)
        if stack_output:
            return stack_output
        try:
            secret_val = self.secrets.get_secret_value(key)
            if len(secret_val) > 0:
                return secret_val[1]
        except Exception:
            print("No such secret {}".format(key))
        print("Did not find value for key {}. Using template default.".format(key))
        return None
    def get_value_from_stacks(self, key):
        return self.stacks.get_output(key)

    def _add_bucket_policy_param(self, overrides, keys):
        """
        When building a bucket policy stack we need to list every single account that will get access to the bucket.
        This is a bad user experience so here we allow the user the give only the account ID they want to add, then we
        go and find what accounts are already allowed and return the parameters with the value that will add
        only the new account
        :param overrides:
        :param keys:
        :return: new overrides with proof account ids set to what is required to create the bucket policy
        """
        new_overrides = copy.deepcopy(overrides)
        if "ProofAccountIds" in keys and "ProofAccountIds" not in new_overrides.keys():
            new_overrides["ProofAccountIds"] = self.bucket_policy_manager\
                .add_account_to_bucket_policy(overrides.get("ProofAccountIdToAdd"))
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
        if "SnapshotID" not in parameter_overrides.keys():
            parameter_overrides["SnapshotID"] = self.snapshot_id
        if "S3BucketToolsName" not in parameter_overrides.keys():
            parameter_overrides["S3BucketToolsName"] = self.shared_tool_bucket_name
        parameter_overrides = self._add_bucket_policy_param(parameter_overrides, keys)
        parameters = []

        for key in sorted(keys):
            if key in parameter_overrides.keys():
                value = parameter_overrides.get(key)
            else:
                value = self.get_value(key)
            if value is not None:
                parameters.append({"ParameterKey": key, "ParameterValue": value})
        return parameters
