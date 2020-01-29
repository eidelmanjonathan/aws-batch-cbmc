import logging

import boto3
import botocore_amazon.monkeypatch


class EnvironmentVariableManager:
    def __init__(self, profile):
        self.session = boto3.session.Session(profile_name=profile)
        self.lambda_client = self.session.client("lambda")
        self.codebuild_client = self.session.client("codebuild")

    def is_substring(self, str1, str2):
        return str1.lower() in str2.lower()

    def find_string_match(self, string, strings):
        matches = [str for str in strings if self.is_substring(string, str)]
        if len(matches) == 1:
            return matches[0]
        logging.info("No single match for %s in %s: Found matches %s",
                     string, strings, matches)
        return None

    def lambda_function_name(self, function):
        """Return function name containing 'function' (case insensitive)"""
        names = [fnc['FunctionName'] for fnc in self.lambda_client.list_functions()['Functions']]
        name = self.find_string_match(function, names)
        if name is None:
            raise Exception("No single function with name {} in {}".format(function, names))
        return name

    def lambda_get_variables(self, lambda_name):
        cfg = self.lambda_client.get_function_configuration(FunctionName=lambda_name)
        return cfg['Environment']['Variables']

    def lambda_variable_name(self, variables, var):
        """Return variable name containing 'var' (case insensitive)"""
        names = list(variables.keys())
        name = self.find_string_match(var, names)
        if name is None:
            raise Exception("No single variable with name {} in {}".format(var, names))
        return name

    def lambda_get_env(self, fn_name, var_name):
        lambda_name = self.lambda_function_name(fn_name)
        variables = self.lambda_get_variables(lambda_name)
        var_lambda_key = self.lambda_variable_name(variables, var_name)
        return (var_name, variables[var_lambda_key])

    def get_codebuild_fullname(self, project_name):
        names = self.codebuild_client.list_projects()['projects']
        name = self.find_string_match(project_name, names)
        if not name:
            raise Exception("No single project with name {} in {}".format(project_name, names))
        return name

    def codebuild_get_variables(self, project):
        projects = self.codebuild_client.batch_get_projects(names=[project])['projects']
        if len(projects) != 1:
            raise Exception("No single project named {}: Found matches {}"
                  .format(project, [proj['name'] for proj in projects]))
        return projects[0]['environment']['environmentVariables']

    def full_name(self, items, name, name_key='name'):
        names = [item[name_key] for item in items
                 if name.lower() in item[name_key].lower()]
        if len(names) == 1:
            return names[0]
        raise Exception("No single name containing {} in {}: Found {}"
              .format(name, [item[name_key] for item in items], names))

    def get_value(self, items, name, name_key='name', value_key='value'):
        vrs = [item for item in items if name == item[name_key]]
        if len(vrs) == 1:
            return vrs[0][value_key]
        raise Exception("Can't find {} in {}"
              .format(name, [item[name_key] for item in items]))

    def codebuild_get_env(self, project_name, var_name):
        project_full_name = self.get_codebuild_fullname(project_name)
        variables = self.codebuild_get_variables(project_full_name)
        full_var_name = self.full_name(variables, var_name)
        return (var_name, self.get_value(variables, full_var_name))

test = EnvironmentVariableManager("shared-proofs")
print(test.lambda_get_env("webhook", "ci_operational"))
print(test.codebuild_get_env('prepare', 'ci_updating_status'))