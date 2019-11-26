# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
# Example of expected values:
# {
#     "ProjectName": "MQTT-Beta2",
#     "NotificationAddress": "jeid@amazon.com",
#     "SIMAddress": "jeid@amazon.com",
#     "GitHubRepository": "eidelmanjonathan/amazon-freertos",
#     "ViewerRepositoryOwner": "markrtuttle"
#   }

import json

class ProjectParams():
    def __init__(self, string=None, filename=None):
        # snapshot is defined by a json string or json file
        if string is None:
            if filename is None:
                raise UserWarning("No string or filename given for snapshot.")
            with open(filename) as handle:
                string = handle.read()
        self.project_params = json.loads(string)

    def write(self, filename):
        with open(filename, 'w') as handle:
            json.dump(self.project_params, handle, indent=2)
