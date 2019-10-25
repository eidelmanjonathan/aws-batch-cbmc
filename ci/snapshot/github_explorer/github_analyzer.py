import json
import os
import re
import subprocess
import urllib

from github import Github, UnknownObjectException

class GitAnalyzer:
    """
    Analyzes proof failures in Github repositories
    """
    def __init__(self, auth, repo_owner, repo_name, proof_base_directory = None, local_repo_folder = None,
                 cbmc_viewer_scripts_folder = None, branch_name = None, makefile_path = None, makefile_dependency_text=None):
        self.github = Github(auth)
        self.repo = self.github.get_repo(repo_owner + "/" + repo_name)
        self.local_repo_folder = local_repo_folder
        self.cbmc_viewer_scripts_folder = cbmc_viewer_scripts_folder
        self.branch = self.repo.get_branch(branch_name) if branch_name else None
        self.pr_merge_cache = {}
        self.proof_base_directory = proof_base_directory
        self.makefile_path = makefile_path
        self.makefile_dependency_text = makefile_dependency_text

    def _run(self, cmd, working_dir=None):
        p = subprocess.check_output(cmd.split(" "), cwd=working_dir, universal_newlines=True, encoding="437")
        return str(p)

    def adapt_makefile(self):
        """
        Creates a new version of the makefile with an additional command to compute the
        set of dependencies for a harness
        """
        self._run("mv {} {}".format(self.makefile_path, self.makefile_path + ".bk"))
        original_make_file = open(self.makefile_path + ".bk")
        makefile_txt = original_make_file.read()
        new_makefile_txt = makefile_txt + """
dependency:
	{}
        """.format(self.makefile_dependency_text)
        original_make_file.close()
        new_make_file = open(self.makefile_path, "w")
        new_make_file.write(new_makefile_txt)
        new_make_file.close()


    def restore_makefile(self):
        self._run("mv {} {}".format(self.makefile_path + ".bk", self.makefile_path))

    def get_pull_request_with_merge_for_sha(self, commit):
        """
        Returns the pull request number that is associated with the commit and that was merged into master
        TODO: Support other branches of interest
        :param commit: Commit object that we're interested in
        :return: Tuple with PR number and merge commit. Returns both None if PR was never merged
        """
        issues = self.github.search_issues(query="query", qualifiers={'type': 'pr',  'sha': commit.sha, 'is': 'merged', "repo": "aws/amazon-freertos"})

        # Assumes that only one
        for issue in issues:
            pull_number = issue.number
            if pull_number:
                pr = None
                merge_commit = self.get_commit_of_pull_request(pull_number, commit)
                if merge_commit:
                    return (merge_commit, pr)
        return (None, None)

    def get_commit_of_pull_request(self, pr_number, commit):
        """
        Gets the commit that merged a pull request into the master branch
        :param pr_number: PR number
        :param commit: The original commit that we were interested in. We use this so we only search through commits to
        master that happened after this commit
        :return: The commit that merged the PR to master
        """
        if pr_number in self.pr_merge_cache.keys():
            return self.pr_merge_cache[pr_number]
        try:
            merge_commit = next(filter(lambda c: GitAnalyzer.is_pr_merge_commit(c)
                                           and GitAnalyzer.get_merge_commit_pr_number(c) == pr_number,
                                       self.repo.get_commits(since=commit.commit.author.date if commit else None)))
            self.pr_merge_cache[pr_number] = merge_commit
            return merge_commit
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
        """
        Gets the pull request that merged this commit into master, if available. Otherwise returns the commit itself
        since it is assumed to be a push
        :param commit_hash: Commit sha we are interested in
        :return: A pair, commit and pull number. If pull number is not null, then the commit is the merge to master.
        otherwise it is just the commit associated with the given commit sha
        """
        commit = self.repo.get_commit(commit_hash)
        merge_commit, pr = self.get_pull_request_with_merge_for_sha(commit)
        if merge_commit:
            return (merge_commit, pr)
        if GitAnalyzer.is_pr_merge_commit(commit):
            pull_number = GitAnalyzer.get_merge_commit_pr_number(commit)
            return (commit, pull_number)
        return (commit, None)

    def get_failed_proofs_for_commit(self, commit):
        return list(set((map(lambda s: s.context.replace("CBMC Batch: ", ""), filter(lambda s: "CBMC Batch" in s.context
                                                                                               and  s.state == "failure"
                                                                                               or s.state == "error",
                                                                                     commit.get_statuses())))))

    def find_broken_actions_in_time_range(self, from_time, to_time):
        """
        Find all of the git actions (merges of PRs or pushes) that had failed proofs
        :param from_time:
        :param to_time:
        :return: list of commits/PR pairs
        """
        all_commits_in_range = self.repo.get_commits(since=from_time, until=to_time)
        found_actions = []
        for c in all_commits_in_range:
            final_commit, pr = self.get_git_action_for_sha(c.sha)
            failed_proofs = self.get_failed_proofs_for_commit(final_commit)
            if len(failed_proofs) > 0:
                found_actions.append((final_commit, pr))
        return found_actions

    def get_failure_point_comparison_commits(self, failed_commit):
        """
        Returns which commits we should compare. If it is a merge commit, we compare the two parents. Otherwise we
        compare the given commit with its parent
        :param failed_commit: Commit we are interested in
        :return: Two commits we should compare
        """
        if len(failed_commit.parents) > 1:
            return failed_commit.parents[0], failed_commit.parents[1]
        else:
            return failed_commit, failed_commit.parents[0]


    def find_point_of_failure(self, broken_commit, broken_proofs):
        """
        Returns the first commit before the broken_commit where the broken_proofs started failing
        :param broken_commit:
        :param broken_proofs:
        :return: Point of failure commit and PR if available
        """
        all_commits = self.repo.get_commits(until=broken_commit.commit.author.date)
        last_failed_action = None
        for c in all_commits:
            action_commit, action_pr = self.get_git_action_for_sha(c.sha)
            if action_commit.commit.author.date <= broken_commit.commit.author.date and self.all_proofs_succeed(action_commit, broken_proofs):
                if last_failed_action:
                    return last_failed_action
                return (action_commit, action_pr)
            last_failed_action = (action_commit, action_pr)

    def get_recent_commits_since(self, commit):
        """
        Returns all commits that have happened since given commit, beginning with the given commit
        :param commit:
        :return:
        """
        all_commits = self.repo.get_commits(since=commit.commit.author.date)
        recent_commits = []
        for c in all_commits:
            if c.sha == commit.sha:
                recent_commits.reverse()
                return recent_commits
            else:
                recent_commits.append(c)

    def all_proofs_succeed(self, commit, proofs):
        if commit.get_combined_status().state == "success":
            return True
        failed_proofs = self.get_failed_proofs_for_commit(commit)
        return set(proofs).isdisjoint(set(failed_proofs))

    def all_proofs_fail(self, commit, proofs):
        if commit.get_combined_status().state == "success":
            return False
        failed_proofs = self.get_failed_proofs_for_commit(commit)
        return(all(p in failed_proofs for p in proofs))

    def find_potential_fix(self, broken_commit, broken_proofs):
        """
        Returns the commit where the broken_proofs were fixed
        """
        all_commits = self.get_recent_commits_since(broken_commit)
        for c in all_commits:
            action_commit, action_pr = self.get_git_action_for_sha(c.sha)
            if action_commit.commit.author.date >= broken_commit.commit.author.date and self.all_proofs_succeed(action_commit, broken_proofs):
                return action_commit, action_pr

    def search_for_proof_directory(self, proof_name, root_directory):
        for dirpath, dirnames, files in os.walk(self.local_repo_folder + root_directory):
            if proof_name in dirpath:
                return dirpath.replace(self.local_repo_folder, "")

    def get_proof_files(self, proof_name):
        proof_directory = self.search_for_proof_directory(proof_name, self.proof_base_directory)
        proof_files = self.repo.get_contents(proof_directory)
        return proof_files

    def get_proof_harness_and_makefile(self, proof_name):
        proof_files = self.get_proof_files(proof_name)
        harness_file = next(filter(lambda f: "harness" in f.name, proof_files))
        makefile = next(filter(lambda f: "Makefile" in f.name, proof_files))
        return harness_file, makefile

    def _get_files_from_dependency_response(self, resp, harness_file, makefile):
        files = []
        for l in resp.splitlines():
            if self.local_repo_folder in l and "gcc" not in l:
                files.append(l.replace(self.local_repo_folder, "").replace(" \\", "").replace(" ", ""))
        files.append(makefile.path)
        files.append(harness_file.path)
        return files

    def get_harness_dependency_set(self, proof_name):
        if not self.local_repo_folder:
            raise Exception("Need a local repo folder!")
        harness_file, makefile = self.get_proof_harness_and_makefile(proof_name)
        directory = "/".join(makefile.path.split("/")[:-1]) + "/"
        proof_directory = self.local_repo_folder + directory
        files = []
        self.adapt_makefile()
        resp = self._run("make dependency", working_dir=proof_directory)
        self.restore_makefile()
        files = self._get_files_from_dependency_response(resp)
        return files


    def _get_relevant_filename(self, l, filepaths):
        for f in filepaths:
            if f in l:
                return f

    def parse_diff_results(self, diff, filepaths):
        relevant_section = False
        results_dict = {}
        current_relevant_filename = None
        for l in diff:
            if "diff" in l and any(map(lambda path: path in l, filepaths)) and not relevant_section:
                current_relevant_filename = self._get_relevant_filename(l, filepaths)
                if current_relevant_filename in results_dict.keys():
                    results_dict[current_relevant_filename] += l
                else:
                    results_dict[current_relevant_filename] = l
                relevant_section = True
            elif "diff" in l and relevant_section:
                results_dict[current_relevant_filename] += l
                relevant_section = False
                current_relevant_filename = None
            elif relevant_section:
                results_dict[current_relevant_filename] += l
        return results_dict

    def compare_file(self, filepaths, base, head):
        diff_filename = "diff_files/" + base + "_" + head + ".diff"
        if not os.path.exists(diff_filename):
            print(base)
            print(head)

            diff = self._run("git diff {} {}".format(base, head), working_dir=self.local_repo_folder)
            f = open(diff_filename, "w")
            f.write(diff)
            f.close()
        f = open(diff_filename, encoding = "ISO-8859-1")
        results_dict = self.parse_diff_results(f.readlines(), filepaths)
        f.close()
        return results_dict