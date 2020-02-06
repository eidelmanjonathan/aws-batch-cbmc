import logging

import boto3
import botocore_amazon.monkeypatch

from new_tools.utilities.utilities import find_string_match


class CodebuildManager:
    """
    This class allows us to manage AWS Codebuild. Specifically, it exposes methods to get and modify environment
    variables such as whether CI should update github or not.
    """
    CODEBUILD_KEYS = [
        'name',
        'description',
        'source',
        'secondarySources',
        'artifacts',
        'secondaryArtifacts',
        'cache',
        'environment',
        'serviceRole',
        'timeoutInMinutes',
        'queuedTimeoutInMinutes',
        'encryptionKey',
        'tags',
        'vpcConfig',
        'badgeEnabled',
        'logsConfig'
    ]

    def __init__(self, profile):
        self.session = boto3.session.Session(profile_name=profile)
        self.codebuild_client = self.session.client("codebuild")

    def get_full_project_name(self, project_name):
        names = self.codebuild_client.list_projects()['projects']
        name = find_string_match(project_name, names)
        if not name:
            raise Exception("No single project with name {} in {}".format(project_name, names))
        return name

    def get_full_variable_name(self, items, name, name_key='name'):
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

    def set_value(self, items, name, value, name_key='name', value_key='value'):
        found = 0
        new = []
        for item in items:
            if item[name_key] == name:
                item[value_key] = value
                found = found + 1
            new.append(item)
        if found == 1:
            return new
        raise Exception("Can't find {} in {}"
              .format(name, [item[name_key] for item in items]))

    def codebuild_get_variables(self, project):
        projects = self.codebuild_client.batch_get_projects(names=[project])['projects']
        if len(projects) != 1:
            raise Exception("No single project named {}: Found matches {}"
                            .format(project, [proj['name'] for proj in projects]))
        return projects[0]['environment']['environmentVariables']

    def codebuild_set_variables(self, project, variables):
        projects = self.codebuild_client.batch_get_projects(names=[project])['projects']
        if len(projects) != 1:
            raise Exception("No single project named {}: Found matches {}"
                  .format(project, [proj['name'] for proj in projects]))
        update = projects[0]
        for key in list(update.keys()):
            if key not in self.CODEBUILD_KEYS:
                del update[key]
        update['environment']['environmentVariables'] = variables
        self.codebuild_client.update_project(**update)

    def get_env_var(self, project_name, var_name):
        """
        Get a codebuild environment variable
        :param project_name:
        :param var_name:
        """
        project_full_name = self.get_full_project_name(project_name)
        variables = self.codebuild_get_variables(project_full_name)
        full_var_name = self.get_full_variable_name(variables, var_name)
        return (var_name, self.get_value(variables, full_var_name))


    def set_env_var(self, project_name, var_name, value):
        """
        Set a codebuild environment variable
        :param project_name:
        :param var_name:
        :param value:
        """
        project_full_name = self.get_full_project_name(project_name)
        variables = self.codebuild_get_variables(project_full_name)
        var_name = self.get_full_variable_name(variables, var_name)
        variables = self.set_value(variables, var_name, value)
        self.codebuild_set_variables(project_full_name, variables)
