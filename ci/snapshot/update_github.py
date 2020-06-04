import json
import os
from datetime import datetime

import github

class GithubUpdater:
    GIT_SUCCESS = "success"
    GIT_FAILURE = "failure"

    def __init__(self, repo_id=None, oath_token=None, session_uuid=None):
        self.session_uuid = session_uuid
        self.g = github.Github(oath_token)
        self.repo = self.g.get_repo(repo_id)

    def update_status(self, status=GIT_SUCCESS, proof_name=None, commit_sha=None, cloudfront_url=None):
        kwds = {'state': status,
                'context': proof_name,
                'description': "Description",
                'target_url': cloudfront_url}
        print(f"Updating github status with the following parameters:\n{json.dumps(kwds, indent=2)}")
        self.repo.get_commit(sha=commit_sha).create_status(**kwds)
        return

    def get_rate_limit(self):
        rl = self.g.get_rate_limit()
        core = rl.core
        return core.remaining
    def get_reset_time(self):
        rtime = self.g.rate_limiting_resettime
        dt_object = datetime.fromtimestamp(rtime)
        return dt_object
