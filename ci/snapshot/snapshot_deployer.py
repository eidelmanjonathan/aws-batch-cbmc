import time

from cloudformation import TEMPLATE_NAME_KEY
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

    def __init__(self, target_cloudformation, build_tools_cloudformation):
        self.target = target_cloudformation
        self.build_tools = build_tools_cloudformation

    def deploy_globals(self):
        self.build_tools.deploy_stacks(SnapshotDeployer.GLOBALS_CLOUDFORMATION_DATA)

    def deploy_build_tools(self):
        self.build_tools.deploy_stacks(SnapshotDeployer.BUILD_TOOLS_CLOUDFORMATION_DATA)

        for pipeline in SnapshotDeployer.BUILD_PIPELINES:
            self.build_tools.wait_for_pipeline_completion(pipeline)


build_tools_cf = Cloudformation("shared-tools",  "snapshot.json")

deployer = SnapshotDeployer(None, build_tools_cf)
deployer.deploy_globals()
deployer.deploy_build_tools()