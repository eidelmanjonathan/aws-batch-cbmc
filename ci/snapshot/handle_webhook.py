import os
import hashlib
import hmac
import json
import traceback
from pprint import pprint
import logging
import uuid

import boto3

############################
# clog_writert copy
#---------------------------------------------------------------------------
#   Miscellaneous module stuff
#---------------------------------------------------------------------------
UNKNOWN = "UNKNOWN"
STARTED = "STARTED"
IGNORED = "COMPLETED:IGNORED"
SUCCEEDED = "COMPLETED:SUCCEEDED"
FAILED = "COMPLETED:FAILED"
LAUNCH_SUCCEEDED = "LAUNCHED:SUCCEEDED"
LAUNCH_FAILED = "LAUNCHED:FAILED"

def is_completed_status(status):
  return status == SUCCEEDED or status == FAILED or status == IGNORED

def entry_string(task_name, task_id, correlation_list, status, args):
  summary = {}
  summary['task_name'] = task_name
  summary['task_id'] = task_id
  summary['correlation_list'] = correlation_list
  summary['status'] = status
  summary.update(args)
  return json.dumps(summary)


class CLogWriter():
  def __init__(self, task_name, task_id=None, correlation_list=[]):
      # snapshot is defined by a json string or json file
      self.task_name = task_name
      self.task_id = task_id
      self.correlation_list = correlation_list

  @classmethod
  def init_lambda(cls, task_name, event, context):
      task_id = context.aws_request_id
      correlation_list = event.get('correlation_list', [task_id]).copy()
      return cls(task_name = task_name,
          task_id=task_id,
          correlation_list=correlation_list)

  @classmethod
  def init_aws_batch(cls, task_name, task_id, correlation_list):
      return cls(task_name=task_name,
                 task_id = task_id,
                 correlation_list=correlation_list)

  @classmethod
  def init_child(cls, parent, child_task_name, child_task_id):
      child_correlation_list = parent.create_child_correlation_list()
      return cls(task_name=child_task_name,
                 task_id=child_task_id,
                 correlation_list=child_correlation_list)

  # TODO: if we care about lambda concurrency, have all task log messages run
  # TODO: through our log functions that prepend the task_id.
  # def critical(self, msg, *args, **kwargs):
  # def error(self, msg, *args, **kwargs):
  # def warning(self, msg, *args, **kwargs):
  # def info(self, msg, *args, **kwargs):
  # def debug(self, msg, *args, **kwargs):

  def entry_string(self, status, args):
      return entry_string(self.task_name, self.task_id, self.correlation_list, status, args)

  def started(self):
      print(self.entry_string(STARTED, {}))

  def launched(self, status=LAUNCH_SUCCEEDED):
      print(self.entry_string(status, {}))

  def launch_child(self, child_task_name, child_task_id, child_correlation_list, status=LAUNCH_SUCCEEDED):
      print(entry_string(child_task_name, child_task_id, child_correlation_list, status, {}))

  def summary(self, status, event, response):
      args = {'event' : event, 'response': response}
      print(self.entry_string(status, args))


  def get_correlation_list(self):
      return self.correlation_list


  # generate a new UUID to track child.
  def create_child_correlation_list(self):
      child_list = self.correlation_list.copy()
      child_list.append(str(uuid.uuid4()))
      return child_list
# end clog_writert copy
############################


def get_github_secret():
  """Get plaintext for key used by GitHub to compute HMAC"""
  sm = boto3.client('secretsmanager')
  s = sm.get_secret_value(SecretId='GitHubSecret')
  return str(json.loads(s['SecretString'])[0]['Secret'])

def check_hmac(github_signature, payload):
  """
  Check HMAC as suggested here:
  https://developer.github.com/webhooks/securing/
  """
  h = hmac.new(get_github_secret().encode(), payload.encode(), hashlib.sha1)
  signature = 'sha1=' + h.hexdigest()
  return hmac.compare_digest(signature, github_signature)


def lambda_handler(event, context):
  logger = CLogWriter.init_lambda("HandleWebhookLambda", event, context)
  logger.started()

  print("event = ")
  print(json.dumps(event))
  print("context = ")
  pprint(context)

  running = os.environ.get('CBMC_CI_OPERATIONAL')
  if not (running and running.strip().lower() == 'true'):
     print("Ignoring GitHub event: CBMC CI is not running")
     return {'statusCode': 200}

  response = {}
  try:
      event['headers'] = {k.lower(): v
                          for k, v in event['headers'].items()}
      if not check_hmac(
              str(event['headers']['x-hub-signature']),
              str(event['body'])):
          response['statusCode'] = 403
      elif event['headers']['x-github-event'] == 'ping':
          response['body'] = 'pong'
          response['statusCode'] = 200
      else:
          lc = boto3.client('lambda')
          event['correlation_list'] = logger.create_child_correlation_list()
          logger.launch_child("cbmc_ci_start:lambda_handler", None, event['correlation_list'])
          result = lc.invoke(
              FunctionName='InvokeBatchLambda',
              Payload=json.dumps(event))
          response['statusCode'] = result['StatusCode']
  except Exception as e:
      response['statusCode'] = 500
      traceback.print_exc()
      print('Error: ' + str(e))
      # raise e

  print("response = ")
  print(json.dumps(response))
  status = SUCCEEDED if (response['statusCode'] >= 200 and response['statusCode'] <= 299) else FAILED
  logger.summary(status, event, response)
  return response