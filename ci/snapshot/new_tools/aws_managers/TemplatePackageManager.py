import boto3

BUILD_TOOLS_IMAGE_S3_SOURCE = "BUILD_TOOLS_IMAGE_S3_SOURCE"
PROOF_ACCOUNT_IMAGE_S3_SOURCE = "PROOF_ACCOUNT_IMAGE_S3_SOURCE"

class TemplatePackageManager:

    def __init__(self, profile, parameter_manager, shared_tool_bucket_name, snapshot_id=None, s3_snapshot_prefix = None):
        self.session = boto3.session.Session(profile_name=profile)
        self.s3 = self.session.client("s3")
        self.parameter_manager = parameter_manager
        self.shared_tool_bucket_name = shared_tool_bucket_name
        self.s3_snapshot_prefix = s3_snapshot_prefix
        self.ecr = self.session.client("ecr")
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