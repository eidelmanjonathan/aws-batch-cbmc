#!/usr/bin/env python3

# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lambda function invoked in response to a Batch job changing state."""
import os
import time
import traceback
import json
import re
# import botocore_amazon.monkeypatch
import boto3

from cbmc_ci_github import update_status
private_bucket_name = os.environ['S3_BKT']
html_bucket_name  = private_bucket_name + "-html"

TIMEOUT = 30

class S3Manager:
    def __init__(self, private_bucket_name, html_bucket_name, session=None):
        if session:
            self.s3_client = session.client('s3')
            self.s3_resource = session.resource('s3')
        else:
            self.s3_client = boto3.client('s3')
            self.s3_resource = boto3.resource('s3')

        # S3 Bucket name for storing CBMC Batch packages and outputs
        self.private_bucket_name = private_bucket_name
        self.html_bucket_name = html_bucket_name
<<<<<<< HEAD

        self.html_bucket_resource = self.s3_resource.Bucket(self.html_bucket_name)
=======
>>>>>>> 239e059b7e227ba1ef8eef0d849e031c97065680

        self.html_bucket_resource = self.s3_resource.Bucket(self.html_bucket_name)

<<<<<<< HEAD
=======

>>>>>>> 239e059b7e227ba1ef8eef0d849e031c97065680
    def read_from_s3(self, s3_path):
        """Read from a file in S3 Bucket

        For getting bookkeeping information from the S3 bucket.
        """
        return self.s3_client.get_object(Bucket=self.private_bucket_name, Key=s3_path)['Body'].read()

    def _get_all_object_keys_in_dir(self, s3_directory, wait_for_directory=False):
        """Returns a list of all keys that begin with this directory
        prefix in the private S3 bucket"""
        all_objs = None
        begin_time = time.time()
        timed_out = False
        while not all_objs and (not timed_out or not wait_for_directory):
            current_time = time.time()
            timed_out = current_time > begin_time + TIMEOUT
            all_objs = self.s3_client.list_objects(Bucket=self.private_bucket_name, Prefix=s3_directory).get("Contents")
        if timed_out:
            return None
        return list(map(lambda o: o["Key"], all_objs))

    def _copy_file_to_html_bucket(self, key):
        print("Copying file: {0}".format(key))
        copy_source = {
            'Bucket': self.private_bucket_name,
            'Key': key
        }
        self.html_bucket_resource.copy(copy_source, "PREFIX/" + key)

    def copy_to_html_bucket(self, s3_directory):
        object_keys_in_directory = self._get_all_object_keys_in_dir(s3_directory, wait_for_directory=True)
        if object_keys_in_directory:
            for k in object_keys_in_directory:
                self._copy_file_to_html_bucket(k)
        else:
            print("Could not find directory {0}".format(s3_directory))

# def main():
#     session = boto3.session.Session(profile_name="jeid-isengard")
#     s3_manager = S3Manager("509240887788-us-west-2-cbmc", "509240887788-us-west-2-cbmc-html", session=session)
#     s3_manager.copy_to_html_bucket("fake_folder")
#
# if __name__ == "__main__":
#     main()
#     print("Done")
# exit()

class Job_name_info:

    def __init__(self, job_name):
        job_name_match = self.check_job_name(job_name)
        if job_name_match:
            self.is_cbmc_batch_property_job = True
            self.job_name = job_name_match.group(1)
            self.timestamp = job_name_match.group(2)
        else:
            self.is_cbmc_batch_property_job = False

    @staticmethod
    def check_job_name(job_name):
        """Check job_name to see if it matches CBMC Batch naming conventions"""
        job_name_pattern = r"([\S]+)"
        timestamp_pattern = r"(\S{16})"
        pattern = job_name_pattern + timestamp_pattern + "-property$"
        res = re.search(pattern, job_name)
        return res

    def get_s3_dir(self):
        """Get s3 bucket directory based on CBMC Batch naming conventions"""
        return self.job_name + self.timestamp

    def get_s3_html_dir(self):
        """Get s3 bucket directory that contains HTML reports if they exist"""
        return self.get_s3_dir() + "/out/html/"

    def get_job_dir(self):
        """
        Get the job directory (in the repo) based on CBMC Batch naming
        conventions.
        """
        return self.job_name

def lambda_handler(event, context):
    # context.aws_request_id

    """
    Update the status of the GitHub commit appropriately depending on CBMC
    output.

    CBMC output is found in the S3 Bucket for CBMC Batch.

    While the lambda function gets triggered after any Batch job changes
    status, it should only perform an action when the status is "SUCCEEDED" or
    "FAILED" for a "-property" job generated by CBMC Batch.

    The event format from AWS Batch Event is here:
    https://docs.aws.amazon.com/batch/latest/userguide/batch_cwe_events.html
    """

    #pylint: disable=unused-argument
    s3_manager = S3Manager(private_bucket_name, html_bucket_name)

    print("CBMC CI End Event")
    print(json.dumps(event))
    job_name = event["detail"]["jobName"]
    status = event["detail"]["status"]
    job_name_info = Job_name_info(job_name)
    if (status in ["SUCCEEDED", "FAILED"] and
            job_name_info.is_cbmc_batch_property_job):
        s3_dir = job_name_info.get_s3_dir()
        job_dir = job_name_info.get_job_dir()
        # Prepare description for GitHub status update
        desc = "CBMC Batch job " + s3_dir + " " + status
        # Get bookkeeping information about commit
        repo_id = int(s3_manager.read_from_s3(s3_dir + "/repo_id.txt"))
        sha = s3_manager.read_from_s3(s3_dir + "/sha.txt").decode('ascii')
        draft_status = s3_manager.read_from_s3(s3_dir + "/is_draft.txt").decode('ascii')
        is_draft = draft_status.lower() == "true"
        try:
            # Get expected output substring
            expected = s3_manager.read_from_s3(s3_dir + "/expected.txt")
            # Get CBMC output
            cbmc = s3_manager.read_from_s3(s3_dir + "/out/cbmc.txt")
            if expected in cbmc:
                print("Expected Verification Result: {}".format(s3_dir))
                update_status(
                    "success", job_dir, s3_dir, desc, repo_id, sha, is_draft)
            else:
                print("Unexpected Verification Result: {}".format(s3_dir))
                update_status(
                    "failure", job_dir, s3_dir, desc, repo_id, sha, is_draft)

            # Copy HTML results to HTML bucket
            # Waits for HTML files to appear - may time out
            s3_manager.copy_to_html_bucket(job_name_info.get_s3_html_dir())


        except Exception as e:
            traceback.print_exc()
            # CBMC Error
            desc += ": CBMC Error"
            print(desc)
            update_status("error", job_dir, s3_dir, desc, repo_id, sha, False)
            raise e
    else:
        print("No action for " + job_name + ": " + status)

    # pylint says return None is useless
    # return None
