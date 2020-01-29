import argparse
import logging

from new_tools.account_orchestration.AccountOrchestrator import AccountOrchestrator

# acc = AccountOrchestrator(build_tools_profile="shared-tools",
#                           proof_profile="shared-proofs",
#                           tools_account_parameters_file="tools_parameters.json",
#                           proof_account_parameters_file="parameters.json")
#
# acc.use_existing_tool_account_snapshot("20200122-195252")
# # acc.generate_new_tool_account_snapshot()
# acc.deploy_globals()
# acc.deploy_build_tools()
# acc.add_proof_account_to_shared_bucket_policy()
#
#
# acc.generate_new_proof_account_snapshot()
# # acc.use_existing_proof_account_snapshot("20191217-160338")
#
# acc.deploy_proof_account_github()
# acc.deploy_proof_account_stacks()
# acc.set_account_environment_variables(is_ci_operating=True, update_github=True)

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
        snapshot_to_deploy = account_orchestrator.generate_new_proof_account_snapshot()
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

