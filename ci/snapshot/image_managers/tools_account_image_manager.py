import json
import os
import shutil
import tarfile
import time

import boto3

from aws_managers.CloudformationStacks import CloudformationStacks


class ToolsAccountImageManager:
    TOOL_ACCOUNT_IMAGES_BASE_DIR = "tool_account_images/"
    MISSING_PARAMETER_MSG = "Missing required parameter, {}"

    BATCH_REPOSITORY_KEY = "BatchCodeCommitBranchName"
    MANDATORY_PARAMS = ["BatchCodeCommitBranchName", "BatchRepositoryName", "BatchRepositoryOwner"]
    DEFAULT_TOOL_IMAGE_S3_PREFIX = "tool-account-images/"

    def __init__(self, tools_account_profile,
                 parameters=None,
                 image_filename=None,
                 tool_image_s3_prefix=None):
        self.session = boto3.session.Session(profile_name=tools_account_profile)
        self.s3 = self.session.client("s3")
        self.stacks = CloudformationStacks(self.session)
        self.bucket_name = self.stacks.get_output("S3BucketName")
        self.local_image_dir = None
        self.image_id = None
        self.local_template_tar_filename = None
        self.tool_image_s3_prefix = tool_image_s3_prefix if tool_image_s3_prefix \
            else ToolsAccountImageManager.DEFAULT_TOOL_IMAGE_S3_PREFIX

        if parameters and image_filename:
            raise Exception("Cannot provide both an image filename and parameters argument. Please choose one")
        self.parameters = parameters if parameters else self._get_parameters_from_file(image_filename)
        self._check_parameters()

    @staticmethod
    def _get_parameters_from_file(image_filename):
        with open(image_filename) as f:
            try:
                json_image = json.loads(f.read())
            except Exception:
                raise Exception("Failed to parse image file {}".format(image_filename))
            if "parameters" not in json_image.keys():
                raise Exception("No parameters in image file {}".format(image_filename))
            return json_image["parameters"]


    def _check_in_params(self, param):
        if param not in self.parameters.keys():
            raise Exception(ToolsAccountImageManager.MISSING_PARAMETER_MSG.format(param))

    def _check_parameters(self):
        [self._check_in_params(mandatory_param) for mandatory_param in ToolsAccountImageManager.MANDATORY_PARAMS]

    def _take_most_recent(self, objects):
        return sorted(objects, key=lambda o: o["LastModified"], reverse=True)[0]

    def _extract_image_name_from_key(self, key_prefix, all_objects):
        matching_objs = filter(lambda o: key_prefix in o["Key"], all_objects)
        most_recent_key = self._take_most_recent(matching_objs)["Key"]
        return most_recent_key.replace(key_prefix, "")

    def get_template_tar_filename_from_s3(self):
        object_contents = self.s3.list_objects(Bucket=self.bucket_name, Prefix="package/")["Contents"]
        return self._extract_image_name_from_key("package/template/", object_contents)

    @staticmethod
    def generate_image_id():
        return time.strftime("%Y%m%d-%H%M%S", time.gmtime())

    @staticmethod
    def create_local_image_directory(image_id):
        image_dir = ToolsAccountImageManager.TOOL_ACCOUNT_IMAGES_BASE_DIR \
                    + "image-{}".format(image_id)
        os.mkdir(image_dir)
        return image_dir


    def download_template_package_tar(self):
        if not self.image_id or not self.local_image_dir:
            raise Exception("Must have image ID and local image directory assigned "
                            "to download template package")
        template_filename = self.get_template_tar_filename_from_s3()
        local_filename = self.local_image_dir + "/" + template_filename
        key = "package/template/{}".format(template_filename)
        self.s3.download_file(Bucket=self.bucket_name,
                              Key=key, Filename=local_filename)
        return template_filename

    def upload_template_package(self):
        local_image_files = os.listdir(self.local_image_dir)
        for f in local_image_files:
            self.s3.upload_file(Bucket=self.bucket_name, Filename=self.local_image_dir + "/{}".format(f),
                                Key=self.tool_image_s3_prefix + "image-{}/{}".format(self.image_id, f))

    def extract_templates(self):
        current_dir = os.getcwd()
        os.chdir(self.local_image_dir)
        tar = tarfile.open(self.local_template_tar_filename)
        prefix = os.path.commonprefix(tar.getnames())
        tar.extractall()
        for yaml in os.listdir(prefix):
            shutil.copyfile(os.path.join(prefix, yaml), yaml)
        shutil.rmtree(prefix)
        os.chdir(current_dir)

    def generate_image_file(self):
        image_json = {
            "templates": self.local_template_tar_filename
        }
        image_file = self.local_image_dir + "/image-{}.json".format(self.image_id)
        with open(image_file, "w") as f:
            f.write(json.dumps(image_json))

    def generate_new_image_from_latest(self):
        self.image_id = ToolsAccountImageManager.generate_image_id()
        self.local_image_dir = ToolsAccountImageManager.create_local_image_directory(self.image_id)
        self.local_template_tar_filename = self.download_template_package_tar()
        self.extract_templates()
        self.generate_image_file()
        self.upload_template_package()
        return self.image_id
