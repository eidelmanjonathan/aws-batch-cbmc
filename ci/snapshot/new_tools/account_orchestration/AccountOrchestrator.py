from functools import reduce

from new_tools.account_orchestration.stacks_data import GLOBALS_CLOUDFORMATION_DATA, BUILD_TOOLS_CLOUDFORMATION_DATA, \
    PROOF_ACCOUNT_GITHUB_CLOUDFORMATION_DATA, BUILD_TOOLS_BUCKET_POLICY, PROOF_ACCOUNT_BATCH_CLOUDFORMATION_DATA, \
    BUILD_TOOLS_PACKAGES, PROOF_ACCOUNT_PACKAGES, BUILD_TOOLS_ALARMS
from new_tools.account_orchestration.AwsAccount import AwsAccount
from new_tools.aws_managers.TemplatePackageManager import BUILD_TOOLS_IMAGE_S3_SOURCE, PROOF_ACCOUNT_IMAGE_S3_SOURCE
from new_tools.aws_managers.key_constants import BUILD_TOOLS_IMAGE_ID_KEY, \
    BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY, PROOF_ACCOUNT_ID_TO_ADD_KEY, PIPELINES_KEY
from new_tools.image_managers.SnapshotManager import PROOF_SNAPSHOT_PREFIX, TOOLS_SNAPSHOT_PREFIX, SnapshotManager


class AccountOrchestrator:
    """
    This class exposes methods to generate new snapshots of Padstone CI AWS accounts, as well as deploying the various
    kinds of stacks necessary to run CI.

    """
    def __init__(self, build_tools_account_profile=None,
                 proof_account_profile=None,
                 tools_account_parameters_file=None,
                 proof_account_parameters_file=None):
        """

        :param build_tools_account_profile: string - name of your aws tools profile from your aws config file
        :param proof_account_profile: string - name of your aws proof profile from your aws config file
        :param tools_account_parameters_file: string - filename of a json file giving parameters for the tool account
        :param proof_account_parameters_file: string - filename of a json file giving parameters for the proof account
        """

        self.build_tools = AwsAccount(build_tools_account_profile,
                                      parameters_file=tools_account_parameters_file,
                                      packages_required=BUILD_TOOLS_PACKAGES,
                                      snapshot_s3_prefix=TOOLS_SNAPSHOT_PREFIX)

        if proof_account_profile:
            self.proof_account_write_access_snapshot = SnapshotManager(build_tools_account_profile,
                                                                       bucket_name=self.build_tools.shared_tool_bucket_name,
                                                                       packages_required=PROOF_ACCOUNT_PACKAGES,
                                                                       tool_image_s3_prefix=PROOF_SNAPSHOT_PREFIX)
            self.proof_account = AwsAccount(profile=proof_account_profile,
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

    def deploy_globals_stack(self, deploy_from_local_template=False):
        # TODO: Should this stack be called globals?
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
    def deploy_proof_account_github(self):
        self.proof_account.deploy_stacks(PROOF_ACCOUNT_GITHUB_CLOUDFORMATION_DATA,
                                         s3_template_source=PROOF_ACCOUNT_IMAGE_S3_SOURCE,
                                         overrides={
                                             BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY: self.build_tools.account_id
                                         })

    def use_existing_proof_account_snapshot(self, snapshot_id):
        self.proof_account.download_and_set_snapshot(snapshot_id)

    def use_existing_tool_account_snapshot(self, snapshot_id):
        self.build_tools.download_and_set_snapshot(snapshot_id)

    def generate_new_tool_account_snapshot(self):
        snapshot_id = self.build_tools.snapshot_manager.generate_new_snapshot_from_latest()
        self.build_tools.download_and_set_snapshot(snapshot_id)
        return snapshot_id

    def generate_new_proof_account_snapshot(self, overrides=None):
        snapshot_id = self.proof_account_write_access_snapshot.generate_new_snapshot_from_latest(overrides=overrides)
        self.proof_account.download_and_set_snapshot(snapshot_id)
        return snapshot_id

    def deploy_proof_account_stacks(self):
        self.proof_account.deploy_stacks(PROOF_ACCOUNT_BATCH_CLOUDFORMATION_DATA,
                                         s3_template_source=PROOF_ACCOUNT_IMAGE_S3_SOURCE,
                                         overrides={
                                             BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY: self.build_tools.account_id
                                         })

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
        self.build_tools.trigger_and_wait_for_pipelines(all_pipelines)
