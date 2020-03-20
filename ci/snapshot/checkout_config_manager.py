import json
import logging
import os
import subprocess
from os import path


class CheckoutConfig:
    CONFIG_FILENAME = "padston_config.json"
    CHECKOUT_SCRIPT_KEY = "checkoutScript"
    GITHUB_FOLDER = ".github"

    def __init__(self, webhook_event, srcdir):
        self.webhook_event = webhook_event
        print("webhook event: {}".format(webhook_event))
        print("webhook keys: {}".format(self.webhook_event.keys()))
        self.srcdir = srcdir
        self.logger = logging.getLogger("CheckoutConfig")
        self.logger.setLevel(logging.INFO)
        self.config_file = path.join(self.srcdir, self.GITHUB_FOLDER, self.CONFIG_FILENAME)
        try:
            self.repo_owner, self.repo_name = self.webhook_event.get("name").split("/")
        except Exception as e:
            self.logger.error("Failed to get repo name and owner from webhook with name {}"
                              .format(self.webhook_event.get("name")))
            raise e
        self.config_dict = self.read_config_file()
        if self.repo_name not in self.config_dict:
            raise Exception("Repo {} is not in the config file at {}".format(self.repo_name, self.config_file))
        self.checkout_info = self.config_dict[self.repo_name]

    def run_checkout(self):
        self.logger.info("Running checkout script {}".format(self.checkout_info[self.CHECKOUT_SCRIPT_KEY]))
        self._run_command(path.join(self.srcdir, self.GITHUB_FOLDER, self.checkout_info[self.CHECKOUT_SCRIPT_KEY]),
                          self.srcdir)

    def read_config_file(self):
        self.logger.info("Trying to read config file at {}".format(self.config_file))
        with open(self.config_file) as f:
            return json.loads(f.read())

    def _run_command(self, cmd, cwd=None):
        self.logger.info('Running "%s" in "%s"', ' '.join(cmd), cwd or '.')
        kwds = {'capture_output': True}
        if cwd:
            kwds['cwd'] = cwd
        result = subprocess.run(cmd, **kwds)
        debug = self._subprocess_data(cmd, cwd, result.stdout, result.stderr)
        logging.info(self._debug_json('subprocess', debug))
        result.check_returncode()

    def _subprocess_data(self, cmd, cwd, stdout, stderr):
        debug = {'cmd': ' '.join(cmd),
                 'cwd': cwd,
                 'stdout': stdout.decode("utf-8").splitlines(),
                 'stderr': stderr.decode("utf-8").splitlines()
                 }
        return debug

    def _debug_json(self, action, body):
        debug = {'script': os.path.basename(__file__),
                 'action': action,
                 'body': body}
        return json.dumps(debug)

