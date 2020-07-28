# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lambda function invoked in response to a Batch job changing state."""

import re
import os
import traceback
import json

import boto3

from cbmc_ci_github import update_status
import clog_writert

# S3 Bucket name for storing CBMC Batch packages and outputs
bkt = os.environ['S3_BUCKET_PROOFS']
PROPERTY = "property"
REPORT = "report"

def read_from_s3(s3_path):
    """Read from a file in S3 Bucket

    For getting bookkeeping information from the S3 bucket.
    """
    s3 = boto3.client('s3')
    return s3.get_object(Bucket=bkt, Key=s3_path)['Body'].read()


class Job_name_info:

    def __init__(self, job_name):
        job_name_match = self.check_job_name(job_name)
        if job_name_match:
            self.is_cbmc_batch_job = True
            self.job_name = job_name_match.group(1)
            self.timestamp = job_name_match.group(2)
            self.type = job_name_match.group(3)
        else:
            self.is_cbmc_batch_job = False

    def is_cbmc_property_job(self):
        return self.is_cbmc_batch_job and self.type == PROPERTY

    def is_cbmc_report_job(self):
        return self.is_cbmc_batch_job and self.type == REPORT

    @staticmethod
    def check_job_name(job_name):
        """Check job_name to see if it matches CBMC Batch naming conventions"""
        job_name_pattern = r"([\S]+)"
        timestamp_pattern = r"(\S{16})"
        pattern = job_name_pattern + timestamp_pattern + "-([a-z]*)$"
        res = re.search(pattern, job_name)
        return res

    def get_s3_dir(self):
        """Get s3 bucket directory based on CBMC Batch naming conventions"""
        return self.job_name + self.timestamp

    def get_full_name(self):
        return self.job_name + self.timestamp + "-" + self.type

    def get_job_dir(self):
        """
        Get the job directory (in the repo) based on CBMC Batch naming
        conventions.
        """
        return self.job_name


class CbmcResponseHandler:

    def __init__(self, job_name_info=None,
                 job_name=None,
                 parent_logger=None,
                 status=None,
                 event=None,
                 response=None,
                 job_dir=None,
                 s3_dir=None,
                 desc=None,
                 repo_id=None,
                 sha=None, is_draft=None):
        self.job_name_info = job_name_info
        self.job_name = job_name
        self.parent_logger = parent_logger
        self.status = status
        self.event = event
        self.response = response
        self.job_dir = job_dir
        self.s3_dir = s3_dir
        self.desc = desc
        self.repo_id = repo_id
        self.sha = sha
        self.is_draft = is_draft


    def handle_github_update(self, post_url=False):
        print("type: {}, is_cbmc_property_job: {}, job name: {}".format(self.job_name_info.type,
                                                                        self.job_name_info.is_cbmc_property_job(),
                                                                        self.job_name))
        # write parent task information once we get property answer.
        self.parent_logger.started()
        self.parent_logger.summary(clog_writert.SUCCEEDED, self.event, self.response)

        if self.status == "SUCCEEDED":
            # Get expected output substring
            expected = read_from_s3(self.s3_dir + "/expected.txt")
            self.response['expected_result'] = expected.decode('ascii')
            # Get CBMC output
            cbmc = read_from_s3(self.s3_dir + "/out/cbmc.txt")
            if expected in cbmc:
                print("Expected Verification Result: {}".format(self.s3_dir))
                update_status(
                    "success", self.job_dir, self.s3_dir, self.desc, self.repo_id, self.sha, self.is_draft, post_url=post_url)
                self.response['status'] = clog_writert.SUCCEEDED
            else:
                print("Unexpected Verification Result: {}".format(self.s3_dir))
                update_status(
                    "failure", self.job_dir, self.s3_dir, self.desc, self.repo_id, self.sha, self.is_draft, post_url=post_url)
                self.response['status'] = clog_writert.FAILED
        else:
            self.response['status'] = clog_writert.FAILED

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


    print("CBMC CI End Event")
    print(json.dumps(event))
    job_name = event["detail"]["jobName"]
    job_id = event["detail"]["jobId"]
    status = event["detail"]["status"]
    job_name_info = Job_name_info(job_name)
    if status in ["FAILED"]:
        print(f"ERROR: The following job has failed: {job_name} with status {status}")
        raise Exception(f"The following job has failed: {job_name} with status {status}")
    if (status in ["SUCCEEDED"] and
            job_name_info.is_cbmc_batch_job):
        s3_dir = job_name_info.get_s3_dir()
        job_dir = job_name_info.get_job_dir()
        # Prepare description for GitHub status update
        desc = "CBMC Batch job " + job_name + " " + status
        # Get bookkeeping information about commit
        repo_id = int(read_from_s3(s3_dir + "/repo_id.txt"))
        sha = read_from_s3(s3_dir + "/sha.txt").decode('ascii')
        draft_status = read_from_s3(s3_dir + "/is_draft.txt").decode('ascii')
        is_draft = draft_status.lower() == "true"
        correlation_list = read_from_s3(s3_dir + "/correlation_list.txt").decode('ascii')
        event["correlation_list"] = json.loads(correlation_list)
        response = {}

        # AWS batch 'magic' that must be added to wire together subprocesses since we don't modify cbmc-batch
        # What is happening here is that CBMC Batch creates subprocesses for four tasks: build, property (prove),
        # coverage, and viewer.  Since we don't want to modify the code for CBMC batch, we are post-facto creating
        # the correlation ids for these tasks to complete the proof tree when they finish.
        # We mark the parent task as completed when the 'property' task succeeds or fails.
        #
        # Although we are not tracking the child tasks accurately for, e.g., timings, the parent task is properly
        # tracked, and the overall timings are correct.
        #
        # See clog_writert.py for more information on correlation ids and logging.

        parent_logger = clog_writert.CLogWriter.init_lambda(s3_dir, event, context)
        child_correlation_list = parent_logger.create_child_correlation_list()
        child_logger = clog_writert.CLogWriter.init_aws_batch(job_name, job_id, child_correlation_list)
        child_logger.launched()
        child_logger.started()

        try:
            response_handler = CbmcResponseHandler(job_name_info=job_name_info, job_name=job_name,
                                                   parent_logger=parent_logger, status=status, event=event,
                                                   response=response, job_dir=job_dir, s3_dir=s3_dir, desc=desc,
                                                   repo_id=repo_id, sha=sha, is_draft=is_draft)
            if job_name_info.is_cbmc_property_job():
                response_handler.handle_github_update(post_url=False)
            elif job_name_info.is_cbmc_report_job():
                response_handler.handle_github_update(post_url=True)
            else:
                response['status'] = clog_writert.SUCCEEDED if (status == "SUCCEEDED") else clog_writert.FAILED

            child_logger.summary(response['status'], event, response)

        except Exception as e:
            traceback.print_exc()
            # CBMC Error
            desc += ": CBMC Error"
            print(desc)
            update_status("error", job_dir, s3_dir, desc, repo_id, sha, False)
            response['error'] = "Exception: {}; Traceback: {}".format(str(e), traceback.format_exc())
            parent_logger.summary(clog_writert.FAILED, event, response)
            child_logger.summary(clog_writert.FAILED, event, response)
            raise e

    else:
        print("No action for " + job_name + ": " + status)

    # pylint says return None is useless
    # return None
