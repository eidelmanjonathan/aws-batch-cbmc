#!/usr/bin/env python3

# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lambda function invoked in response to a Batch job changing state."""
from datetime import datetime
import os
import time
import traceback
import json
import re
#import botocore_amazon.monkeypatch
from concurrent.futures.thread import ThreadPoolExecutor

import boto3

from cbmc_ci_github import update_status
private_bucket_name = os.environ['S3_BKT']
html_bucket_name  = private_bucket_name + "-html"
REPORT_PENDING_MESSAGE = "Report pending..."
CLOUDFRONT_URL = "d29x9pz2jmwmbm.cloudfront.net/"

TIMEOUT = 30

class S3Manager:
    def __init__(self, private_bucket_name, html_bucket_name, prefix=None, session=None):
        if session:
            self.s3_client = session.client('s3')
        else:
            self.s3_client = boto3.client('s3')

        # S3 Bucket name for storing CBMC Batch packages and outputs
        self.private_bucket_name = private_bucket_name
        self.html_bucket_name = html_bucket_name
        self.prefix = prefix if prefix else ""

    def get_html_prefix(self):
        return self.prefix

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
        print("Trying to copy file with only client: {0} from {1} to {2} with key {3}"
              .format(key, str(self.private_bucket_name), str(self.html_bucket_name), str(self.prefix + key)))
        copy_source = {
            'Bucket': self.private_bucket_name,
            'Key': key
        }
        self.s3_client.copy_object(CopySource=copy_source, Bucket=self.html_bucket_name, Key = self.prefix + key)
        print("Successfully copied file {0} from {1} to {2}"
              .format(key, str(self.private_bucket_name),
                      str(self.html_bucket_name)))

    def copy_to_html_bucket(self, s3_directory):
        object_keys_in_directory = self._get_all_object_keys_in_dir(s3_directory, wait_for_directory=True)
        print("Number of items in directory: {0}".format(str(len(object_keys_in_directory))))
        executor = ThreadPoolExecutor(max_workers=90)
        futures_list = []
        if object_keys_in_directory:
            for k in object_keys_in_directory:
                futures_list.append(executor.submit(self._copy_file_to_html_bucket, k))
            for f in futures_list:
                f.result()
            print("Finished copying directory")
        else:
            print("Could not find directory {0}".format(s3_directory))

# def main():
#     session = boto3.session.Session(profile_name="jeid-isengard")
#     s3_manager = S3Manager("509240887788-us-west-2-cbmc", "509240887788-us-west-2-cbmc-html", session=session)
#     s3_manager.copy_to_html_bucket("ARPGenerateRequestPacket-20190916-220139")
#
# if __name__ == "__main__":
#     main()
#     print("Done")
# exit()

class Job_name_info:

    def __init__(self, job_name):
        property_job_name_match = self.check_job_name(job_name, "property")
        report_job_name_match = self.check_job_name(job_name, "report")

        if property_job_name_match:
            self.is_cbmc_batch_property_job = True
            self.is_report_job = False
            self.job_name = property_job_name_match.group(1)
            self.timestamp = property_job_name_match.group(2)
        elif report_job_name_match:
            self.is_cbmc_batch_property_job = False
            self.is_report_job = True
            self.job_name = property_job_name_match.group(1)
            self.timestamp = property_job_name_match.group(2)
        else:
            self.is_cbmc_batch_property_job = False
            self.is_report_job = False

    @staticmethod
    def check_job_name(job_name, suffix):
        """Check job_name to see if it matches CBMC Batch naming conventions"""
        job_name_pattern = r"([\S]+)"
        timestamp_pattern = r"(\S{16})"
        pattern = job_name_pattern + timestamp_pattern + "-"+suffix+"$"
        res = re.search(pattern, job_name)
        return res

    def get_s3_dir(self):
        """Get s3 bucket directory based on CBMC Batch naming conventions"""
        return self.job_name + self.timestamp

    def get_s3_html_dir(self):
        """Get s3 bucket directory that contains HTML reports if they exist"""
        return self.get_s3_dir() + "/out/html/"

    def get_s3_html_index_file(self):
        return self.get_s3_html_dir() + "index.html"

    def get_job_dir(self):
        """
        Get the job directory (in the repo) based on CBMC Batch naming
        conventions.
        """
        return self.job_name

