import boto3
import botocore_amazon.monkeypatch

from new_tools.utilities.utilities import find_string_match


class LambdaManager:
    LAMBDA_KEYS = [
        'FunctionName',
        'Role',
        'Handler',
        'Description',
        'Timeout',
        'MemorySize',
        'VpcConfig',
        'Environment',
        'Runtime',
        'DeadLetterConfig',
        'KMSKeyArn',
        'TracingConfig',
        'RevisionId',
        'Layers'
    ]

    LAMBDA_VPCCONFIG_KEYS = [
        'SubnetIds',
        'SecurityGroupIds'
    ]

    def __init__(self, profile):
        self.session = boto3.session.Session(profile_name=profile)
        self.lambda_client = self.session.client("lambda")

    def get_function_name(self, function):
        """Return function name containing 'function' (case insensitive)"""
        names = [fnc['FunctionName'] for fnc in self.lambda_client.list_functions()['Functions']]
        name = find_string_match(function, names)
        if name is None:
            raise Exception("No single function with name {} in {}".format(function, names))
        return name

    def get_variables(self, lambda_name):
        cfg = self.lambda_client.get_function_configuration(FunctionName=lambda_name)
        return cfg['Environment']['Variables']

    def get_variable_name(self, variables, var):
        """Return variable name containing 'var' (case insensitive)"""
        names = list(variables.keys())
        name = find_string_match(var, names)
        if name is None:
            raise Exception("No single variable with name {} in {}".format(var, names))
        return name

    def set_variables(self, function, variables):
        cfg = self.lambda_client.get_function_configuration(FunctionName=function)
        for key in list(cfg.keys()):
            if key not in self.LAMBDA_KEYS:
                del cfg[key]
        if cfg.get('VpcConfig'):
            for key in list(cfg['VpcConfig'].keys()):
                if key not in self.LAMBDA_VPCCONFIG_KEYS:
                    del cfg['VpcConfig'][key]
        cfg['Environment']['Variables'] = variables
        self.lambda_client.update_function_configuration(**cfg)

    def get_env_var(self, fn_name, var_name):
        lambda_name = self.get_function_name(fn_name)
        variables = self.get_variables(lambda_name)
        var_lambda_key = self.get_variable_name(variables, var_name)
        return (var_name, variables[var_lambda_key])

    def set_env_var(self, fn_name, name, value):
        lambda_name = self.get_function_name(fn_name)
        variables = self.get_variables(lambda_name)
        var_name = self.get_variable_name(variables, name)
        variables[var_name] = value
        self.set_variables(lambda_name, variables)

