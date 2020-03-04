import json
import logging

import boto3

UNEXPECTED_POLICY_MSG = "Someone has changed the bucket policy on the shared build account. " \
                              "There should only be one statement. Bucket policy should only be updated " \
                              "with CloudFormation template. Aborting!"
MISSING_BUCKET_POLICY_MESSAGE = "An error occurred (NoSuchBucketPolicy) when calling the GetBucketPolicy operation: The bucket policy does not exist"
class BucketPolicyManager:
    """
    This class manages changes to S3 bucket policies. The purpose of this is to grant read access to CI accounts to a
    shared S3 bucket that stores account snapshots. This allows us to share account snapshots between CI accounts,
    guaranteeing similar behaviour between accounts.
    """

    def __init__(self, session, shared_tool_bucket_name):
        self.session = session
        self.shared_tool_bucket_name = shared_tool_bucket_name
        self.s3 = self.session.client("s3")
        self.logger = logging.getLogger("BucketPolicyManager")
        self.logger.setLevel(logging.INFO)

    def _verify_missing_policy_exception(self, e):
        """
        If we have a missing bucket policy, do nothing, for any other exception, raise it
        :param e: an exception
        """
        if str(e) == MISSING_BUCKET_POLICY_MESSAGE:
            self.logger.info("Could not find an existing bucket policy. Creating a new one")
            return
        else:
            raise e

    def get_existing_bucket_policy_accounts(self):
        """
        Gets the AWS accounts that have read access to this S3 bucket. We are assuming that changes have only been made
        using these scripts and the CloudFormation template. If anything looks like it was changed manually, we fail
        :return: Account IDs that currently have read access to the bucket
        """
        try:
            result = self.s3.get_bucket_policy(Bucket=self.shared_tool_bucket_name)

        # FIXME: I couldn't seem to import the specific exception here
        except Exception as e:
            # If the exception is that there is no bucket policy, we can safely create one
            # If there is any other exception, raise it and error out
            self._verify_missing_policy_exception(e)
            return []
        policy_json = json.loads(result["Policy"])

        if len(policy_json["Statement"]) > 1:
            raise Exception(UNEXPECTED_POLICY_MSG)

        policy = policy_json["Statement"][0]["Principal"]["AWS"]
        # Make sure policy is a list and not a single object
        policy = policy if isinstance(policy, list) else [policy]

        action = policy_json["Statement"][0]["Action"]
        if set(action) != {"s3:GetObject", "s3:ListBucket"}:
            raise Exception(UNEXPECTED_POLICY_MSG)

        account_ids = list(map(lambda a: a.replace("arn:aws:iam::", "").replace(":root", ""), policy))

        return account_ids

    def build_bucket_policy_arns_list(self, accountIdToAdd):
        """
        Returns the list of arns we would need to allow in the bucket policy if we are trying to add
        the given accountIdToAdd, as a comma separated string
        :param accountIdToAdd:
        :return: the list of arns, as a comma separated string
        """
        existing_proof_accounts = self.get_existing_bucket_policy_accounts()
        existing_proof_accounts.append(accountIdToAdd)
        existing_proof_accounts = list(set(existing_proof_accounts))
        return ",".join(
            list(map(lambda p: "arn:aws:iam::{}:root".format(p), existing_proof_accounts)))