import argparse
import json

import dateutil

from github_analyzer import GitAnalyzer
import datetime
PARAMS_FNAME = "params.json"
def create_parser():
    arg = argparse.ArgumentParser(description="""
    Github proof failure diagnosis tool
    """)

    arg.add_argument('--git-authentication',
                     metavar='AUTHSTRING',
                     help='The github authentication string for your account'
                    )
    arg.add_argument('--git-owner',
                     metavar='OWNER',
                     help="The github owner of the repository you're working on")
    arg.add_argument("--git-repo",
                     metavar="REPO",
                     help="The repository name you are working on")

    arg.add_argument("--get-broken-commits",
                     action="store_true",
                     help="Get all broken commits between two time stamps")

    arg.add_argument("--find-point-of-failure",
                     action="store_true",
                     help="Find the earliest git committed push or pull request before the given sha "
                          "where the given proofs failed")
    arg.add_argument("--find-point-of-success",
                     action="store_true",
                     help="Find the earliest git committed push or pull request after the given sha "
                          "where the given proofs succeeded")
    arg.add_argument("--get-diff-fail-to-fix",
                     action="store_true",
                     help="Finds the point of failure related to this sha, the point of success, and computes "
                          "the diff of all the harness files for the proofs we are interested in")
    arg.add_argument("--get-diff-point-of-failure",
                     action="store_true",
                     help="Gives the diff between files relevant to the proof immediately before failure, "
                          "and with failure")
    arg.add_argument("--commit-sha",
                     metavar="SHA",
                     help="The sha of the commit we are interested in"
                     )

    arg.add_argument("--start-time",
                      metavar="TIME",
                      help="Start time for commits you are interested in. Format: YYYY-MM-DDTHH:MM:SS")

    arg.add_argument("--end-time",
                      metavar="TIME",
                      help="End time for commits you are interested in. Format: YYYY-MM-DDTHH:MM:SS")

    arg.add_argument("--broken-proofs",
                     nargs='+',
                     metavar="PROOFS",
                     help="List of proofs that are broken")
    arg.add_argument("--get-dependency-cone",
                     action="store_true",
                     help="Get all the dependencies of some proofs")
    arg.add_argument("--local_repo_folder",
                     metavar="PATH",
                     help="Where your local git repo is")
    return arg

args = create_parser().parse_args()
params_f = open(PARAMS_FNAME)
params_map = json.loads(params_f.read())

auth_str = args.git_authentication if args.git_authentication else params_map.get("git-authentication")
git_owner = args.git_owner if args.git_owner else params_map.get("git-owner")
git_repo = args.git_repo if args.git_repo else params_map.get("git-repo")
local_repo_folder = args.local_repo_folder if args.local_repo_folder else params_map.get("local-repo-folder")

g = GitAnalyzer(auth_str, git_owner, git_repo, local_repo_folder=local_repo_folder)

def generate_action_dict(commit, pr):
    return {
        "commit_sha": commit.sha,
        "commit_message": commit.commit.message,
        "commit_date": datetime.datetime.strftime(commit.commit.author.date, "%Y-%m-%dT%H:%M:%S"),
        "pull_request_number": pr
    }

if args.get_broken_commits:
    broken_proofs = args.broken_proofs if args.broken_proofs else None
    start_time =datetime.datetime.strptime(args.start_time, "%Y-%m-%dT%H:%M:%S")
    end_time =datetime.datetime.strptime(args.end_time, "%Y-%m-%dT%H:%M:%S")
    broken_actions = g.find_broken_actions_in_time_range(start_time, end_time,
                                                         broken_proofs=broken_proofs)
    actions_found = []
    for a in broken_actions:
        actions_found.append(generate_action_dict(a[0], a[1]))

    print(json.dumps(actions_found, indent=2))

if args.find_point_of_failure:
    commit, pr = g.get_git_action_for_sha(args.commit_sha)
    commit_of_failure, pr_of_failure = g.find_point_of_failure(commit)
    resp = generate_action_dict(commit_of_failure, pr_of_failure)
    print(json.dumps(resp, indent=2))

if args.find_point_of_success:
    commit, pr = g.get_git_action_for_sha(args.commit_sha)
    fix_commit, fix_pr = g.find_potential_fix(commit)
    resp = generate_action_dict(fix_commit, fix_pr)
    print(json.dumps(resp, indent=2))

if args.get_diff_fail_to_fix:
    commit, pr = g.get_git_action_for_sha(args.commit_sha)
    fix_commit, fix_pr = g.find_potential_fix(commit)
    failed_action, succeeded_action = g.find_point_of_failure(commit)
    failure_commit = failed_action
    broken_proofs = args.broken_proofs if args.broken_proofs else []
    for broken_proof in broken_proofs:
        print("Getting changes relevant to broken proof: {}".format(broken_proof))
        harness_file, makefile = g.get_proof_harness_and_makefile(broken_proof)
        g.compare_file([harness_file.path], failure_commit.sha, fix_commit.sha)
        g.compare_file([makefile.path],  failure_commit.sha, fix_commit.sha)
        print("------------------")

if args.get_diff_point_of_failure:
    commit, pr = g.get_git_action_for_sha(args.commit_sha)
    failure_commit, failure_pr = g.find_point_of_failure(commit)
    commit1, commit2 = g.get_failure_point_comparison_commits(failure_commit)
    print(commit1.sha + "-" + commit2.sha)
    broken_proofs = args.broken_proofs if args.broken_proofs else []
    for broken_proof in broken_proofs:
        print("Getting changes relevant to broken proof: {}".format(broken_proof))
        cone = g.get_harness_dependency_cone(broken_proof)
        g.compare_file(cone, commit1.sha, commit2.sha)
        print("------------------")

if args.get_dependency_cone:
    for proof in args.broken_proofs:
        g.get_harness_dependency_cone(proof)

