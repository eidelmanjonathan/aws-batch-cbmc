from functools import reduce

from new_tools.account_orchestration.stacks_data import GLOBALS_CLOUDFORMATION_DATA, BUILD_TOOLS_CLOUDFORMATION_DATA, \
    PROOF_ACCOUNT_GITHUB_CLOUDFORMATION_DATA, BUILD_TOOLS_BUCKET_POLICY, PROOF_ACCOUNT_BATCH_CLOUDFORMATION_DATA, \
    BUILD_TOOLS_PACKAGES, PROOF_ACCOUNT_PACKAGES, BUILD_TOOLS_ALARMS, CLOUDFRONT_CLOUDFORMATION_DATA
from new_tools.account_orchestration.AwsAccount import AwsAccount
from new_tools.aws_managers.TemplatePackageManager import BUILD_TOOLS_IMAGE_S3_SOURCE, PROOF_ACCOUNT_IMAGE_S3_SOURCE
from new_tools.aws_managers.key_constants import BUILD_TOOLS_IMAGE_ID_KEY, \
    BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY, PROOF_ACCOUNT_ID_TO_ADD_KEY, PIPELINES_KEY, S3_BUCKET_PROOFS_OVERRIDE_KEY, \
    CLOUDFRONT_URL_KEY
from new_tools.image_managers.SnapshotManager import PROOF_SNAPSHOT_PREFIX, TOOLS_SNAPSHOT_PREFIX, SnapshotManager