def lambda_handler(event, context):
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
    s3_manager = S3Manager(private_bucket_name, html_bucket_name,
                           prefix=datetime.today().strftime('%Y-%m-%d')
                                  + "/" + str(context.aws_request_id) + "/")

    print("CBMC CI End Event")
    print(json.dumps(event))
    job_name = event["detail"]["jobName"]
    status = event["detail"]["status"]
    job_name_info = Job_name_info(job_name)

    if status in ["SUCCEEDED", "FAILED"]:
        s3_dir = job_name_info.get_s3_dir()
        job_dir = job_name_info.get_job_dir()
        # Prepare description for GitHub status update
        desc = "CBMC Batch job " + s3_dir + " " + status
        # Get bookkeeping information about commit
        repo_id = int(s3_manager.read_from_s3(s3_dir + "/repo_id.txt"))
        sha = s3_manager.read_from_s3(s3_dir + "/sha.txt").decode('ascii')
        draft_status = s3_manager.read_from_s3(s3_dir + "/is_draft.txt").decode('ascii')
        is_draft = draft_status.lower() == "true"
        # Get expected output substring
        expected = s3_manager.read_from_s3(s3_dir + "/expected.txt")
        # Get CBMC output
        cbmc = s3_manager.read_from_s3(s3_dir + "/out/cbmc.txt")

        # If verification is complete but report hasn't been generated, we want to update Git status with result
        # Let user know the proof result, but that the full report is pending
        if job_name_info.is_cbmc_batch_property_job:
            try:

                if expected in cbmc:
                    print("Expected Verification Result: {}".format(s3_dir))
                    update_status(
                        "success", job_dir, REPORT_PENDING_MESSAGE, desc, repo_id, sha, is_draft)
                else:
                    print("Unexpected Verification Result: {}".format(s3_dir))
                    update_status(
                        "failure", job_dir, REPORT_PENDING_MESSAGE, desc, repo_id, sha, is_draft)

            except Exception as e:
                traceback.print_exc()
                # CBMC Error
                desc += ": CBMC Error"
                print(desc)
                update_status("error", job_dir, s3_dir, desc, repo_id, sha, False)
                raise e
        # If we have finished generating the report, copy all files to the HTML S3 bucket so they can be served with
        # CloudFront. Update Git to point to cloudFront URL
        elif job_name_info.is_report_job:
            # Copy HTML results to HTML bucket
            # Waits for HTML files to appear - may time out
            s3_manager.copy_to_html_bucket(job_name_info.get_s3_html_dir())
            index_file_link = job_name_info.get_s3_html_index_file()
            index_file_prefix = s3_manager.get_html_prefix()
            full_url = CLOUDFRONT_URL + index_file_prefix + index_file_link
            print("URL to report: " + str(full_url))
            try:
                if expected in cbmc:
                    print("Expected Verification Result: {}".format(s3_dir))
                    update_status(
                        "success", job_dir, full_url, desc, repo_id, sha, is_draft)
                else:
                    print("Unexpected Verification Result: {}".format(s3_dir))
                    update_status(
                        "failure", job_dir, full_url, desc, repo_id, sha, is_draft)
            # We should not try to update the git status on error, since we can
            # just leave what was there in the property step
            except Exception as e:
                traceback.print_exc()
                # CBMC Error
                desc += ": CBMC Error"
                print(desc)
                raise e


    else:
        print("No action for " + job_name + ": " + status)

    # pylint says return None is useless
    # return None
