import json
import os
import time


class ParameterSet:
    def __init__(self,filename=None, string=None):
        # snapshot is defined by a json string or json file
        if string is None:
            if filename is None:
                raise UserWarning("No string or filename given for snapshot.")
            with open(filename) as handle:
                string = handle.read()
        self.image = json.loads(string)
        self.parameters = self.image.get("parameters")

    def get(self, key):
        return self.image.get(key)

    def get_parameter(self, key):
        return self.parameters.get(key)

    def write(self, filename):
        with open(filename, 'w') as handle:
            json.dump(self.image, handle, indent=2)

