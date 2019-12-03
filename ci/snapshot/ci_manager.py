import argparse
import json
import logging

from snapshot_deployer import SnapshotDeployer


class CiManager:

    def __init__(self):
        self.args = self.parse_args()
        self.target_profile = self.args.profile
        self.build_tools_profile = self.args.build_profile
        self.snapshot_filename = self.args.snapshot
        self.project_params_filename = self.args.project_params

        self.snapshot_deployer = SnapshotDeployer(self.build_tools_profile, self.target_profile,
                                                  self.snapshot_filename, self.project_params_filename)



    def create_parser(self):
        arg = argparse.ArgumentParser(description="""
        Update an account: either update beta or promote beta to prod.
        """)

        arg.add_argument('--profile',
                         metavar='PROFILE',
                         help='The target AWS account profile to deploy CI infra on'
                         )

        arg.add_argument('--build-profile',
                         metavar='PROFILE',
                         help="""
                         The AWS account profile for the build account
                         (defaults to prod account)."""
                         )

        arg.add_argument('--snapshot',
                         metavar='FILE',
                         default="snapshot.json",
                         help='Snapshot file to deploy from filesystem'
                         )
        arg.add_argument('--project-params',
                         metavar='FILE',
                         default="parameters.json",
                         help='JSON file with project parameters'
                         )

        arg.add_argument('--new-snapshot',
                         action='store_true',
                         help='Update build account and generate new snapshot')

        arg.add_argument('--deploy-snapshot',
                         action='store_true',
                         help='Deploy a snapshot')

        arg.add_argument('--snapshot-id',
                         metavar='SNAPSHOTID',
                         help='Snapshot ID to deploy in proof account')

        arg.add_argument('--verbose',
                         action='store_true',
                         help='Verbose output.'
                         )
        arg.add_argument('--debug',
                         action='store_true',
                         help='Debug output.'
                         )

        return arg

    def parse_args(self):
        args = self.create_parser().parse_args()
        if args.verbose:
            logging.basicConfig(level=logging.INFO)
        if args.debug:
            logging.basicConfig(level=logging.DEBUG)
        logging.info('Arguments: %s', args)
        return args

    def create_new_snapshot(self):
        """
        Updates the shared build account with the latest CloudFormation Yamls, triggers builds for all of the
        tools, and then creates a new snapshot with all of the latest builds
        :returns: New snapshot ID
        """
        self.snapshot_deployer.deploy_globals()
        snapshot_id = self.snapshot_deployer.create_new_snapshot()
        self.snapshot_deployer.deploy_build_tools(snapshot_id)
        return snapshot_id

    def deploy_snapshot(self, snapshot_id):
        self.snapshot_deployer.add_proof_account_to_shared_bucket_policy(snapshot_id)
        self.snapshot_deployer.deploy_proof_account_github(snapshot_id)
        self.snapshot_deployer.deploy_proof_account_stacks(snapshot_id)

    def run(self):
        new_snapshot_id = None
        if self.args.new_snapshot:
            new_snapshot_id = self.create_new_snapshot()
            print(json.dumps({
                "snapshot-id": new_snapshot_id,
                "status": "Success"
            }))

        if self.args.deploy_snapshot:
            if not self.target_profile:
                raise Exception("Must provide target profile to deploy proof account")
            if not new_snapshot_id and not self.args.snapshot_id:
                raise Exception("Must either generate a new snapshot or provide a snapshot ID")
            if new_snapshot_id:
                snapshot_id = new_snapshot_id
            else:
                snapshot_id = self.args.snapshot_id
            self.deploy_snapshot(snapshot_id)
            print(json.dumps({
                "status": "Success"
            }))




if __name__ == '__main__':
    ci_manager = CiManager()
    ci_manager.run()
