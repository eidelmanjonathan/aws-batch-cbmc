import json
import os
from datetime import datetime

import github

OATH_TOKEN = os.getenv("GIT_OATH")
CLOUDFRONT_URL = os.getenv('CLOUDFRONT_URL')
GIT_REPO = os.getenv("GIT_REPO")
GIT_OATH = os.getenv("GIT_OATH")
REPO_OWNER = os.getenv("GIT_OWNER")
GIT_COMMIT_SHA = os.getenv("GIT_COMMIT_SHA")
UUID = os.getenv("UUID")
class GithubUpdater:
    GIT_SUCCESS = "success"
    GIT_FAILURE = "failure"
    LITANI_SUCCESS = "successful"
    LITANI_FAILURE = "failed"

    def __init__(self, repo_id=None, oath_token=None, cloudfront_url=None, session_uuid=None, status_json_filename = None):
        self.session_uuid = session_uuid
        self.g = github.Github(oath_token)
        self.repo = self.g.get_repo(repo_id)
        self.cloudfront_url = cloudfront_url
        if status_json_filename:
            with open(status_json_filename) as f:
                self.proof_statuses = json.loads(f.read())
        print(f"Created GithubUpdater for cloudfront: {cloudfront_url} with uuid: {session_uuid}")

    def update_status(self, status=GIT_SUCCESS, proof_name=None, commit_sha=None,):
        kwds = {'state': status,
                'context': proof_name,
                'description': "Description",
                'target_url': (f"https://{self.cloudfront_url}/{self.session_uuid}/{proof_name}/report/report/index.html")}
        self.repo.get_commit(sha=commit_sha).create_status(**kwds)
        print(json.dumps(kwds))
        return

    def get_rate_limit(self):
        rl = self.g.get_rate_limit()
        core = rl.core
        return core.remaining
    def get_reset_time(self):
        rtime = self.g.rate_limiting_resettime
        dt_object = datetime.fromtimestamp(rtime)
        return dt_object
