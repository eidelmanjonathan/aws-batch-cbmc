import argparse
import json
import logging

from new_tools.account_orchestration.AccountOrchestrator import AccountOrchestrator
from new_tools.aws_managers.BucketPolicyManager import BucketPolicyManager


def create_parser():
    arg = argparse.ArgumentParser(description="""
    Update an account: either update beta or promote beta to prod.
    """)

    arg.add_argument('--proof-profile',
                     metavar='PROFILE',
                     help='The target AWS account profile to deploy CI infra on'
                     )

    arg.add_argument('--build-profile',
                     metavar='PROFILE',
                     help="""
                     The AWS account profile for the build account."""
                     )
    arg.add_argument('--project-parameters',
                     metavar='parameters.json',
                     help="""
                     The filename of the json file with project specific parameters we want to pass in
                     """
                     )
    arg.add_argument('--generate-snapshot',
                     action="store_true",
                     help="""
                     Generate a snapshot based on latest builds
                     """
                     )

    arg.add_argument('--snapshot-id',
                     metavar="ID",
                     help="""
                     Snapshot ID to deploy
                     """
                     )

    arg.add_argument('--deploy-snapshot',
                     action="store_true",
                     help="""
                     Generate a snapshot based on latest builds
                     """
                     )
    arg.add_argument("--source-proof-profile",
                     metavar="PROFILE",
                     help="""
                     Account whose snapshot we want to deploy
                     """)
    arg.add_argument("--package-overrides",
                     metavar="package_overrides.json",
                     help="""
                     filename of a json file with packages we want to use that aren't the latest
                     """)
    return arg
def parse_args():
    args = create_parser().parse_args()
    logging.info('Arguments: %s', args)
    return args

def get_package_overrides(overrides_filename):
    with open(overrides_filename) as f:
        return json.loads(f.read())

if __name__ == '__main__':
    args = parse_args()
    account_orchestrator = AccountOrchestrator(build_tools_account_profile=args.build_profile,
                                               proof_account_profile=args.proof_profile,
                                               proof_account_parameters_file=args.project_parameters)
    if args.generate_snapshot and args.snapshot_id:
        raise Exception("Should not provide a snapshot ID if you are trying to generate a new snapshot")
    account_orchestrator.add_proof_account_to_shared_bucket_policy()
    snapshot_to_deploy = None
    if args.generate_snapshot:
        package_overrides = None
        if args.package_overrides:
            package_overrides = get_package_overrides(args.package_overrides)
        snapshot_to_deploy = account_orchestrator\
            .generate_new_proof_account_snapshot(overrides=package_overrides)
        print("Generated snapshot: {}".format(snapshot_to_deploy))

    elif args.snapshot_id:
        snapshot_to_deploy = args.snapshot_id

    elif args.source_proof_profile:
        snapshot_to_deploy = account_orchestrator.get_account_snapshot_id(args.source_proof_profile)

    if args.deploy_snapshot:
        if not snapshot_to_deploy:
            raise Exception("Must provide snapshot ID to deploy or generate new snapshot")
        account_orchestrator.use_existing_proof_account_snapshot(snapshot_to_deploy)
        account_orchestrator.deploy_proof_account_github()
        account_orchestrator.deploy_proof_account_stacks()
        account_orchestrator.set_proof_account_environment_variables()

