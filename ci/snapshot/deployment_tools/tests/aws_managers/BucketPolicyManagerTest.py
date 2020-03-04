import unittest
from unittest.mock import Mock

from deployment_tools.aws_managers.BucketPolicyManager import BucketPolicyManager

SHARED_BUCKET_NAME = "TEST_BUCKET"
session_mock = Mock()
s3_client_mock = Mock()
session_mock.client = Mock(return_value=s3_client_mock)

bucketPolicyManager = BucketPolicyManager(session_mock, SHARED_BUCKET_NAME)

bucket_policy_response_one_account = {"Policy": """
{
    "Version": "2008-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::10000000:root"
            },
            "Action": [
                "s3:ListBucket",
                "s3:GetObject"
            ],
            "Resource": [
                "arn:aws:s3:::20000000-us-west-2-cbmc/*",
                "arn:aws:s3:::20000000-us-west-2-cbmc"
            ]
        }
    ]
}"""}

class BucketPolicyManagerTest(unittest.TestCase):

    def getExistingBucketPolicyOneExistingAccount(self):
        s3_client_mock.get_bucket_policy = Mock(return_value=bucket_policy_response_one_account)

        existing_accounts = bucketPolicyManager.get_existing_bucket_policy_accounts()
        self.assertEqual(existing_accounts, ['10000000'])

if __name__ == '__main__':
    unittest.main()
