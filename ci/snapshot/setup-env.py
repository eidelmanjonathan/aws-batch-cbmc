#!/usr/bin/env python3

# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import datetime
import json
import logging
import os
import random
import re
import string
import textwrap
import time
from os.path import join, isfile

import requests

import botocore_amazon.monkeypatch
import boto3
import botocore

import stackst
import snapshott
import secretst

################################################################


def create_parser():
    arg = argparse.ArgumentParser(description="""
    Deploy the stacks as described by a snapshot.
    """)

    arg.add_argument('--profile',
                     metavar='NAME',
                     help='AWS account profile name'
                    )
    arg.add_argument('--snapshot',
                     metavar='FILE',
                     required=True,
                     help='Snapshot file to deploy from filesystem'
                    )
    arg.add_argument('--email',
                     metavar='NAME',
                     help='Email address to use'
                    )

    arg.add_argument('--git_access_token',
                     metavar='NAME',
                     help='Git access token')
    return arg


class EnvironmentSetup:

    def __init__(self, session, profile, snapshot):
        self.session = session
        self.profile = profile
        self.email_client = self.session.client("ses")
        self.secret_client = self.session.client("secretsmanager")
        self.s3_client = self.session.client("s3")
        self.ecr_client = self.session.client("ecr")
        self.pipeline_client = self.session.client("codepipeline")
        self.snapshot = snapshot
        self.logger = logging.getLogger('env_setup_logger')
        self.logger.setLevel(logging.INFO)


    def verify_email_address(self, email):
        self.email_client.verify_email_address(EmailAddress=email)

    def set_git_access_token(self, git_access_token):
        lettersAndDigits = string.ascii_letters + string.digits
        github_random_secret = ''.join(random.choice(lettersAndDigits) for i in range(10))
        github_commit_status_pat_secret_string = '[{"GitHubPAT":"{0}"}]'.format(git_access_token)
        github_secret_string = '[{"Secret":"{0}"}]'.format(github_random_secret)
        self.secret_client.create_secret(name = "GitHubCommitStatusPAT", SecretString = github_commit_status_pat_secret_string)
        self.secret_client.create_secret(name = "GitHubSecret", SecretString =  github_secret_string)

    def trigger_deploy_global_stack(self):
        return os.popen("./snapshot-deploy --profile {0} --doit --globals --snapshot snapshot.json"
                        .format(self.profile)).read()

    def trigger_deploy_build_stacks(self):
        return os.popen("./snapshot-deploy --profile {0} --build --snapshot snapshot.json"
                        .format(self.profile)).read()

    def trigger_create_snapshot(self):
        logs = os.popen("./snapshot-create --profile {0} --snapshot updated_snapshot.json".format(self.profile)).read()
        print(logs)
        matching_snapshot_ids = re.findall("snapshot-\d*-\d*", logs)
        return matching_snapshot_ids[0].replace("snapshot-", "")


    def trigger_deploy_prod_stacks(self, timestamp_str):
        return os.popen("./snapshot-deploy --profile {0} --prod --snapshotid {1}".format(self.profile, timestamp_str)).read()

    def get_docker_image_suffix_from_ecr(self):
        return self.ecr_client.list_images(repositoryName="cbmc")["imageIds"][0]["imageTag"].replace("ubuntu16-gcc-", "")

    # Gets name of CBMC S3 bucket
    #FIXME: Assumes that there is only one bucket with cbmc in the name. Otherwise this is broken
    def get_cbmb_s3_bucket_name(self):
        resp = self.s3_client.list_buckets()
        bucket_names = map(lambda b: b["Name"], resp["Buckets"])
        return next(filter(lambda n: "cbmc" in n, bucket_names))

    def _take_most_recent(self, objects):
        return sorted(objects, key = lambda o: o["LastModified"], reverse=True)[0]

    # Takes the most recent snapshot
    def _extract_snapshot_name_from_key(self, key_prefix, all_objects):
        matching_objs = filter(lambda o: key_prefix in o["Key"], all_objects)
        most_recent_key = self._take_most_recent(matching_objs)["Key"]
        return most_recent_key.replace(key_prefix, "")

    def get_package_filenames_from_s3(self):
        cbmc_bucket_name = self.get_cbmb_s3_bucket_name()
        object_contents = self.s3_client.list_objects(Bucket=cbmc_bucket_name, Prefix="package/")["Contents"]
        batch_pkg = self._extract_snapshot_name_from_key("package/batch/" ,object_contents)
        cbmc_pkg = self._extract_snapshot_name_from_key("package/cbmc/" ,object_contents)
        lambda_pkg = self._extract_snapshot_name_from_key("package/lambda/" ,object_contents)
        viewer_pkg = self._extract_snapshot_name_from_key("package/viewer/" ,object_contents)
        template_pkg = self._extract_snapshot_name_from_key("package/template/" ,object_contents)

        return {
            "batch": batch_pkg,
            "cbmc": cbmc_pkg,
            "lambda": lambda_pkg,
            "viewer": viewer_pkg,
            "templates": template_pkg,
            "docker": self.get_docker_image_suffix_from_ecr()
        }

    def update_and_write_snapshot(self, package_filenames):
        self.snapshot.snapshot["batch"] = package_filenames.get("batch")
        self.snapshot.snapshot["cbmc"] = package_filenames.get("cbmc")
        self.snapshot.snapshot["lambda"] = package_filenames.get("lambda")
        self.snapshot.snapshot["viewer"] = package_filenames.get("viewer")
        self.snapshot.snapshot["docker"] = package_filenames.get("docker")
        self.snapshot.snapshot["templates"] = package_filenames.get("templates")
        self.snapshot.write("updated_snapshot.json")

    def get_all_snapshot_filenames(self):
        onlyfiles = [f for f in os.listdir("./") if isfile(join("./", f))]
        return list(filter(lambda f: "snapshot-" in f, onlyfiles))

    def get_snapshot_timestamp(self):
        dated_snapshots = filter(lambda s: ".json" in s and "snapshot-" in s, self.get_all_snapshot_filenames())
        dates = map(lambda s: datetime.datetime.strptime(s.replace(".json", "").replace("snapshot-", ""), "%Y%m%d-%H%M%S"), dated_snapshots)
        return sorted(dates, reverse=True)[0].strftime("%Y%m%d-%H%M%S")

    def is_pipeline_complete(self, pipeline_name):
        pipeline_state = self.pipeline_client.get_pipeline_state(name=pipeline_name)
        return not any(state["latestExecution"]["status"] == "InProgress" for state in pipeline_state["stageStates"])

    def wait_for_pipeline_completion(self, pipeline_name):
        print("Waiting for build pipeline: {0}".format(pipeline_name))
        while not self.is_pipeline_complete(pipeline_name):
            time.sleep(1)
        print("Done waiting for build pipeline: {0}".format(pipeline_name))

def main():
    args = create_parser().parse_args()
    snapshot = snapshott.Snapshot(filename=args.snapshot)
    session = boto3.session.Session(profile_name=args.profile)
    envSetup = EnvironmentSetup(session, args.profile, snapshot)
    # Verify email address if necessary
    if args.email:
        envSetup.verify_email_address(args.email)

    if args.git_access_token:
        envSetup.set_git_access_token(args.git_access_token)

    print(envSetup.trigger_deploy_global_stack())
    print(envSetup.trigger_deploy_build_stacks())

    envSetup.wait_for_pipeline_completion("Build-CBMC-Linux-Pipeline")
    envSetup.wait_for_pipeline_completion("Build-Docker-Pipeline")
    envSetup.wait_for_pipeline_completion("Build-Viewer-Pipeline")
    envSetup.wait_for_pipeline_completion("Build-Batch-Pipeline")

    package_filenames = envSetup.get_package_filenames_from_s3()
    envSetup.update_and_write_snapshot(package_filenames)

    snapshot_id = envSetup.trigger_create_snapshot()
    print(envSetup.trigger_deploy_prod_stacks(snapshot_id))



if __name__ == "__main__":
    main()
    print("done")