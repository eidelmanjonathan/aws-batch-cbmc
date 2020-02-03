import json

import boto3

UNEXPECTED_POLICY_MSG = "Someone has changed the bucket policy on the shared build account. " \
                              "There should only be one statement. Bucket policy should only be updated " \
                              "with CloudFormation template. Aborting!"
class BucketPolicyManager:
    """
    This class manages changes to S3 bucket policies. The purpose of this is to grant read access to CI accounts to a
    shared S3 bucket that stores account snapshots. This allows us to share account snapshots between CI accounts,
    guaranteeing similar behaviour between accounts.
    """

    def __init__(self, profile, shared_tool_bucket_name):
        self.session = boto3.session.Session(profile_name=profile)
        self.shared_tool_bucket_name = shared_tool_bucket_name
        self.s3 = self.session.client("s3")

    def get_existing_bucket_policy_accounts(self):
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

    def add_account_to_bucket_policy(self, accountIdToAdd):
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