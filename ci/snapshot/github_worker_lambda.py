import boto3
import logging
import github
import json
from math import ceil
from datetime import datetime
from time import sleep
from update_github import GithubUpdater


def lambda_handler(event, request):
    print(event)
    g = None
    for r in event["Records"]:
        github_msg = json.loads(r["body"])
        print(json.dumps(github_msg, indent=2))
        if g is None:
            g = GithubUpdater(repo_id=int(github_msg["repo_id"]),
                              oath_token=github_msg["oath"])

        remaining_calls = g.get_rate_limit()
        time_to_reset = g.get_reset_time() - datetime.now()
        seconds = ceil(time_to_reset.total_seconds())
        print(f"Rate limit remaining: {remaining_calls}")
        print(f"Seconds to reset: {seconds}")
        if remaining_calls <= seconds:
            multiplier = ceil(seconds / remaining_calls)
            print(f"Sleeping for {multiplier} seconds")
            sleep(multiplier)

        g.update_status(status=github_msg["status"], proof_name=github_msg["context"], commit_sha=github_msg["commit"])
