# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import time

STABLE_STACK_TIMEOUT = 15 * 60 # Wait 15 minutes for stacks to stablize

class CloudformationStacks():
    """
    This class manages stacks in Cloudformation. It is responsible for deploying and waiting for stacks,
    as well as dealing with the parameters and output variables
    TODO: This is a straight copy paste of the old stackst.py script. I think that this file could still be improved
        substantially but it is out of scope for now
    """
    def __init__(self, session):
        """
        :param session: boto3 session
        """
        self.session = session
        self.client = self.session.client("cloudformation")
        self.description = None
        self.stack = None
        self.update()

    ################################################################

    def update(self):
        self.description = self.client.describe_stacks()
        #FIXME Why nested functions
        def parse_parameters(params):
            return {param['ParameterKey']: param['ParameterValue'] for param in params}

        def parse_outputs(outs):
            # TODO: inline this
            return {out.get('ExportName') or out.get('OutputKey'): out['OutputValue'] for out in outs}

        def parse_stacks(stks):
            return {stk['StackName']:
                    {
                        "parameters": parse_parameters(stk.get('Parameters', [])),
                        "outputs": parse_outputs(stk.get('Outputs', [])),
                        "status": stk['StackStatus'],
                        "statusreason": stk.get('StackStatusReason')
                    }
                    for stk in stks}

        self.stack = parse_stacks(self.description['Stacks'])

    ################################################################

    def get_status(self, stack=None):
        #FIXME: SHouldn't return 2 types
        if stack is None:
            return {stk: self.stack[stk]['status'] for stk in self.stack}
        if stack in self.stack:
            return self.stack[stack]['status']
        return None

    def get_status_reason(self, stack=None):
        #FIXME: Duplicate code
        #FIXME: Shouldn't return 2 types
        if stack is None:
            return {stk: self.stack[stk]['statusreason'] for stk in self.stack}
        if stack in self.stack:
            return self.stack[stack]['statusreason']
        return None

    def get_output(self, output=None, stack=None):
        if stack is None and output is None:
            return {stk: self.stack[stk]['outputs'] for stk in self.stack}
        if stack is not None and output is None:
            return self.stack[stack]['outputs']
        if stack is None and output is not None:
            # assuming output appears in only one stack (or output values equal)
            for stk in self.stack:
                # print("Checking stack {}".format(stk))

                if output in self.stack[stk]['outputs']:
                    return self.stack[stk]['outputs'][output]
            return None
        return self.stack[stack]['outputs'][output]

    def get_client(self):
        return self.client

    def get_statuses(self, stacks=None):
        #TODO What is stacks
        if stacks is None:
            stacks = self.stack.keys()
        return {stack: self.get_status(stack) for stack in stacks}

    def get_status_reasons(self, stacks=None):
        #TODO What is stacks
        if stacks is None:
            stacks = self.stack.keys()
        return {stack: self.get_status_reason(stack) for stack in stacks}

    ################################################################

    def stable_stack(self, stack):
        status = self.get_status(stack)
        if status is None: # Perhaps the stack is not yet created
            return True
        return status.endswith('_COMPLETE') or status.endswith('_FAILED')

    def stable_stacks(self, stacks=None):
        if stacks is None:
            stacks = self.stack.keys()
        return all([self.stable_stack(stack) for stack in stacks])

    def successful_stack(self, stack):
        status = self.get_status(stack)
        reason = self.get_status_reason(stack)
        return (status.endswith('_COMPLETE') and
                (reason is None or 'failed' not in reason))

    def successful_stacks(self, stacks=None):
        if stacks is None:
            stacks = self.stack.keys()
        return all([self.successful_stack(stack) for stack in stacks])

    def wait_for_stable_stacks(self, stacks=None):
        if stacks is None:
            stacks = self.stack.keys()

        def print_statuses(statuses):
            print("\nStack status:")
            for stack in sorted(statuses.keys()):
                print("  {:20}: {}".format(stack, statuses[stack]))

        # One might use a cloudformation waiter here, but a waiter can
        # wait on only one stack and only one status.  Here there are
        # several stacks and several possible statuses for a stable
        # stack.  Also, waiters print no progress information during
        # the wait.

        start = time.time()
        while time.time() < start + STABLE_STACK_TIMEOUT:
            self.update()
            statuses = self.get_statuses(stacks)
            print_statuses(statuses)
            if self.stable_stacks(statuses):
                return
            time.sleep(5)

        raise UserWarning("Timed out waiting for stacks to stabilize")

    ################################################################

    def display(self, stacks=None):
        if stacks is None:
            stacks = self.stack.keys()

        def display_parameters(params):
            print("  Parameters:")
            for key in sorted(params.keys()):
                print("    {:20}: {}".format(key, params[key]))

        def display_outputs(outs):
            print("  Outputs:")
            for key in sorted(outs.keys()):
                print("    {:20}: {}".format(key, outs[key]))

        for stack in sorted(stacks):
            print("\n{}".format(stack))
            display_parameters(self.stack[stack]['parameters'])
            display_outputs(self.stack[stack]['outputs'])
            print("  Status: {} ({})".format(self.stack[stack]['status'],
                                             self.stack[stack]['statusreason']))

    ################################################################
