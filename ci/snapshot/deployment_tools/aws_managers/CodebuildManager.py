import logging

import boto3
import botocore_amazon.monkeypatch

from deployment_tools.utilities.utilities import find_string_match_ignore_case


class CodebuildManager:
    """
    This class allows us to manage AWS Codebuild. Specifically, it exposes methods to get and modify environment
    variables such as whether CI should update github or not.
    """

    # These are the keys as documented here: https://docs.aws.amazon.com/zh_cn/codebuild/latest/APIReference/API_Project.html
    CODEBUILD_KEYS = \
        ['artifacts',
         'badgeEnabled',
         'cache',
         'description',
         'encryptionKey',
         'environment',
         'logsConfig',
         'name',
         'queuedTimeoutInMinutes',
         'secondaryArtifacts',
         'secondarySources',
         'serviceRole',
         'source',
         'tags',
         'timeoutInMinutes',
         'vpcConfig']

    def __init__(self, session):
        self.session = session
        self.codebuild_client = self.session.client("codebuild")

    ### Private methods
    def _get_full_project_name(self, project_name):
        names = self.codebuild_client.list_projects()['projects']
        name = find_string_match_ignore_case(project_name, names)
        if not name:
            raise Exception("No single project with name {} in {}".format(project_name, names))
        return name

    def _get_full_variable_name(self, items, name, name_key='name'):
        return find_string_match_ignore_case(name, [item[name_key] for item in items], enforce_unique=True)

    def _get_value(self, items, name, name_key='name', value_key='value'):
        vrs = [item for item in items if name == item[name_key]]
        if len(vrs) == 1:
            return vrs[0][value_key]
        raise Exception("Can't find {} in {}"
                        .format(name, [item[name_key] for item in items]))

    def _generate_new_value_item(self, item, value_key, value):
        item[value_key] = value
        return item

    def _generate_map_with_new_value(self, items, name, value, name_key='name', value_key='value'):
        keys = [item[name_key] for item in items]
        if name not in keys:
            raise Exception("Can't find {} in {}".format(name, keys))
        if keys.count(name) > 1:
            raise Exception("Found a duplicate entry of {} in {}".format(name, keys))
        return list(map(lambda item :
                        self._generate_new_value_item(item, value_key, value) if item[name_key] == name else item, items))

    def _codebuild_get_variables(self, project):
        projects = self.codebuild_client.batch_get_projects(names=[project])['projects']
        if len(projects) != 1:
            raise Exception("No single project named {}: Found matches {}"
                            .format(project, [proj['name'] for proj in projects]))
        return projects[0]['environment']['environmentVariables']

    def _codebuild_set_variables(self, project, variables):
        projects = self.codebuild_client.batch_get_projects(names=[project])['projects']
        if len(projects) != 1:
            raise Exception("No single project named {}: Found matches {}"
                  .format(project, [proj['name'] for proj in projects]))
        #TODO: Why would there every be things that aren't codebuild keys?
        update = dict(filter(lambda item: item[0] in self.CODEBUILD_KEYS, projects[0].items()))
        update['environment']['environmentVariables'] = variables
        self.codebuild_client.update_project(**update)

    ### Public methods
    def get_env_var(self, project_name, var_name):
        """
        Get a codebuild environment variable
        :param project_name: string
        :param var_name: string
        """
        project_full_name = self._get_full_project_name(project_name)
        variables = self._codebuild_get_variables(project_full_name)
        full_var_name = self._get_full_variable_name(variables, var_name)
        return (var_name, self._get_value(variables, full_var_name))


    def set_env_var(self, project_name, var_name, value):
        """
        Set a codebuild environment variable
        :param project_name: string
        :param var_name: string
        :param value: string
        """
        project_full_name = self._get_full_project_name(project_name)
        variables = self._codebuild_get_variables(project_full_name)
        var_name = self._get_full_variable_name(variables, var_name)
        variables = self._generate_map_with_new_value(variables, var_name, value)
        self._codebuild_set_variables(project_full_name, variables)
