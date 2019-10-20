import argparse
import json

import dateutil

from github_analyzer import GitAnalyzer
import datetime
PARAMS_FNAME = "params.json"
DEFAULT_INTERVAL = 24
def create_parser():
    arg = argparse.ArgumentParser(description="""
    Github proof failure diagnosis tool
    """)

    arg.add_argument("--get-broken-commits",
                     action="store_true",
                     help="Get all broken commits between two time stamps")

    arg.add_argument("--find-fix",
                     action="store_true",
                     help="Find suspected fix for broken proofs")
    arg.add_argument("--find-point-of-failure",
                     action="store_true",
                     help="Finds point where the proofs started failing, gives diff with immediately before failure")

    arg.add_argument("--commit-sha",
                     metavar="SHA",
                     help="The sha of the commit we are interested in"
                     )

    arg.add_argument("--interval-hours",
                     metavar="HOURS",
                     help="We will search for utc time +-HOURS")

    arg.add_argument("--utc",
                     metavar="TIME",
                     help="Time when the errors we are looking for happened")

    arg.add_argument("--local_repo_folder",
                     metavar="PATH",
                     help="Where your local git repo is")

    arg.add_argument("--pretty-print",
                     action="store_true",
                     help="Pretty print diffs instead of spitting out json")
    arg.add_argument("--params-file",
                     metavar="FILENAME",
                     help="json File with static parameters")
    return arg

args = create_parser().parse_args()

params_f = open(args.params_file if args.params_file else PARAMS_FNAME)
params_map = json.loads(params_f.read())

auth_str = params_map.get("git-authentication")
git_owner = params_map.get("git-owner")
git_repo = params_map.get("git-repo")
local_repo_folder = params_map.get("local-repo-folder")
branch_name = params_map.get("branch-name")
cbmc_viewer_scripts_folder = params_map.get("cbmc-viewer-scripts-folder")
proof_base_directory = params_map.get("proofs-root-folder")
makefile_path = params_map.get("makefile")
makefile_dependency_text = params_map.get("makefile-dependency-text")

g = GitAnalyzer(auth_str, git_owner, git_repo, makefile_path=makefile_path, proof_base_directory=proof_base_directory, cbmc_viewer_scripts_folder=cbmc_viewer_scripts_folder, local_repo_folder=local_repo_folder, branch_name=branch_name, makefile_dependency_text=makefile_dependency_text)

def generate_action_dict(commit, pr):
    action_dict = {
        "commit_sha": commit.sha,
        "commit_message": commit.commit.message,
        "commit_date": datetime.datetime.strftime(commit.commit.author.date, "%Y-%m-%dT%H:%M:%S"),
        "pull_request_number": pr
    }
    failed_proofs = g.get_failed_proofs_for_commit(commit)
    if failed_proofs:
        action_dict["failed_proofs"] = failed_proofs
    return action_dict

def pretty_print(diff_map):
    for key in diff_map.keys():
        print("-----------------")
        print(key)
        print(diff_map[key])
        print("-----------------")
if args.get_broken_commits:
    interval = int(args.interval_hours) if args.interval_hours else DEFAULT_INTERVAL
    utc = datetime.datetime.strptime(args.utc, "%Y-%m-%dT%H:%M:%S")
    start_time =utc - datetime.timedelta(hours=interval)
    end_time = utc + datetime.timedelta(hours=interval)
    broken_actions = g.find_broken_actions_in_time_range(start_time, end_time)
    actions_found = []
    for a in broken_actions:
        actions_found.append(generate_action_dict(a[0], a[1]))

    print(json.dumps(actions_found))

if args.find_fix:
    commit, pr = g.get_git_action_for_sha(args.commit_sha)
    broken_proofs = g.get_failed_proofs_for_commit(commit)
    fix_commit, fix_pr = g.find_potential_fix(commit, broken_proofs)
    failed_commit, fail_pr = g.find_point_of_failure(commit, broken_proofs)
    diff_map = {}
    for broken_proof in broken_proofs:
        harness_file, makefile = g.get_proof_harness_and_makefile(broken_proof)
        diff_map.update(g.compare_file([harness_file.path], failed_commit.sha, fix_commit.sha))
        diff_map.update(g.compare_file([makefile.path],  failed_commit.sha, fix_commit.sha))
    if args.pretty_print:
        pretty_print(diff_map)
    else:
        print(json.dumps(diff_map))

if args.find_point_of_failure:
    commit, pr = g.get_git_action_for_sha(args.commit_sha)
    broken_proofs = g.get_failed_proofs_for_commit(commit)
    failure_commit, failure_pr = g.find_point_of_failure(commit, broken_proofs)
    commit1, commit2 = g.get_failure_point_comparison_commits(failure_commit)
    broken_proofs = g.get_failed_proofs_for_commit(failure_commit)
    diff_map = {}
    for broken_proof in broken_proofs:
        dependencies = g.get_harness_dependency_set(broken_proof)
        diff_map.update(g.compare_file(dependencies, commit1.sha, commit2.sha))
    if args.pretty_print:
        pretty_print(diff_map)
    else:
        print(json.dumps(diff_map))



