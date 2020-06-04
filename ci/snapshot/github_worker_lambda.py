import os
import json
from math import floor, ceil
from datetime import datetime
from time import sleep
from update_github import GithubUpdater

import boto3
THROTTLE_THRESHOLD = 300
TIMEOUT_LIMIT = 500

queue_url = os.getenv("QUEUE_URL")

def enqueue_message(msg):
    sqs = boto3.client("sqs")
    sqs.send_message(QueueUrl=queue_url, MessageBody=msg)

def lambda_handler(event, request):
    print(event)
    g = None
    for r in event["Records"]:
        github_msg = json.loads(r["body"])
        print(json.dumps(github_msg, indent=2))

        # We should only create the GithubUpdater once
        # since it uses up some of our API limit
        if g is None:
            g = GithubUpdater(repo_id=int(github_msg["repo_id"]),
                              oath_token=github_msg["oath"])

        remaining_calls = g.get_rate_limit()
        time_to_reset = g.get_reset_time() - datetime.now()
        seconds = floor(time_to_reset.total_seconds())
        print(f"Rate limit remaining: {remaining_calls}")
        print(f"Seconds to reset: {seconds}")
        if remaining_calls < THROTTLE_THRESHOLD and remaining_calls <= seconds:
            sleep_time = ceil(seconds / remaining_calls)

            if sleep_time >= TIMEOUT_LIMIT:
                sleep(TIMEOUT_LIMIT)
                enqueue_message(json.dumps(github_msg))
                return

            print(f"Running low on github Sleeping for {sleep_time} seconds")
            sleep(sleep_time)

        g.update_status(status=github_msg["status"], proof_name=github_msg["context"], commit_sha=github_msg["commit"])
