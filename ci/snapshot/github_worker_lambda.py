import os
import json
import time
from math import floor, ceil
from datetime import datetime
from time import sleep
from update_github import GithubUpdater

import boto3
TIME_LIMIT_MINUTES = 10

queue_url = os.getenv("QUEUE_URL")
queue_name = os.getenv("GITHUB_QUEUE_NAME")

class Sqs:
    def __init__(self, queue_url=None, queue_name=None):
        self.queue_url=queue_url
        self.sqs = boto3.client("sqs")
        self.sqs_resource = boto3.resource("sqs")
        print(f"Trying to get resource for queue with name: {queue_name}")
        self.queue = self.sqs_resource.get_queue_by_name(QueueName=queue_name)

    def delete_message(self, m):
        self.queue.delete_messages(
            Entries=[
                {
                    'Id': m.message_id,
                    "ReceiptHandle": m.receipt_handle
                },
            ]
        )
    def receive_message(self):
        return self.queue.receive_messages(MaxNumberOfMessages=10)

def lambda_handler(event, request):
    sqs = Sqs(queue_url=queue_url, queue_name=queue_name)
    g = None
    remaining_calls = None
    time_to_reset = None
    seconds = None

    # Run for 10 minutes
    t_end = time.time() + 60 * TIME_LIMIT_MINUTES
    while time.time() < t_end:
        for m in sqs.receive_message():
            github_msg = json.loads(m.body)
            print(json.dumps(github_msg, indent=2))

            # We should only create the GithubUpdater once
            # since it uses up some of our API limit
            if g is None or remaining_calls is None or time_to_reset is None or seconds is None:
                g = GithubUpdater(repo_id=int(github_msg["repo_id"]),
                                  oath_token=github_msg["oath"])
                remaining_calls = g.get_rate_limit()
                time_to_reset = g.get_reset_time() - datetime.now()
                seconds = floor(time_to_reset.total_seconds())
                print(f"Rate limit remaining: {remaining_calls}")
                print(f"Seconds to reset: {seconds}")
            if remaining_calls == 0:
                raise Exception(f"Hit the Github API ratelimit. Failed to deliver message:{json.dumps(github_msg, indent=2)}")
            elif remaining_calls <= seconds:
                # Exit, we cannot process this call right now
                return
            cloudfront_url = github_msg["cloudfront_url"] if "cloudfront_url" in github_msg else None
            g.update_status(status=github_msg["status"], proof_name=github_msg["context"], commit_sha=github_msg["commit"],
                            cloudfront_url=cloudfront_url, description=github_msg["description"])
            sqs.delete_message(m)
            remaining_calls = remaining_calls - 1

