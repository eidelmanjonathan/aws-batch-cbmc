import os
import pathlib
import shutil
import tarfile
import time

import boto3
import botocore_amazon.monkeypatch


class ImageManager:

    def __init__(self, profile,
                 base_image_directory=None,
                 bucket_name=None,
                 packages_required=None):
        self.session = boto3.session.Session(profile_name=profile)
        self.s3 = self.session.client("s3")
        self.base_image_directory = base_image_directory
        self.packages_required = packages_required
        self.bucket_name = bucket_name


    @staticmethod
    def generate_image_id():
        return time.strftime("%Y%m%d-%H%M%S", time.gmtime())

    def create_local_image_directory(self, image_id):
        image_dir = self.base_image_directory \
                    + "/image-{}".format(image_id)
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

    def generate_new_image_from_latest(self):
        self.image_id = self.generate_image_id()
        self.local_image_dir = self.create_local_image_directory(self.image_id)
        for package in self.packages_required.keys():
            downloaded_pkg = self.download_package_tar(package)
            if self.packages_required[package]["extract"]:
                self.extract_package(downloaded_pkg)
        # self.generate_image_file()
        # self.upload_template_package()
        return self.image_id

# i = ImageManager("shared-tools",
#                  base_image_directory="tool-account-images",
#                  bucket_name="677072028621-us-west-2-cbmc",
#                  packages_required={"template": {"extract": True}, "cbmc": {"extract": False}})
# i.generate_new_image_from_latest()