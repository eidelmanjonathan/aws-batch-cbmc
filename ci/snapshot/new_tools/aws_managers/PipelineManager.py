import time

import boto3


class PipelineManager:

    def __init__(self, profile):
        self.session = boto3.session.Session(profile_name=profile)
        self.pipeline_client = self.session.client("codepipeline")

    def trigger_pipeline(self, pipeline_name):
        self.pipeline_client.start_pipeline_execution(name=pipeline_name)

    def _is_pipeline_complete(self, pipeline_name):
        pipeline_state = self.pipeline_client.get_pipeline_state(name=pipeline_name)
        return all("latestExecution" in state.keys()
                       for state in pipeline_state["stageStates"]) \
               and not any(state["latestExecution"]["status"] == "InProgress"
                       for state in pipeline_state["stageStates"])

    def wait_for_pipeline_completion(self, pipeline_name):
        print("Waiting for build pipeline: {0}".format(pipeline_name))
        while not self._is_pipeline_complete(pipeline_name):
            time.sleep(1)
        print("Done waiting for build pipeline: {0}".format(pipeline_name))