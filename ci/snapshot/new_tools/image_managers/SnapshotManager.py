import json
import os
import shutil
import tarfile
import time

import boto3

PROOF_SNAPSHOT_PREFIX = "snapshot/"
TOOLS_SNAPSHOT_PREFIX = "tool-account-images/"

class SnapshotManager:

    def __init__(self, profile,
                 bucket_name=None,
                 packages_required=None,
                 tool_image_s3_prefix=None):
        self.session = boto3.session.Session(profile_name=profile)
        self.s3 = self.session.client("s3")
        self.base_image_directory = tool_image_s3_prefix
        self.packages_required = packages_required
        self.bucket_name = bucket_name
        self.tool_image_s3_prefix = tool_image_s3_prefix


    @staticmethod
    def generate_image_id():
        return time.strftime("%Y%m%d-%H%M%S", time.gmtime())

    def create_local_image_directory(self, image_id):
        image_dir = self.base_image_directory \
                    + "/snapshot-{}".format(image_id)
        os.mkdir(image_dir)
        return image_dir

    def _take_most_recent(self, objects):
        return sorted(objects, key=lambda o: o["LastModified"], reverse=True)[0]

    def _extract_image_name_from_key(self, key_prefix, all_objects):
        matching_objs = filter(lambda o: key_prefix in o["Key"], all_objects)
        most_recent_key = self._take_most_recent(matching_objs)["Key"]
        return most_recent_key.replace(key_prefix, "")

    def _get_tar_filename_from_s3(self, package):
        object_contents = self.s3.list_objects(Bucket=self.bucket_name, Prefix="package/")["Contents"]
        return self._extract_image_name_from_key("package/{}/".format(package), object_contents)


    def download_package_tar(self, package):
        if not self.image_id or not self.local_image_dir:
            raise Exception("Must have image ID and local image directory assigned "
                            "to download template package")
        package_filename = self._get_tar_filename_from_s3(package)
        local_filename = self.local_image_dir + "/" + package_filename
        key = "package/{}/{}".format(package, package_filename)
        self.s3.download_file(Bucket=self.bucket_name,
                              Key=key, Filename=local_filename)
        return package_filename

    def extract_package(self, package_filename):
        current_dir = os.getcwd()
        os.chdir(self.local_image_dir)
        tar = tarfile.open(package_filename)
        prefix = os.path.commonprefix(tar.getnames())
        tar.extractall()
        for yaml in os.listdir(prefix):
            shutil.copyfile(os.path.join(prefix, yaml), yaml)
        shutil.rmtree(prefix)
        os.chdir(current_dir)

    def upload_template_package(self, upload_profile = None):
        local_image_files = os.listdir(self.local_image_dir)
        if upload_profile:
            upload_session = boto3.session.Session(profile_name=upload_profile)
            upload_s3 = upload_session.client("s3")
        else:
            upload_s3 = self.s3
        for f in local_image_files:
            if "lambda" in f and "zip" in f:
                key = self.tool_image_s3_prefix + "snapshot-{}/{}".format(self.image_id, "lambda.zip")
            else:
                key = self.tool_image_s3_prefix + "snapshot-{}/{}".format(self.image_id, f)
            upload_s3.upload_file(Bucket=self.bucket_name, Filename=self.local_image_dir + "/{}".format(f),
                                Key=key)

    def generate_image_file(self, local_template_tar_filename):
        image_json = {
            "templates": local_template_tar_filename
        }
        image_file = self.local_image_dir + "/snapshot-{}.json".format(self.image_id)
        with open(image_file, "w") as f:
            f.write(json.dumps(image_json))

    def generate_new_image_from_latest(self, upload_profile = None):
        self.image_id = self.generate_image_id()
        self.local_image_dir = self.create_local_image_directory(self.image_id)
        for package in self.packages_required.keys():
            downloaded_pkg = self.download_package_tar(package)
            if self.packages_required[package]["extract"]:
                self.extract_package(downloaded_pkg)
        self.generate_image_file(self.local_image_dir + "/snapshot-{}.json".format(self.image_id))
        self.upload_template_package(upload_profile = upload_profile)
        return self.image_id

    def download_snapshot(self, snapshot_id):
        key = self.tool_image_s3_prefix + "snapshot-{}/snapshot-{}.json" .format(snapshot_id, snapshot_id)
        self.s3.download_file(Bucket=self.bucket_name,
                              Key=key,
                              Filename="snapshot_tmp.json")
        with open("snapshot_tmp.json") as f:
            return json.loads(f.read())
