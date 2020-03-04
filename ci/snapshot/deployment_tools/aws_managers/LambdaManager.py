import boto3
import botocore_amazon.monkeypatch

from deployment_tools.utilities.utilities import find_string_match_ignore_case


class LambdaManager:
    """
    This class allows us to manage AWS Lambda. Specifically, it exposes methods to get and modify environment
    variables such as whether CI should update github or not.
    """

    # Lambda parameters as described in https://docs.aws.amazon.com/lambda/latest/dg/configuration-console.html
    LAMBDA_KEYS = [
        'DeadLetterConfig',
        'Description',
        'Environment',
        'FunctionName',
        'Handler',
        'KMSKeyArn',
        'Layers',
        'MemorySize',
        'RevisionId',
        'Role', 'Runtime',
        'Timeout',
        'TracingConfig',
        'VpcConfig'
    ]

    LAMBDA_VPCCONFIG_KEYS = [
        'SecurityGroupIds',
        'SubnetIds'
    ]

    def __init__(self, session):
        self.session = session
        self.lambda_client = self.session.client("lambda")

    def _get_function_name(self, function):
        """Return function name containing 'function' (case insensitive)"""
        names = [fnc['FunctionName'] for fnc in self.lambda_client.list_functions()['Functions']]
        name = find_string_match_ignore_case(function, names)
        if name is None:
            raise Exception("No single function with name {} in {}".format(function, names))
        return name

    def _get_variables(self, lambda_name):
        cfg = self.lambda_client.get_function_configuration(FunctionName=lambda_name)
        return cfg['Environment']['Variables']

    def _get_variable_name(self, variables, var):
        """Return variable name containing 'var' (case insensitive)"""
        names = list(variables.keys())
        name = find_string_match_ignore_case(var, names)
        if name is None:
            raise Exception("No single variable with name {} in {}".format(var, names))
        return name

    def _set_variables(self, function, variables):
        cfg = self.lambda_client.get_function_configuration(FunctionName=function)

        cfg = dict(filter(lambda item: item[0] in self.LAMBDA_KEYS, cfg.items()))
        if cfg.get('VpcConfig'):
            cfg['VpcConfig'] = dict(filter(lambda item: item[0] in self.LAMBDA_VPCCONFIG_KEYS, cfg['VpcConfig'].items()))
        cfg['Environment']['Variables'] = variables
        self.lambda_client.update_function_configuration(**cfg)

    def get_env_var(self, fn_name, var_name):
        """
        Get a lambda environment variable
        :param fn_name: Name of the lambda
        :param var_name: environment variable name
        :return: variable name value pair
        """
        lambda_name = self._get_function_name(fn_name)
        variables = self._get_variables(lambda_name)
        var_lambda_key = self._get_variable_name(variables, var_name)
        return (var_name, variables[var_lambda_key])

    def set_env_var(self, fn_name, name, value):
        """
        Set a lambda environment variable
        :param fn_name: Name of the lambda
        :param var_name: environment variable name
        :return: variable name value pair
        """
        lambda_name = self._get_function_name(fn_name)
        variables = self._get_variables(lambda_name)
        var_name = self._get_variable_name(variables, name)
        variables[var_name] = value
        self._set_variables(lambda_name, variables)

