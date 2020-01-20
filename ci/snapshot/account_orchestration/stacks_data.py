from aws_managers.AwsAccount import TEMPLATE_NAME_KEY, PARAMETER_KEYS_KEY, PIPELINES_KEY

GLOBALS_CLOUDFORMATION_DATA = {
    "globals": {
        TEMPLATE_NAME_KEY: "build-globals.yaml",
        PARAMETER_KEYS_KEY: ["BatchRepositoryOwner",
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
                             'BatchRepositoryBranchName'],
        PIPELINES_KEY: ["Build-Batch-Pipeline"]
    },
    "build-viewer": {
        TEMPLATE_NAME_KEY: "build-viewer.yaml",
        PARAMETER_KEYS_KEY: ['S3BucketName',
                             'GitHubToken',
                             'ViewerRepositoryOwner',
                             'ViewerRepositoryName',
                             'ViewerRepositoryBranchName'],
        PIPELINES_KEY: ["Build-Viewer-Pipeline"]
    },
    "build-docker": {
        TEMPLATE_NAME_KEY: "build-docker.yaml",
        PARAMETER_KEYS_KEY: ['S3BucketName',
                             'GitHubToken',
                             'BatchRepositoryOwner',
                             'BatchRepositoryName',
                             'BatchRepositoryBranchName'],
        PIPELINES_KEY: ["Build-Docker-Pipeline"]
    },
    "build-cbmc-linux": {
        TEMPLATE_NAME_KEY: "build-cbmc-linux.yaml",
        PARAMETER_KEYS_KEY: ['S3BucketName',
                             'GitHubToken',
                             'CBMCBranchName'],
        PIPELINES_KEY: ["Build-CBMC-Linux-Pipeline"]
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