import json
class ParameterSet:
    def __init__(self,filename=None, string=None, json_obj=None):
        if not filename and not string and not json_obj:
            raise Exception("Must provide filename, string or json")

        if json_obj:
            self.image = json_obj
            self.parameters = self.image.get("parameters")
        else:
            if filename:
                with open(filename) as handle:
                    string = handle.read()
            self.image = json.loads(string)
            self.parameters = self.image.get("parameters")

    def get(self, key):
        return self.image.get(key)

    def get_parameter(self, key):
        return self.parameters.get(key) if self.parameters else None

    def write(self, filename):
        with open(filename, 'w') as handle:
            json.dump(self.image, handle, indent=2)