class AccountOrchestrator:
    """
    This class exposes methods to generate new snapshots of Padstone CI AWS accounts, as well as deploying the various
    kinds of stacks necessary to run CI.
    """

    def __init__(self, build_tools_profile=None,
                 proof_profile=None,
                 cloudfront_profile=None,
                 tools_account_parameters_file=None,
                 proof_account_parameters_file=None):


        self.build_tools = AwsAccount(build_tools_profile,
                                      parameters_file=tools_account_parameters_file,
                                      packages_required=BUILD_TOOLS_PACKAGES,
                                      snapshot_s3_prefix=TOOLS_SNAPSHOT_PREFIX)

        if proof_profile:
            self.proof_account_write_access_snapshot = SnapshotManager(build_tools_profile,
                                                             bucket_name=self.build_tools.shared_tool_bucket_name,
                                                             packages_required=PROOF_ACCOUNT_PACKAGES,
                                                             tool_image_s3_prefix=PROOF_SNAPSHOT_PREFIX)
            self.proof_account = AwsAccount(profile=proof_profile,
                                            shared_tool_bucket_name=self.build_tools.shared_tool_bucket_name,
                                            parameters_file=proof_account_parameters_file,
                                            packages_required=PROOF_ACCOUNT_PACKAGES,
                                            snapshot_s3_prefix=PROOF_SNAPSHOT_PREFIX)

        if cloudfront_profile:
            self.cloudfront_account = AwsAccount(profile=cloudfront_profile,
                                                 shared_tool_bucket_name=self.build_tools.shared_tool_bucket_name,
                                                 parameters_file=proof_account_parameters_file,
                                                 packages_required=PROOF_ACCOUNT_PACKAGES,
                                                 snapshot_s3_prefix=PROOF_SNAPSHOT_PREFIX)

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

    def deploy_globals(self, deploy_from_local_template=False):
        # If we are deploying a particular image
        s3_template_source = BUILD_TOOLS_IMAGE_S3_SOURCE if not deploy_from_local_template else None
        param_overrides = {
            BUILD_TOOLS_IMAGE_ID_KEY: self.build_tools.snapshot_id
        }
        self.build_tools.deploy_stacks(GLOBALS_CLOUDFORMATION_DATA,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)

    def deploy_build_tools(self, deploy_from_local_template=False):
        s3_template_source = BUILD_TOOLS_IMAGE_S3_SOURCE if not deploy_from_local_template else None
        param_overrides = {
            BUILD_TOOLS_IMAGE_ID_KEY: self.build_tools.snapshot_id
        }
        self.build_tools.deploy_stacks(BUILD_TOOLS_CLOUDFORMATION_DATA,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)

    def deploy_build_alarms(self, deploy_from_local_template=False):
        s3_template_source = BUILD_TOOLS_IMAGE_S3_SOURCE if not deploy_from_local_template else None
        param_overrides = {
            BUILD_TOOLS_IMAGE_ID_KEY: self.build_tools.snapshot_id
        }
        self.build_tools.deploy_stacks(BUILD_TOOLS_ALARMS,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)
    #
    def add_proof_account_to_shared_bucket_policy(self):
        s3_template_source = BUILD_TOOLS_IMAGE_S3_SOURCE
        param_overrides = {
            BUILD_TOOLS_IMAGE_ID_KEY: self.build_tools.snapshot_id,
            PROOF_ACCOUNT_ID_TO_ADD_KEY: self.proof_account.account_id
        }
        self.build_tools.deploy_stacks(BUILD_TOOLS_BUCKET_POLICY,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)

    #
    def deploy_proof_account_github(self, cloudfront_url=None):
        self.proof_account.deploy_stacks(PROOF_ACCOUNT_GITHUB_CLOUDFORMATION_DATA,
                                         s3_template_source=PROOF_ACCOUNT_IMAGE_S3_SOURCE,
                                         overrides={
                                             BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY: self.build_tools.account_id,
                                             CLOUDFRONT_URL_KEY: cloudfront_url if cloudfront_url else ""
                                         })

    def use_existing_proof_account_snapshot(self, snapshot_id):
        self.proof_account.download_snapshot(snapshot_id)
        if self.cloudfront_account:
            self.cloudfront_account.download_snapshot(snapshot_id)

    def use_existing_tool_account_snapshot(self, snapshot_id):
        self.build_tools.download_snapshot(snapshot_id)

    def generate_new_tool_account_snapshot(self):
        snapshot_id = self.build_tools.snapshot_manager.generate_new_image_from_latest()
        self.build_tools.download_snapshot(snapshot_id)
        return snapshot_id

    def generate_new_proof_account_snapshot(self, overrides=None):
        snapshot_id = self.proof_account_write_access_snapshot.generate_new_image_from_latest(overrides=overrides)
        self.proof_account.download_snapshot(snapshot_id)
        return snapshot_id

    def deploy_proof_account_stacks(self):
        self.proof_account.deploy_stacks(PROOF_ACCOUNT_BATCH_CLOUDFORMATION_DATA,
                                         s3_template_source=PROOF_ACCOUNT_IMAGE_S3_SOURCE,
                                         overrides={
                                             BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY: self.build_tools.account_id
                                         })

    def deploy_cloudfront_stacks(self):
        self.cloudfront_account.deploy_stacks(CLOUDFRONT_CLOUDFORMATION_DATA,
                                              s3_template_source=PROOF_ACCOUNT_IMAGE_S3_SOURCE,
                                              overrides={
                                                  BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY: self.build_tools.account_id,
                                                  S3_BUCKET_PROOFS_OVERRIDE_KEY: self.proof_account.get_s3_proof_bucket_name()
                                              })
        self.cloudfront_account.get_parameter("CloudfrontUrl")
        self.deploy_proof_account_github(cloudfront_url=cloudfront_url)

    def get_account_snapshot_id(self, source_profile):
        return AwsAccount(profile=source_profile,
                   shared_tool_bucket_name=self.build_tools.shared_tool_bucket_name)\
            .get_current_snapshot_id()

    def set_proof_account_environment_variables(self):
        is_ci_operating = True # Is this ever false?
        update_github = self.proof_account.get_update_github_status()
        self.proof_account.set_ci_operating(is_ci_operating)
        self.proof_account.set_update_github(update_github)

    def trigger_build_pipelines(self):
        all_pipelines = map(lambda k: BUILD_TOOLS_CLOUDFORMATION_DATA[k][PIPELINES_KEY],
                            BUILD_TOOLS_CLOUDFORMATION_DATA.keys())
        all_pipelines = reduce(lambda l1, l2: l1 + l2, all_pipelines)
        self.build_tools.trigger_pipelines(all_pipelines)

    def wait_for_pipelines(self):
        all_pipelines = map(lambda k: BUILD_TOOLS_CLOUDFORMATION_DATA[k][PIPELINES_KEY],
                            BUILD_TOOLS_CLOUDFORMATION_DATA.keys())
        all_pipelines = reduce(lambda l1, l2: l1 + l2, all_pipelines)
        self.build_tools._wait_for_pipelines(all_pipelines)