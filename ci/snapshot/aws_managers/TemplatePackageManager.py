import boto3

BUILD_TOOLS_IMAGE_S3_SOURCE = "BUILD_TOOLS_IMAGE_S3_SOURCE"
PROOF_ACCOUNT_IMAGE_S3_SOURCE = "PROOF_ACCOUNT_IMAGE_S3_SOURCE"
SNAPSHOT_ID_OVERRIDE_KEY = "SnapshotID"
BUILD_TOOLS_ACCOUNT_ID_OVERRIDE_KEY = "BuildToolsAccountId"
PROOF_ACCOUNT_ID_TO_ADD_KEY = "ProofAccountIdToAdd"
BUILD_TOOLS_IMAGE_ID_KEY = "build-tools-image-id"

class TemplatePackageManager:

    def __init__(self, profile, parameter_manager, shared_tool_bucket_name):
        self.session = boto3.session.Session(profile_name=profile)
        self.s3 = self.session.client("s3")
        self.parameter_manager = parameter_manager
        self.shared_tool_bucket_name = shared_tool_bucket_name
        self.ecr = self.session.client("ecr")

    def get_s3_url_for_template(self, template_name, s3_template_source, parameter_overrides=None):
        if s3_template_source == BUILD_TOOLS_IMAGE_S3_SOURCE:
            build_tools_image_id = parameter_overrides.get(BUILD_TOOLS_IMAGE_ID_KEY)
            if not build_tools_image_id:
                raise Exception("Cannot fetch build tool templates, no image id provided")
            return ("https://s3.amazonaws.com/{}/tool-account-images/image-{}/{}"
                         .format(self.shared_tool_bucket_name,
                                 build_tools_image_id,
                                 template_name))
        elif s3_template_source == PROOF_ACCOUNT_IMAGE_S3_SOURCE:

            snapshot_id = self.parameter_manager.get_value('SnapshotID', parameter_overrides=parameter_overrides)

            if not snapshot_id:
                raise Exception("Cannot fetch proof account templates from S3 with no snapshot ID")
            return ("https://s3.amazonaws.com/{}/snapshot/snapshot-{}/{}"
                             .format(self.shared_tool_bucket_name,
                                     snapshot_id,
                                     template_name))

    def take_most_recent(self, objects):
        return sorted(objects, key=lambda o: o["LastModified"], reverse=True)[0]

    def extract_snapshot_name_from_key(self, key_prefix, all_objects):
        matching_objs = filter(lambda o: key_prefix in o["Key"], all_objects)
        most_recent_key = self.take_most_recent(matching_objs)["Key"]
        return most_recent_key.replace(key_prefix, "")

    def get_docker_image_suffix_from_ecr(self):
        return self.ecr.list_images(repositoryName="cbmc")["imageIds"][0]["imageTag"].replace("ubuntu16-gcc-", "")

    def get_latest_proof_tool_package_filenames_s3(self):
        object_contents = self.s3.list_objects(Bucket=self.shared_tool_bucket_name, Prefix="package/")["Contents"]
        batch_pkg = self.extract_snapshot_name_from_key("package/batch/", object_contents)
        cbmc_pkg = self.extract_snapshot_name_from_key("package/cbmc/", object_contents)
        lambda_pkg = self.extract_snapshot_name_from_key("package/lambda/", object_contents)
        viewer_pkg = self.extract_snapshot_name_from_key("package/viewer/", object_contents)
        template_pkg = self.extract_snapshot_name_from_key("package/template/", object_contents)
        return {
            "batch": batch_pkg,
            "cbmc": cbmc_pkg,
            "lambda": lambda_pkg,
            "viewer": viewer_pkg,
            "templates": template_pkg,
            "docker": self.get_docker_image_suffix_from_ecr()
        }