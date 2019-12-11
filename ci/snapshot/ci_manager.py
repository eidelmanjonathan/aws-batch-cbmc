import argparse
import json
import logging

from cloudformation import Cloudformation
from snapshot_deployer import SnapshotDeployer
from tools_account_image_manager import ToolsAccountImageManager


class CiManager:
    DOUBLE_ASSIGNMENT_ERROR = "Cannot assign value in both file and command line argument"

    def __init__(self):
        self.args = self.parse_args()
        self.promote_from_profile = None
        self.target_profile = None
        self.build_tools_profile = None
        # We can provide profile values from a file, but command line arguments take pre
        if self.args.profile_info_file:
            if self.args.profile or self.args.build_profile:
                raise Exception(CiManager.DOUBLE_ASSIGNMENT_ERROR)
            profile_info = self._get_profile_info_from_file(self.args.profile_info_file)
            self.target_profile = profile_info.get("profile")
            self.build_tools_profile = profile_info.get("build-profile")
        if self.args.profile:
            self.target_profile = self.args.profile
        if self.args.build_profile:
            self.build_tools_profile = self.args.build_profile
        if self.args.promote_from_profile:
            self.promote_from_profile = self.args.promote_from_profile

        self.cloudfront_profile = self.args.cloudfront_profile

        self.snapshot_filename = self.args.snapshot
        self.build_tools_image_filename = self.args.build_tools_image_filename
        self.project_params_filename = self.args.project_params

        self.snapshot_deployer = SnapshotDeployer(build_tools_profile=self.build_tools_profile,
                                                  proof_profile=self.target_profile,
                                                  cloudfront_profile=self.cloudfront_profile,
                                                  snapshot_filename=self.snapshot_filename,
                                                  parameters_filename=self.project_params_filename)

        if self.promote_from_profile:
            self.promote_source_cloudformation = Cloudformation(self.promote_from_profile)

    def _get_profile_info_from_file(self, filename):
        f = open(filename)
        return json.loads(f.read())

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

        arg.add_argument('--cloudfront-profile',
                         metavar='PROFILE',
                         help="""
                         This is an optional parameter for the AWS profile where we want to deploy our Cloudfront 
                         distribution. If this isn't provided we simply don't deploy Cloudfront
                         """)

        arg.add_argument('--promote-from-profile',
                         metavar='PROFILE',
                         help="""
                         The AWS profile whose snapshot we would like to deploy
                         in this target profile
                         """)

        arg.add_argument('--profile-info-file',
                         metavar='filename.json',
                         help="""
                         If you don't want to list all the profiles you are dealing with every time you run the command,
                         you can provide them in a json file
                         """)

        arg.add_argument('--snapshot',
                         metavar='FILE',
                         default="snapshot.json",
                         help='Snapshot file to deploy from filesystem'
                         )

        arg.add_argument('--bootstrap-build-tools-account',
                         action='store_true',
                         help='Use local yaml to bootstrap a new build tools account')

        arg.add_argument('--build-tools-image-filename',
                         metavar='FILE',
                         default='build-tools-image.json',
                         help='Build tools image file')

        arg.add_argument('--new-build-tools-image',
                         action='store_true',
                         help='Generate new build tools image')

        arg.add_argument('--deploy-build-tools-image',
                         action='store_true',
                         help='Deploy a build tools image')
        arg.add_argument('--build-tools-image-id',
                         metavar='IMAGEID',
                         help='build tools image ID we want to deploy')

        arg.add_argument('--project-params',
                         metavar='FILE',
                         default="parameters.json",
                         help='JSON file with project parameters'
                         )

        arg.add_argument('--new-proof-account-snapshot',
                         action='store_true',
                         help='Update build account and generate new snapshot')

        arg.add_argument('--deploy-snapshot',
                         action='store_true',
                         help='Deploy a snapshot')

        arg.add_argument('--snapshot-id',
                         metavar='SNAPSHOTID',
                         help='Snapshot ID to deploy in proof account')

        arg.add_argument('--debug-change',
                         action='store_true',
                         help='Run debug flow')

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

    def debug_change(self):
        """
        This is a flow to quickly deploy the whole stack for the purposes of debugging. It generates a new
        build tool and proof image and deploys both, but does not trigger all the builds. This way, you only
        wait for the pipelines that you actually changed
        :return:
        """
        tool_image_manager = ToolsAccountImageManager(self.build_tools_profile,
                                                      image_filename=self.build_tools_image_filename)
        build_tools_image_id = tool_image_manager.generate_new_image_from_latest()
        self.snapshot_deployer.deploy_globals(build_tools_image_id=build_tools_image_id)
        self.snapshot_deployer.deploy_build_tools(build_tools_image_id=build_tools_image_id)

        snapshot_id = self.snapshot_deployer.create_new_snapshot()
        self.snapshot_deployer.reload_all_snapshots(snapshot_id)
        self.snapshot_deployer.add_proof_account_to_shared_bucket_policy(snapshot_id)
        self.snapshot_deployer.deploy_proof_account_github(snapshot_id)
        self.snapshot_deployer.deploy_proof_account_stacks(snapshot_id)
        self.snapshot_deployer.deploy_cloudfront_stacks(snapshot_id)
        cloudfront_url = self.snapshot_deployer.cloudfront_account.get_cloudfront_url()
        self.snapshot_deployer.deploy_proof_account_github(snapshot_id, cloudfront_url=cloudfront_url)

    def create_new_build_tools_image(self):
        self.snapshot_deployer.trigger_all_builds()
        tool_image_manager = ToolsAccountImageManager(self.build_tools_profile,
                                                      image_filename=self.build_tools_image_filename)
        return tool_image_manager.generate_new_image_from_latest()

    def deploy_build_tools_image(self, build_tools_image_id):
        self.snapshot_deployer.deploy_globals(build_tools_image_id=build_tools_image_id)
        self.snapshot_deployer.deploy_build_tools(build_tools_image_id=build_tools_image_id)

    def deploy_build_tools_local_yamls(self):
        self.snapshot_deployer.deploy_globals()
        self.snapshot_deployer.deploy_build_tools()

    def create_new_proof_account_snapshot(self):
        """
        Updates the shared build account with the latest CloudFormation Yamls, triggers builds for all of the
        tools, and then creates a new snapshot with all of the latest builds
        :returns: New snapshot ID
        """
        self.snapshot_deployer.trigger_all_builds()
        snapshot_id = self.snapshot_deployer.create_new_snapshot()
        return snapshot_id

    def deploy_snapshot(self, snapshot_id):
        self.snapshot_deployer.add_proof_account_to_shared_bucket_policy(snapshot_id)
        self.snapshot_deployer.deploy_proof_account_github(snapshot_id)
        self.snapshot_deployer.deploy_proof_account_stacks(snapshot_id)

    def deploy_cloudfront(self, snapshot_id):
        self.snapshot_deployer.deploy_cloudfront_stacks(snapshot_id)

    def run(self):
        # If we are creating a brand new shared account, we must deploy from local YAMLs instead of
        # using a build tools image. This should only be used to boostrap a new account, and we should immediately
        # create an image after that
        if self.args.bootstrap_build_tools_account:
            self.deploy_build_tools_local_yamls()

        build_tools_image_id = None
        if self.args.new_build_tools_image:
            build_tools_image_id = self.create_new_build_tools_image()
            print(json.dumps({
                "build-tools-image-id": build_tools_image_id,
                "status": "Success"
            }))

        if self.args.deploy_build_tools_image:
            build_tools_image_id = build_tools_image_id if build_tools_image_id else self.args.build_tools_image_id
            if not build_tools_image_id:
                raise Exception("Must provide build tools image id")
            self.deploy_build_tools_image(build_tools_image_id)

        snapshot_id = None
        if self.args.new_proof_account_snapshot:
            snapshot_id = self.create_new_proof_account_snapshot()
            self.snapshot_deployer.reload_all_snapshots(snapshot_id)
            print(json.dumps({
                "snapshot-id": snapshot_id,
                "status": "Success"
            }))

        elif self.promote_from_profile:
            snapshot_id = self.promote_source_cloudformation.get_current_snapshot_id()

        if self.args.deploy_snapshot:
            if not self.target_profile:
                raise Exception("Must provide target profile to deploy proof account")

            if not snapshot_id and not self.args.snapshot_id:
                raise Exception("Must either generate a new snapshot, provide a snapshot ID, "
                                "or provide an account to take the snapshot from")
            if snapshot_id:
                snapshot_id = snapshot_id
            else:
                snapshot_id = self.args.snapshot_id
            self.deploy_snapshot(snapshot_id)
            print(json.dumps({
                "status": "Success"
            }))
            if self.cloudfront_profile:
                self.deploy_cloudfront(snapshot_id)
                cloudfront_url = self.snapshot_deployer.cloudfront_account.get_cloudfront_url()
                self.snapshot_deployer.deploy_proof_account_github(snapshot_id, cloudfront_url=cloudfront_url)

        if self.args.debug_change:
            self.debug_change()


if __name__ == '__main__':
    ci_manager = CiManager()
    ci_manager.run()
