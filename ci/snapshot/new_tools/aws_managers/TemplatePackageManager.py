import boto3

BUILD_TOOLS_IMAGE_S3_SOURCE = "BUILD_TOOLS_IMAGE_S3_SOURCE"
PROOF_ACCOUNT_IMAGE_S3_SOURCE = "PROOF_ACCOUNT_IMAGE_S3_SOURCE"

class TemplatePackageManager:
    """
    Goes to S3 to find cloudformation templates
    """

    def __init__(self, profile, parameter_manager, shared_tool_bucket_name, snapshot_id=None, s3_snapshot_prefix = None):
        self.session = boto3.session.Session(profile_name=profile)
        self.s3 = self.session.client("s3")
        self.parameter_manager = parameter_manager
        self.shared_tool_bucket_name = shared_tool_bucket_name
        self.s3_snapshot_prefix = s3_snapshot_prefix
        self.snapshot_id = snapshot_id

    def get_s3_url_for_template(self, template_name, parameter_overrides=None):
        snapshot_id = self.snapshot_id if self.snapshot_id else self.parameter_manager\
            .get_value('SnapshotID', parameter_overrides=parameter_overrides)

        if not snapshot_id:
            raise Exception("Cannot fetch account templates from S3 with no snapshot ID")
        return ("https://s3.amazonaws.com/{}/{}snapshot-{}/{}"
                .format(self.shared_tool_bucket_name, self.s3_snapshot_prefix,
                        snapshot_id,
                        template_name))
