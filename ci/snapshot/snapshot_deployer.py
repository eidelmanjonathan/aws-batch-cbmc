import subprocess
import time

from cloudformation import TEMPLATE_NAME_KEY, SNAPSHOT_ID_OVERRIDE_KEY, BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY, \
    PROOF_ACCOUNT_ID_TO_ADD_KEY, BUILD_TOOLS_IMAGE_ID_KEY
from cloudformation import PARAMETER_KEYS_KEY

from cloudformation import Cloudformation


class SnapshotDeployer:
    BUILD_PIPELINES = [
        "Build-CBMC-Linux-Pipeline",
        "Build-Docker-Pipeline",
        "Build-Viewer-Pipeline",
        "Build-Batch-Pipeline"
    ]
    GLOBALS_CLOUDFORMATION_DATA = {
        "globals": {
            TEMPLATE_NAME_KEY: "build-globals.yaml",
            PARAMETER_KEYS_KEY: ["GitHubRepository",
                                  "GitHubBranchName",
                                  "BatchRepositoryOwner",
                                  "BatchRepositoryName",
                                  "BatchRepositoryBranchName",
                                  "ViewerRepositoryOwner",
                                  "ViewerRepositoryName",
                                  "ViewerRepositoryBranchName",
                                  "S3BucketSuffix"]
        }
    }

    BUILD_TOOLS_CLOUDFORMATION_DATA = {
        "build-batch": {
            TEMPLATE_NAME_KEY: "build-batch.yaml",
            PARAMETER_KEYS_KEY: ['S3BucketName',
                                 'GitHubToken',
                                 'BatchRepositoryOwner',
                                 'BatchRepositoryName',
                                 'BatchRepositoryBranchName']
        },
        "build-viewer": {
            TEMPLATE_NAME_KEY: "build-viewer.yaml",
            PARAMETER_KEYS_KEY: ['S3BucketName',
                                 'GitHubToken',
                                 'ViewerRepositoryOwner',
                                 'ViewerRepositoryName',
                                 'ViewerRepositoryBranchName']
        },
        "build-docker": {
            TEMPLATE_NAME_KEY: "build-docker.yaml",
            PARAMETER_KEYS_KEY: ['S3BucketName',
                                 'GitHubToken',
                                 'BatchRepositoryOwner',
                                 'BatchRepositoryName',
                                 'BatchRepositoryBranchName']
        },
        "build-cbmc-linux": {
            TEMPLATE_NAME_KEY: "build-cbmc-linux.yaml",
            PARAMETER_KEYS_KEY: ['S3BucketName',
                                 'GitHubToken',
                                 'CBMCBranchName']
        }
    }

    BUILD_TOOLS_BUCKET_POLICY = {
        "bucket-policy": {
            TEMPLATE_NAME_KEY: "bucket-policy.yaml",
            PARAMETER_KEYS_KEY: ["S3BucketToolsName",
                                 "ProofAccountIds"]
        }
    }

    PROOF_ACCOUNT_GITHUB_CLOUDFORMATION_DATA = {
        "github": {
            TEMPLATE_NAME_KEY: "github.yaml",
            PARAMETER_KEYS_KEY: ['S3BucketToolsName',
                                 'BuildToolsAccountId',
                                 'ProjectName',
                                 'SnapshotID',
                                 'GitHubRepository',
                                 'GitHubBranchName']
        }
    }

    PROOF_ACCOUNT_BATCH_CLOUDFORMATION_DATA = {
        "cbmc-batch": {
            TEMPLATE_NAME_KEY: "cbmc.yaml",
            PARAMETER_KEYS_KEY: ['ImageTagSuffix',
                                 'BuildToolsAccountId']
        },
        "alarms-prod": {
            TEMPLATE_NAME_KEY: "alarms-prod.yaml",
            PARAMETER_KEYS_KEY: ['ProjectName',
                                 'SIMAddress',
                                 'NotificationAddress']
        },
        "canary": {
            TEMPLATE_NAME_KEY: "canary.yaml",
            PARAMETER_KEYS_KEY: ['GitHubRepository',
                                 'GitHubBranchName',
                                 'GitHubLambdaAPI']
        }

    }

    def __init__(self, build_tools_profile=None, proof_profile=None, snapshot_filename=None, parameters_filename=None):
        if not build_tools_profile:
            raise Exception("Cannot deploy stacks with no build tools profile")
        if not snapshot_filename:
            raise Exception("Cannot deploy stacks without snapshot JSON file")
        if proof_profile and not parameters_filename:
            raise Exception("Cannot deploy proof account without project parameters file")
        self.build_tools = Cloudformation(build_tools_profile, snapshot_filename)
        self.snapshot_filename = snapshot_filename

        if proof_profile:
            self.proof_account = Cloudformation(proof_profile,snapshot_filename,
                                                project_params_filename=parameters_filename,
                                                shared_tool_bucket_name=self.build_tools.shared_tool_bucket_name)

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
        s3_template_source = Cloudformation.BUILD_TOOLS_IMAGE_S3_SOURCE if build_tools_image_id else None
        param_overrides = {
            BUILD_TOOLS_IMAGE_ID_KEY: build_tools_image_id
        } if build_tools_image_id else None
        self.build_tools.deploy_stacks(SnapshotDeployer.GLOBALS_CLOUDFORMATION_DATA,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)

    def deploy_build_tools(self, build_tools_image_id=None):
        s3_template_source = Cloudformation.BUILD_TOOLS_IMAGE_S3_SOURCE if build_tools_image_id else None
        param_overrides = {
            BUILD_TOOLS_IMAGE_ID_KEY: build_tools_image_id
        } if build_tools_image_id else None
        self.build_tools.deploy_stacks(SnapshotDeployer.BUILD_TOOLS_CLOUDFORMATION_DATA,
                                       s3_template_source=s3_template_source,
                                       overrides=param_overrides)

        for pipeline in SnapshotDeployer.BUILD_PIPELINES:
            self.build_tools.wait_for_pipeline_completion(pipeline)
            self.build_tools.update_and_write_snapshot()

    def trigger_all_builds(self):
        for pipeline in SnapshotDeployer.BUILD_PIPELINES:
            self.build_tools.trigger_pipeline(pipeline)
        for pipeline in SnapshotDeployer.BUILD_PIPELINES:
            self.build_tools.wait_for_pipeline_completion(pipeline)

    def add_proof_account_to_shared_bucket_policy(self, snapshot_id):
        self.build_tools.deploy_stacks(SnapshotDeployer.BUILD_TOOLS_BUCKET_POLICY,
                                       s3_template_source=Cloudformation.PROOF_ACCOUNT_IMAGE_S3_SOURCE,
                                       overrides={
                                           SNAPSHOT_ID_OVERRIDE_KEY: snapshot_id,
                                           PROOF_ACCOUNT_ID_TO_ADD_KEY: self.proof_account.account_id
                                       })

    def create_new_snapshot(self):
        cmd = './snapshot-create --profile {} --snapshot {}'
        output = SnapshotDeployer.run(cmd.format(self.build_tools.profile, self.snapshot_filename))
        return SnapshotDeployer.parse_snapshot_id(output)

    def deploy_proof_account_github(self, snapshot_id):
        self.proof_account.deploy_stacks(SnapshotDeployer.PROOF_ACCOUNT_GITHUB_CLOUDFORMATION_DATA,
                                         s3_template_source=Cloudformation.PROOF_ACCOUNT_IMAGE_S3_SOURCE,
                                         overrides={
                                             SNAPSHOT_ID_OVERRIDE_KEY: snapshot_id,
                                             BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY: self.build_tools.account_id
                                         })

    def deploy_proof_account_stacks(self, snapshot_id):
        self.proof_account.deploy_stacks(SnapshotDeployer.PROOF_ACCOUNT_BATCH_CLOUDFORMATION_DATA,
                                         s3_template_source=Cloudformation.PROOF_ACCOUNT_IMAGE_S3_SOURCE,
                                         overrides={
                                             SNAPSHOT_ID_OVERRIDE_KEY: snapshot_id,
                                             BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY: self.build_tools.account_id
                                         })

    def get_current_snapshot_id(self):
        return self.proof_account.get_current_snapshot_id()

    def reload_all_snapshots(self, snapshot_id):
        if self.proof_account:
            self.proof_account.load_local_snapshot(snapshot_id)
        self.build_tools.load_local_snapshot(snapshot_id)
        if self.cloudfront_account:
            self.cloudfront_account.load_local_snapshot(snapshot_id)