import subprocess

from account_orchestration.stacks_data import GLOBALS_CLOUDFORMATION_DATA, BUILD_TOOLS_CLOUDFORMATION_DATA
from aws_managers.AwsAccount import AwsAccount, BUILD_TOOLS_IMAGE_ID_KEY
from aws_managers.TemplatePackageManager import BUILD_TOOLS_IMAGE_S3_SOURCE

BUILD_TOOLS_PACKAGES = {
    "template": {"extract": True}
}

class AccountOrchestrator:


    def __init__(self, build_tools_profile=None,
                 proof_profile=None,
                 build_tool_image_filename=None,
                 proof_account_image_filename=None,
                 ):
        self.build_tools = AwsAccount(build_tools_profile, build_tools_image_filename=build_tool_image_filename)
        self.build_tools_image_manager = ImageManager(build_tools_profile,
                                                      bucket_name=self.build_tools.shared_tool_bucket_name,
                                                      packages_required=BUILD_TOOLS_PACKAGES)

        # self.snapshot_filename = snapshot_filename
        #
        # if proof_profile:
        #     self.proof_account = Cloudformation(proof_profile,snapshot_filename,
        #                                         project_params_filename=parameters_filename,
        #                                         shared_tool_bucket_name=self.build_tools.shared_tool_bucket_name)

    @staticmethod
    def parse_snapshot_id(output):
        sid = None
        for line in output.split('\n'):
            if line.startswith('Updating SnapshotID to '):
                sid = line[len('Updating SnapshotID to '):]
                break
        if sid is None:
            raise UserWarning("snapshot id is none")
        return sid

    @staticmethod
    def run(string):
        print('Running: {}'.format(string))
        result = subprocess.run(string.split(), capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        result.check_returncode()
        return result.stdout

    def deploy_globals(self, build_tools_image_id=None):
        # If we are deploying a particular image
        s3_template_source = BUILD_TOOLS_IMAGE_S3_SOURCE if build_tools_image_id else None
        param_overrides = {
            BUILD_TOOLS_IMAGE_ID_KEY: build_tools_image_id
        } if build_tools_image_id else None
        self.build_tools.deploy_stacks(GLOBALS_CLOUDFORMATION_DATA,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)

    def deploy_build_tools(self, build_tools_image_id=None):
        s3_template_source = BUILD_TOOLS_IMAGE_S3_SOURCE if build_tools_image_id else None
        param_overrides = {
            BUILD_TOOLS_IMAGE_ID_KEY: build_tools_image_id
        } if build_tools_image_id else None
        self.build_tools.deploy_stacks(BUILD_TOOLS_CLOUDFORMATION_DATA,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)

    #
    # def trigger_all_builds(self):
    #     for pipeline in AccountOrchestrator.BUILD_PIPELINES:
    #         self.build_tools.trigger_pipeline(pipeline)
    #     for pipeline in AccountOrchestrator.BUILD_PIPELINES:
    #         self.build_tools.wait_for_pipeline_completion(pipeline)
    #
    # def add_proof_account_to_shared_bucket_policy(self, snapshot_id):
    #     self.build_tools.deploy_stacks(AccountOrchestrator.BUILD_TOOLS_BUCKET_POLICY,
    #                                    s3_template_source=Cloudformation.PROOF_ACCOUNT_IMAGE_S3_SOURCE,
    #                                    overrides={
    #                                        SNAPSHOT_ID_OVERRIDE_KEY: snapshot_id,
    #                                        PROOF_ACCOUNT_ID_TO_ADD_KEY: self.proof_account.account_id
    #                                    })
    #
    # def create_new_snapshot(self):
    #     cmd = './snapshot-create --profile {} --snapshot {}'
    #     output = AccountOrchestrator.run(cmd.format(self.build_tools.profile, self.snapshot_filename))
    #     return AccountOrchestrator.parse_snapshot_id(output)
    #
    # def deploy_proof_account_github(self, snapshot_id):
    #     self.proof_account.deploy_stacks(AccountOrchestrator.PROOF_ACCOUNT_GITHUB_CLOUDFORMATION_DATA,
    #                                      s3_template_source=Cloudformation.PROOF_ACCOUNT_IMAGE_S3_SOURCE,
    #                                      overrides={
    #                                          SNAPSHOT_ID_OVERRIDE_KEY: snapshot_id,
    #                                          BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY: self.build_tools.account_id
    #                                      })
    #
    # def deploy_proof_account_stacks(self, snapshot_id):
    #     self.proof_account.deploy_stacks(AccountOrchestrator.PROOF_ACCOUNT_BATCH_CLOUDFORMATION_DATA,
    #                                      s3_template_source=Cloudformation.PROOF_ACCOUNT_IMAGE_S3_SOURCE,
    #                                      overrides={
    #                                          SNAPSHOT_ID_OVERRIDE_KEY: snapshot_id,
    #                                          BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY: self.build_tools.account_id
    #                                      })
    #
    # def get_current_snapshot_id(self):
    #     return self.proof_account.get_current_snapshot_id()
    #
    # def reload_all_snapshots(self, snapshot_id):
    #     if self.proof_account:
    #         self.proof_account.load_local_snapshot(snapshot_id)
    #     self.build_tools.load_local_snapshot(snapshot_id)
    #     if self.cloudfront_account:
    #         self.cloudfront_account.load_local_snapshot(snapshot_id)

