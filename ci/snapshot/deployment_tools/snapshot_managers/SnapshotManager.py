import json
import os
import shutil
import tarfile
import time

import boto3

from deployment_tools.utilities.utilities import remove_substring

PROOF_SNAPSHOT_PREFIX = "snapshot/"
S3_PACKAGE_KEY_PREFIX = "package/"
TOOLS_SNAPSHOT_PREFIX = "tool-account-images/"

CONTENTS_KEY = "Contents"
EXTRACT_KEY = "extract"
IMAGE_IDS_KEY = "imageIds"
IMAGE_TAG_KEY = "imageTag"
KEY_CONST = "Key"
LAST_MODIFIED_KEY = "LastModified"
SNAPSHOT_CONST = "snapshot"

CBMC_BATCH_CONST = "cbmc-batch"
CBMC_REPO_NAME = "cbmc"
LAMBDA_CONST = "lambda"
LAMBDA_ZIP_FILE = "lambda.zip"
UBUNTU_IMAGE_PREFIX = "ubuntu16-gcc-"

CBMC_BATCH_TAR= "cbmc-batch.tar.gz"
CBMC_VIEWER_CONST = "cbmc-viewer"
CBMC_VIEWER_TAR = "cbmc-viewer.tar.gz"
SNAPSHOT_TMP_FILENAME = "snapshot_tmp.json"

