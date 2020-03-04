import logging
from functools import reduce

from deployment_tools.account_orchestration.stacks_data import GLOBALS_CLOUDFORMATION_DATA, BUILD_TOOLS_CLOUDFORMATION_DATA, \
    PROOF_ACCOUNT_GITHUB_CLOUDFORMATION_DATA, BUILD_TOOLS_BUCKET_POLICY, PROOF_ACCOUNT_BATCH_CLOUDFORMATION_DATA, \
    BUILD_TOOLS_PACKAGES, PROOF_ACCOUNT_PACKAGES, BUILD_TOOLS_ALARMS
from deployment_tools.account_orchestration.AwsAccount import AwsAccount
from deployment_tools.aws_managers.key_constants import BUILD_TOOLS_SNAPSHOT_ID_KEY, \
    BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY, PROOF_ACCOUNT_ID_TO_ADD_KEY, PIPELINES_KEY, SNAPSHOT_ID_OVERRIDE_KEY
from deployment_tools.snapshot_managers.SnapshotManager import PROOF_SNAPSHOT_PREFIX, TOOLS_SNAPSHOT_PREFIX, SnapshotManager


BUILD_TOOLS_IMAGE_S3_SOURCE = "BUILD_TOOLS_IMAGE_S3_SOURCE"
PROOF_ACCOUNT_IMAGE_S3_SOURCE = "PROOF_ACCOUNT_IMAGE_S3_SOURCE"
BOOTSTRAP_CONST = "BOOTSTRAP"

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
        self.logger = logging.getLogger("AccountOrchestrator")
        self.logger.setLevel(logging.INFO)
        self.build_tools = AwsAccount(build_tools_account_profile,
                                      parameters_file=tools_account_parameters_file,
                                      packages_required=BUILD_TOOLS_PACKAGES,
                                      snapshot_s3_prefix=TOOLS_SNAPSHOT_PREFIX)

        if proof_account_profile:
            self.proof_account_write_access_snapshot = SnapshotManager(self.build_tools.session,
                                                                       bucket_name=self.build_tools.shared_tool_bucket_name,
                                                                       packages_required=PROOF_ACCOUNT_PACKAGES,
                                                                       tool_image_s3_prefix=PROOF_SNAPSHOT_PREFIX)
            self.proof_account = AwsAccount(profile=proof_account_profile,
                                            shared_tool_bucket_name=self.build_tools.shared_tool_bucket_name,
                                            parameters_file=proof_account_parameters_file,
                                            packages_required=PROOF_ACCOUNT_PACKAGES,
                                            snapshot_s3_prefix=PROOF_SNAPSHOT_PREFIX)

    @staticmethod
    def _parse_snapshot_id(output):
        sid = None
        for line in output.split('\n'):
            if line.startswith('Updating SnapshotID to '):
                sid = line[len('Updating SnapshotID to '):]
                break
        if sid is None:
            raise UserWarning("snapshot id is none")
        return sid

    def deploy_globals_stack(self, deploy_from_local_template=False):
        """
        Deploy the 'globals' stack into the build tools account which has the shared S3 bucket
        and other global resources
        :param deploy_from_local_template: Boolean - if true, we deploy from local templates instead of S3. Used to
            bootstrap new tools accounts
        """
        # TODO: Should this stack be called globals?
        s3_template_source = BUILD_TOOLS_IMAGE_S3_SOURCE if not deploy_from_local_template else None
        param_overrides = {
            BUILD_TOOLS_SNAPSHOT_ID_KEY: self.build_tools.snapshot_id,
        }
        if deploy_from_local_template:
            param_overrides[SNAPSHOT_ID_OVERRIDE_KEY] = BOOTSTRAP_CONST
        self.logger.info("Deploying globals stack in build tools account {}".format(self.build_tools.account_id))
        self.build_tools.deploy_stacks(GLOBALS_CLOUDFORMATION_DATA,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)

    def deploy_build_tools(self, deploy_from_local_template=False):
        """
        Deploy the 'build tools' stacks which are responsible for the various pipelines that build CBMC, CBMC-batch etc...
        :param deploy_from_local_template: deploy_from_local_template: Boolean - if true, we deploy from local templates instead of S3. Used to
            bootstrap new tools accounts
        """
        s3_template_source = BUILD_TOOLS_IMAGE_S3_SOURCE if not deploy_from_local_template else None
        param_overrides = {
            BUILD_TOOLS_SNAPSHOT_ID_KEY: self.build_tools.snapshot_id
        }
        if deploy_from_local_template:
            param_overrides[SNAPSHOT_ID_OVERRIDE_KEY] = BOOTSTRAP_CONST
        self.logger.info("Deploying build tools stack in build tools account {}".format(self.build_tools.account_id))
        self.build_tools.deploy_stacks(BUILD_TOOLS_CLOUDFORMATION_DATA,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)

    def deploy_build_alarms(self, deploy_from_local_template=False):
        """
        Deploy build tools account alarms stacks which send out alarms for build failures
        :param deploy_from_local_template: deploy_from_local_template: Boolean - if true, we deploy from local templates instead of S3. Used to
            bootstrap new tools accounts
        """
        s3_template_source = BUILD_TOOLS_IMAGE_S3_SOURCE if not deploy_from_local_template else None
        param_overrides = {
            BUILD_TOOLS_SNAPSHOT_ID_KEY: self.build_tools.snapshot_id,
        }
        if deploy_from_local_template:
            param_overrides[SNAPSHOT_ID_OVERRIDE_KEY] = BOOTSTRAP_CONST
        self.logger.info("Deploying build alarms stack in build tools account {}".format(self.build_tools.account_id))
        self.build_tools.deploy_stacks(BUILD_TOOLS_ALARMS,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)
    #
    def add_proof_account_to_shared_bucket_policy(self):
        """
        Gives read access to the shared S3 bucket in the tools account to the proof account
        """
        s3_template_source = BUILD_TOOLS_IMAGE_S3_SOURCE
        param_overrides = {
            BUILD_TOOLS_SNAPSHOT_ID_KEY: self.build_tools.snapshot_id,
            PROOF_ACCOUNT_ID_TO_ADD_KEY: self.proof_account.account_id
        }
        self.logger.info("Deploying bucket policy stack to proof account {} in tools account {}".format(self.proof_account.account_id,
                                                                                                        self.build_tools.account_id))
        self.build_tools.deploy_stacks(BUILD_TOOLS_BUCKET_POLICY,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)

    #
    def deploy_proof_account_github(self):
        """
        Deploys the 'github' stack in the proof account
        """
        self.logger.info("Deploying github stack in proof account {}".format(self.proof_account.account_id))
        self.proof_account.deploy_stacks(PROOF_ACCOUNT_GITHUB_CLOUDFORMATION_DATA,
                                         s3_template_source=PROOF_ACCOUNT_IMAGE_S3_SOURCE,
                                         overrides={
                                             BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY: self.build_tools.account_id
                                         })

    def use_existing_proof_account_snapshot(self, snapshot_id):
        """
        Downloads and sets a proof account snapshot
        :param snapshot_id: the snapshot ID that we hope to deploy
        """
        self.proof_account.download_and_set_snapshot(snapshot_id)

    def use_existing_tool_account_snapshot(self, snapshot_id):
        """
        Downloads and sets a tool account snapshot
        :param snapshot_id: the snapshot ID that we hope to deploy
        """
        self.build_tools.download_and_set_snapshot(snapshot_id)

    def generate_new_tool_account_snapshot(self):
        """
        Generates a new tool account snapshot
        :return: string-  the newly generated snapshot ID
        """
        snapshot_id = self.build_tools.snapshot_manager.generate_new_snapshot_from_latest()
        self.build_tools.download_and_set_snapshot(snapshot_id)
        return snapshot_id

    def generate_new_proof_account_snapshot(self, overrides=None):
        """
        Generates a new proof account snapshot
        :param overrides: dictionary - has any packages that we want to explicitely use instead of the most recent
        :return: string - newly generated snapshot ID
        """
        snapshot_id = self.proof_account_write_access_snapshot.generate_new_snapshot_from_latest(overrides=overrides)
        self.proof_account.download_and_set_snapshot(snapshot_id)
        return snapshot_id

    def deploy_proof_account_stacks(self):
        """
        Deploys cbmc-batch, alarms, and canary stacks in parallel
        """
        self.logger.info("Deploying cbmc-batch, alarms, and canary stack in proof account {}".format(self.proof_account.account_id))
        self.proof_account.deploy_stacks(PROOF_ACCOUNT_BATCH_CLOUDFORMATION_DATA,
                                         s3_template_source=PROOF_ACCOUNT_IMAGE_S3_SOURCE,
                                         overrides={
                                             BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY: self.build_tools.account_id
                                         })

    def get_account_snapshot_id(self, source_profile):
        """
        Returns the current snapshot ID of a particular profile
        :param source_profile: string - aws profile name from ~/.aws config file
        :return: snapshot ID running in givne account
        """
        return AwsAccount(profile=source_profile,
                   shared_tool_bucket_name=self.build_tools.shared_tool_bucket_name)\
            .get_current_snapshot_id()

    def set_proof_account_environment_variables(self):
        """
        Sets the proof account environment variables in lambda and codebuild to match whatever the ParameterManager
        says.
        """
        is_ci_operating = True # Is this ever false?
        update_github = self.proof_account.get_update_github_status()
        self.proof_account.set_ci_operating(is_ci_operating)
        self.proof_account.set_update_github(update_github)

    def trigger_and_wait_for_build_pipelines(self):
        """
        Triggers all build tools pipelines and waits for all of them to complete
        """
        all_pipelines = map(lambda k: BUILD_TOOLS_CLOUDFORMATION_DATA[k][PIPELINES_KEY],
                            BUILD_TOOLS_CLOUDFORMATION_DATA.keys())
        all_pipelines = reduce(lambda l1, l2: l1 + l2, all_pipelines)
        self.build_tools.trigger_and_wait_for_pipelines(all_pipelines)
