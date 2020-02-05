import argparse
import json
import logging

from new_tools.account_orchestration.AccountOrchestrator import AccountOrchestrator

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
                     The project specific parameters we want to pass in
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
                     metavar="PROFILE",
                     help="""
                     Any packages we want to use that aren't the latest
                     """)
    return arg
def parse_args():
    args = create_parser().parse_args()
    logging.info('Arguments: %s', args)
    return args

if __name__ == '__main__':
    args = parse_args()
    account_orchestrator = AccountOrchestrator(build_tools_profile=args.build_profile,
                                               proof_profile=args.proof_profile,
                                               proof_account_parameters_file=args.project_parameters)

    snapshot_to_deploy = None
    if args.generate_snapshot:
        package_overrides = None
        if args.package_overrides:
            with open(args.package_overrides) as f:
                package_overrides = json.loads(f.read())
        account_orchestrator.add_proof_account_to_shared_bucket_policy()
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
        if not args.generate_snapshot:
            account_orchestrator.add_proof_account_to_shared_bucket_policy()
        account_orchestrator.use_existing_proof_account_snapshot(snapshot_to_deploy)
        account_orchestrator.deploy_proof_account_github()
        account_orchestrator.deploy_proof_account_stacks()
        account_orchestrator.set_proof_account_environment_variables()