class SnapshotManager:
    """
    This is the class that manages any kind of snapshot of an account and handles saving those snapshots
    to/downloading them from S3, assigning IDs etc..
    """

    def __init__(self, session,
                 bucket_name=None,
                 packages_required=None,
                 tool_image_s3_prefix=None):
        self.session = session
        self.s3 = self.session.client("s3")
        self.ecr = self.session.client("ecr")
        self.base_snapshot_directory = tool_image_s3_prefix
        self.packages_required = packages_required
        self.bucket_name = bucket_name
        self.tool_snapshot_s3_prefix = tool_image_s3_prefix
        self.all_packages = None

    ### Private methods

    @staticmethod
    def generate_snapshot_id():
        return time.strftime("%Y%m%d-%H%M%S", time.gmtime())

    def _create_local_snapshot_directory(self, snapshot_id):
        snapshot_dir = os.path.join(self.base_snapshot_directory, "{}-{}".format(SNAPSHOT_CONST, snapshot_id))
        os.mkdir(snapshot_dir)
        return snapshot_dir

    @staticmethod
    def _take_most_recent(objects):
        return sorted(objects, key=lambda o: o[LAST_MODIFIED_KEY], reverse=True)[0]

    @staticmethod
    def _extract_package_name_from_key(key_prefix, all_objects):
        matching_objs = filter(lambda o: key_prefix in o[KEY_CONST], all_objects)
        most_recent_key = SnapshotManager._take_most_recent(matching_objs)[KEY_CONST]
        return most_recent_key.replace(key_prefix, "")

    def _get_all_packages(self):
        if self.all_packages:
            return self.all_packages
        self.all_packages = []
        paginator = self.s3.get_paginator("list_objects")
        page_iterator = paginator.paginate(Bucket=self.bucket_name, Prefix=S3_PACKAGE_KEY_PREFIX)
        for page in page_iterator:
            if CONTENTS_KEY in page:
                for key in page[CONTENTS_KEY]:
                    self.all_packages.append(key)
        return self.all_packages

    def _get_filename_of_package_in_s3(self, package):
        """For any given package (cbmc, cbmc-batch etc...) there will be many builds. We want to return the
        filename of the most recent build in S3
        NOTE: This relies on the fact that the date is in the package tarball filename because keys
        are returned in alphabetical order
        package: name of package build folder in S3 (eg cbmc)

        """
        object_contents = self._get_all_packages()
        return self._extract_package_name_from_key("{}{}/".format(S3_PACKAGE_KEY_PREFIX, package), object_contents)

    def _download_package_tar(self, package, package_filename=None):
        """
        Downloads the tarball of a particular package from S3
        :param package: the name of the package directory in S3 that we are downloading
        :param package_filename: Optional string to download a particular tarball. Default behaviour is latest
        :return: the package filename in S3 that was downloaded
        """
        if not self.snapshot_id or not self.local_snapshot_dir:
            raise Exception("Must have snapshot ID and local snapshot directory assigned "
                            "to download template package")
        if not package_filename:
            package_filename = self._get_filename_of_package_in_s3(package)
        local_filename = os.path.join(self.local_snapshot_dir, package_filename)
        key = "{}{}/{}".format(S3_PACKAGE_KEY_PREFIX, package, package_filename)
        self.s3.download_file(Bucket=self.bucket_name, Key=key, Filename=local_filename)
        return package_filename

    def _extract_package(self, package_filename):
        """
        Some packages need to be extracted before being put in the snapshot. This method goes into the
        snapshot local directory,
        :param package_filename:
        :return:
        """
        current_dir = os.getcwd()
        os.chdir(self.local_snapshot_dir)
        tar = tarfile.open(package_filename)

        #TODO: Is this prefix removal necessary? I don't see a common prefix in these tarballs
        prefix = os.path.commonprefix(tar.getnames())
        tar.extractall()
        # Flatten directory structure
        for file in os.listdir(prefix):
            shutil.move(os.path.join(prefix, file), file)
        os.rmdir(prefix)
        os.chdir(current_dir)

    def _upload_template_package(self):
        local_snapshot_files = os.listdir(self.local_snapshot_dir)
        for f in local_snapshot_files:
            key = self.tool_snapshot_s3_prefix + "{}-{}/{}".format(SNAPSHOT_CONST ,self.snapshot_id, f)
            self.s3.upload_file(Bucket=self.bucket_name, Filename=os.path.join(self.local_snapshot_dir, "{}".format(f)),
                                  Key=key)

    def _generate_snapshot_file(self, package_filenames):
        image_file = os.path.join(self.local_snapshot_dir, "{}-{}.json".format(SNAPSHOT_CONST, self.snapshot_id))
        with open(image_file, "w") as f:
            f.write(json.dumps(package_filenames))

    def _get_most_recent_cbmc_image(self):
        image_name = self.ecr.list_images(repositoryName=CBMC_REPO_NAME)[IMAGE_IDS_KEY][0][IMAGE_TAG_KEY]
        return remove_substring(image_name, UBUNTU_IMAGE_PREFIX)

    def _rename_package_tar(self, package_name, package_filename):
        current_dir = os.getcwd()
        os.chdir(self.local_snapshot_dir)
        #FIXME: these archived files should have predictable names
        if LAMBDA_CONST in package_filename:
            os.rename(package_filename, LAMBDA_ZIP_FILE)
        elif CBMC_BATCH_CONST in package_filename:
            os.rename(package_filename, CBMC_BATCH_TAR)
        elif CBMC_VIEWER_CONST in package_filename:
            os.rename(package_filename, CBMC_VIEWER_TAR)
        else:
            os.rename(package_filename, "{}.tar.gz".format(package_name))
        os.chdir((current_dir))

    ### Public methods

    def generate_new_snapshot_from_latest(self, overrides=None):
        """
        Generates a new snapshot and assigns it an ID. By default it will take the most recent
        build of each tool, but this can be overriden by providing an overrides dictionary that will
        give a specific package tarball
        :param overrides: dictionary - package names to particular package tar filename in S3 that we should use
        :return: string - generated snapshot id
        """
        self.snapshot_id = self.generate_snapshot_id()
        self.local_snapshot_dir = self._create_local_snapshot_directory(self.snapshot_id)
        package_filenames = {}
        for package in self.packages_required.keys():
            if overrides and package in overrides:
                downloaded_pkg = self._download_package_tar(package, package_filename=overrides[package])
            else:
                downloaded_pkg = self._download_package_tar(package)
            package_filenames[package] = downloaded_pkg

            if self.packages_required[package][EXTRACT_KEY]:
                self._extract_package(downloaded_pkg)
            self._rename_package_tar(package, downloaded_pkg)

        #TODO In the future we may want this to be more general
        image_tag_suffix = self._get_most_recent_cbmc_image()
        package_filenames["ImageTagSuffix"] = "-{}".format(image_tag_suffix)

        self._generate_snapshot_file(package_filenames)
        self._upload_template_package()
        return self.snapshot_id

    def download_snapshot(self, snapshot_id):
        """
        Downloads a snapshot description JSON from S3 and returns it as a dictionary
        :param snapshot_id: string - snapshot ID that we should download
        :return: dictionary containing all snapshot details
        """
        key = self.tool_snapshot_s3_prefix + "{}-{}/{}-{}.json" .format(SNAPSHOT_CONST, snapshot_id,
                                                                        SNAPSHOT_CONST, snapshot_id)
        self.s3.download_file(Bucket=self.bucket_name,
                              Key=key,
                              Filename=SNAPSHOT_TMP_FILENAME)
        with open(SNAPSHOT_TMP_FILENAME) as f:
            return json.loads(f.read())
