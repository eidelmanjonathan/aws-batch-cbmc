import logging
import time

import boto3

DEFAULT_SLEEP_INTERVAL = 5
class PipelineManager:
    """
    Class for interacting with AWS pipelines.
    """

    def __init__(self, session, sleep_interval=None):
        self.session = session
        self.pipeline_client = self.session.client("codepipeline")
        self.logger = logging.getLogger('PipelineManager')
        self.logger.setLevel(logging.INFO)
        self.sleep_interval = sleep_interval if sleep_interval else DEFAULT_SLEEP_INTERVAL

    ### PRIVATE
    def _is_pipeline_complete(self, pipeline_name):
        pipeline_state = self.pipeline_client.get_pipeline_state(name=pipeline_name)
        return all("latestExecution" in state.keys()
                       for state in pipeline_state["stageStates"]) \
               and not any(state["latestExecution"]["status"] == "InProgress"
                       for state in pipeline_state["stageStates"])


    ### PUBLIC

    def trigger_pipeline_async(self, pipeline_name):
        """
        Trigger code pipeline. Does not wait for pipeline to complete
        :param pipeline_name: string
        """
        self.pipeline_client.start_pipeline_execution(name=pipeline_name)

    def wait_for_pipeline_completion(self, pipeline_name):
        """
        Checks every second until a pipeline is complete
        :param pipeline_name:
        :return:
        """
        self.logger.info("Waiting for build pipeline: {0}".format(pipeline_name))
        while not self._is_pipeline_complete(pipeline_name):
            time.sleep(self.sleep_interval)
        self.logger.info("Done waiting for build pipeline: {0}".format(pipeline_name))


