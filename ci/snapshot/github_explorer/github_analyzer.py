import json
import os
import re
import subprocess
import urllib

from github import Github, UnknownObjectException

PROOF_DIRECTORY_CACHE_FILENAME = "proof_directories.json"
REPO_PROOF_BASE_DIRECTORY = "tools/cbmc/proofs"

class GitAnalyzer:

    def __init__(self, auth, repo_owner, repo_name, local_repo_folder = None):
        self.github = Github(auth)
        self.repo = self.github.get_repo(repo_owner + "/" + repo_name)
        proof_directory_cache_file = open(PROOF_DIRECTORY_CACHE_FILENAME, "r")
        self.proof_directory_cache = json.loads(proof_directory_cache_file.read())
        proof_directory_cache_file.close()
        self.local_repo_folder = local_repo_folder

    def _run(self, cmd, working_dir=None):
        p = subprocess.check_output(cmd.split(" "), cwd=working_dir, universal_newlines=True)
        return str(p)

    def get_pull_request_number_for_sha(self, commit):
        # print("looking for PR:" + commit.sha)
        issues = self.github.search_issues(query="query", qualifiers={'type': 'pr',  'sha': commit.sha, 'is': 'merged', "repo": "aws/amazon-freertos"})

        # Assumes that only one
        for issue in issues:
            # print(issue)
            pull_number = issue.number
            if pull_number:
                pr = None
                merge_commit = self.get_commit_of_pull_request(pull_number, commit)
                if merge_commit:
                    return (merge_commit, pr)
        return (None, None)

    def get_commit_of_pull_request(self, pr_number, commit=None):
        try:
            if commit:
                return next(filter(lambda c: GitAnalyzer.is_pr_merge_commit(c)
                                               and GitAnalyzer.get_merge_commit_pr_number(c) == pr_number,
                                     self.repo.get_commits(since=commit.commit.author.date if commit else None)))
            else:
                return next(filter(lambda c: GitAnalyzer.is_pr_merge_commit(c)
                                             and GitAnalyzer.get_merge_commit_pr_number(c) == pr_number,
                                   self.repo.get_commits()))
        except StopIteration:
            return None

    @staticmethod
    def is_pr_merge_commit(commit):
        if "Merge pull request" in commit.commit.message:
            return True
        return False

    @staticmethod
    def get_merge_commit_pr_number(commit):
        return int(re.search("Merge pull request #\d*", commit.commit.message).group(0).replace("Merge pull request #", ""))

    def get_git_action_for_sha(self, commit_hash):
        commit = self.repo.get_commit(commit_hash)
        merge_commit, pr = self.get_pull_request_number_for_sha(commit)
        if merge_commit:
            return (merge_commit, pr)
        if GitAnalyzer.is_pr_merge_commit(commit):
            pull_number = GitAnalyzer.get_merge_commit_pr_number(commit)
            return (commit, pull_number)
        return (commit, None)

    def get_failed_proofs_for_commit(self, commit):
        return list(map(lambda s: s.context.replace("CBMC Batch: ", ""), filter(lambda s: s.state == "failure", commit.get_statuses())))

    def find_broken_actions_in_time_range(self, from_time, to_time, broken_proofs = None):
        all_commits_in_range = self.repo.get_commits(since=from_time, until=to_time)
        found_actions = []
        for c in all_commits_in_range:
            final_commit, pr = self.get_git_action_for_sha(c.sha)
            failed_proofs = self.get_failed_proofs_for_commit(final_commit)
            if broken_proofs is not None and all(broken_proof in failed_proofs for broken_proof in broken_proofs):
                found_actions.append((final_commit, pr))
            elif broken_proofs is None and len(failed_proofs) > 0:
                found_actions.append((final_commit, pr))
        return found_actions

    def get_failure_point_comparison_commits(self, failed_commit):
        if len(failed_commit.parents) > 1:
            return failed_commit.parents[0], failed_commit.parents[1]
        else:
            return failed_commit, failed_commit.parents[0]


    def find_point_of_failure(self, broken_commit):
        all_commits = self.repo.get_commits(until=broken_commit.commit.author.date)
        last_failed_action = None
        for c in all_commits:
            action_commit, action_pr = self.get_git_action_for_sha(c.sha)
            print("Searching for point of failure - commit {} has status: {}".format(action_commit.sha, action_commit.get_combined_status().state))
            if action_commit.commit.author.date <= broken_commit.commit.author.date and action_commit.get_combined_status().state == "success":
                if last_failed_action:
                    return last_failed_action
                return (action_commit, action_pr)
            last_failed_action = (action_commit, action_pr)

    def get_recent_commits_since(self, commit):
        all_commits = self.repo.get_commits(since=commit.commit.author.date)
        recent_commits = []
        for c in all_commits:
            if c.sha == commit.sha:
                recent_commits.reverse()
                return recent_commits
            else:
                recent_commits.append(c)

    def find_potential_fix(self, broken_commit):
        all_commits = self.get_recent_commits_since(broken_commit)
        for c in all_commits:
            action_commit, action_pr = self.get_git_action_for_sha(c.sha)
            print("Searching for point of fix - commit {} has status: {}".format(action_commit.sha, action_commit.get_combined_status().state))
            if action_commit.commit.author.date >= broken_commit.commit.author.date and action_commit.get_combined_status().state == "success":
                return action_commit, action_pr

    def search_for_proof_directory(self, proof_name, root_directory):
        all_files = self.repo.get_contents(root_directory)
        for f in all_files:
            if proof_name in f.name:
                return f.path
            if not f.content:
                recursive_response = self.search_for_proof_directory(proof_name, f.path)
                if recursive_response:
                    return recursive_response

    def save_proof_directory_cache(self):
        f = open("proof_directories.json", "w")
        f.write(json.dumps(self.proof_directory_cache))
        f.close()

    def get_proof_files(self, proof_name):
        if proof_name in self.proof_directory_cache.keys():
            proof_directory = self.proof_directory_cache.get(proof_name)
            try:
                proof_files = self.repo.get_contents(proof_directory)
            except UnknownObjectException:
                proof_directory = self.search_for_proof_directory(proof_name, REPO_PROOF_BASE_DIRECTORY)
                proof_files = self.repo.get_contents(proof_directory)
        else:
            proof_directory = self.search_for_proof_directory(proof_name, REPO_PROOF_BASE_DIRECTORY)
            proof_files = self.repo.get_contents(proof_directory)

        self.proof_directory_cache[proof_name] = proof_directory
        self.save_proof_directory_cache()
        return proof_files

    def get_proof_harness_and_makefile(self, proof_name):
        proof_files = self.get_proof_files(proof_name)
        harness_file = next(filter(lambda f: "harness" in f.name, proof_files))
        makefile = next(filter(lambda f: "Makefile" in f.name, proof_files))
        return harness_file, makefile

    def get_harness_dependency_cone(self, proof_name):
        if not self.local_repo_folder:
            raise Exception("Need a local repo folder!")
        harness_file, makefile = self.get_proof_harness_and_makefile(proof_name)
        directory = makefile.path.replace("/Makefile.json", "")
        print(self.local_repo_folder + directory)
        resp = self._run("make cone", working_dir=self.local_repo_folder + directory + "/").splitlines()
        files =[]
        for l in resp:
            if self.local_repo_folder in l:
                files.append(l.replace(self.local_repo_folder, "").replace(" \\", "").replace(" ", ""))
        return files

    def compare_file(self, filepaths, base, head):
        diff_filename = "diff_files/" + base + "_" + head + ".diff"
        if not os.path.exists(diff_filename):
            comparison = self.repo.compare(base, head)
            urllib.request.urlretrieve(comparison.diff_url, diff_filename)
        f = open(diff_filename, encoding = "ISO-8859-1")
        print(filepaths)
        relevant_section = False
        for l in f.readlines():
            if any(map(lambda path: path in l, filepaths)) and not relevant_section:
                relevant_section = True
                print(l)
            elif "diff" in l and relevant_section:
                print(l)
                relevant_section = False
            elif relevant_section:
                print(l)
        f.close()