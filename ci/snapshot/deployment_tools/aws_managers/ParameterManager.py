import copy
import logging

import boto3

from deployment_tools.aws_managers.BucketPolicyManager import BucketPolicyManager
from deployment_tools.aws_managers.key_constants import SHARED_BUCKET_PARAM_KEY

from secretst import Secrets


class ParameterManager:
    """
    This class manages which parameters we should pass to the various stacks we deploy. We have several different
    sources of data we use to populate our stack parameters so the purpose of this class is to simply expose an
    interface to easily get the parameters we need to deploy a stack
    """
    SNAPSHOT_ID_KEY = "SnapshotID"
    def __init__(self, session, stacks,
                 snapshot=None,
                 snapshot_id=None,
                 shared_tools_bucket=None,
                 project_parameters=None):
        self.session = session
        self.stacks = stacks
        self.secrets = Secrets(self.session)
        self.s3 = self.session.client("s3")
        self.account_id = self.session.client('sts').get_caller_identity().get('Account')
        self.snapshot = snapshot
        self.snapshot_id = snapshot_id
        self.logger = logging.getLogger('ParameterManager')
        self.logger.setLevel(logging.INFO)

        # We can store project specific parameters for several projects in a single JSON
        # we only want to use project parameters that are for this specific project ID
        self.project_parameters = project_parameters.get(self.account_id) \
            if project_parameters else None
        self.shared_tool_bucket_name = shared_tools_bucket
        self.bucket_policy_manager = BucketPolicyManager(self.session, self.shared_tool_bucket_name)

    ### Private methods

    def _get_secret_val(self, key):
        try:
            secret_val = self.secrets.get_secret_value(key)
            if len(secret_val) > 0:
                return secret_val[1]
        except Exception:
            self.logger.debug("No such secret {}".format(key))

    def _generate_overrides_with_bucket_policy(self, overrides, keys):
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
        if "ProofAccountIds" in keys and "ProofAccountIds" not in new_overrides:
            new_overrides["ProofAccountIds"] = self.bucket_policy_manager\
                .build_bucket_policy_arns_list(overrides.get("ProofAccountIdToAdd"))
        return new_overrides

    ### Public methods

    def get_value(self, key, parameter_overrides=None):
        """
        Returns the value we should associate with the given key. Draws from the following data sources in
        this order of preference:
        1) parameter_overrides
        2) current snapshot
        3) current project parameters,
        4) existing stack outputs
        5) existing stack secret values
        :param key: string
        :param parameter_overrides: dictionary (string -> string)
        """
        parameter_overrides = parameter_overrides if parameter_overrides else {}
        parameter_overrides = self._generate_overrides_with_bucket_policy(parameter_overrides, key)

        #FIXME: Once we're confident in new scripts, get rid of this weird mismatch
        if key == 'GitHubToken':
            key = 'GitHubCommitStatusPAT'

        if key in parameter_overrides:
            return parameter_overrides.get(key)

        if self.snapshot and key in self.snapshot:
            return self.snapshot.get(key)

        if self.project_parameters and key in self.project_parameters:
            return self.project_parameters.get(key)

        stack_output = self.stacks.get_output(key)
        if stack_output:
            return stack_output
        secret_val = self._get_secret_val(key)
        if secret_val:
            return secret_val
        self.logger.info("Did not find value for key {}. Using template default.".format(key))
        return None

    def make_stack_parameters(self, keys, parameter_overrides):
        """
        Produces the set of parameters used to deploy a stack with Cloudformation given the sources of data
        currently set in the object
        :param keys: list of keys we want to find values for
        :param parameter_overrides: any overrides that should take precedence over existing sources
        :return: a list of dictionaries that can be passed the CloudformationStacks object as parameters
        """
        parameter_overrides = parameter_overrides if parameter_overrides else {}
        parameter_overrides["SnapshotID"] = self.snapshot_id if "SnapshotID" not in parameter_overrides \
            else parameter_overrides["SnapshotID"]
        parameter_overrides["S3BucketToolsName"] = self.shared_tool_bucket_name \
            if "S3BucketToolsName" not in parameter_overrides else parameter_overrides["S3BucketToolsName"]
        parameter_overrides = self._generate_overrides_with_bucket_policy(parameter_overrides, keys)
        parameters = []

        for key in sorted(keys):
            value = parameter_overrides.get(key) if key in parameter_overrides else self.get_value(key)
            if value is not None:
                parameters.append({"ParameterKey": key, "ParameterValue": value})
        return parameters
