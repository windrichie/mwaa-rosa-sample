"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
from airflow import DAG
from datetime import datetime
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
import requests
import yaml
import boto3
import json

default_args = {
   'owner': 'aws',
   'depends_on_past': False,
   'start_date': datetime(2024, 3, 15),
   'provide_context': True
}

dag = DAG(
   'kubernetes_pod_example', default_args=default_args, schedule_interval=None
)

# use a kube_config template stored in s3 dags folder
template_kube_config_path = '/usr/local/airflow/dags/template_kube_config.yaml'

# set variables
rosa_cluster_name = '<ROSA Cluster name>:6443'
rosa_url = '<ROSA URL>:6443'
local_kube_config_path = '/tmp/kube_config.yaml'
sm_secret_id = 'mwaa-rosa-demo/rosacredentials'
# run `oc get route oauth-openshift -n openshift-authentication -o json | jq .spec.host` to get the URI
rosa_oauth_uri = '<ROSA OAuth URL>/oauth/authorize?client_id=openshift-challenging-client&response_type=token'

# get username and password from AWS Secrets Manager
sm = boto3.client('secretsmanager')
response = sm.get_secret_value(
    SecretId=sm_secret_id,
)
creds = json.loads(response['SecretString'])
rosa_namespace = creds['namespace']
rosa_user = creds['username']
rosa_password = creds['password']

# generate access token to OpenShift cluster using the retrieved credentials
response = requests.get(rosa_oauth_uri, auth=(rosa_user, rosa_password), allow_redirects=False)
res_location = response.headers['Location']
access_token = res_location.split('#')[1].split('&')[0].split('=')[1]

# construct kube_config file using the access token
with open(template_kube_config_path) as f:
   doc = yaml.safe_load(f)

doc['clusters'][0]['cluster']['server'] = rosa_url
doc['clusters'][0]['name'] = rosa_cluster_name
doc['contexts'][0]['context']['cluster'] = rosa_cluster_name
doc['contexts'][0]['context']['namespace'] = rosa_namespace
doc['contexts'][0]['context']['user'] = f'{rosa_user}/{rosa_cluster_name}'
doc['contexts'][0]['name'] = f'{rosa_namespace}/{rosa_cluster_name}/{rosa_user}'
doc['current-context'] = f'{rosa_namespace}/{rosa_cluster_name}/{rosa_user}'
doc['users'][0]['name'] = f'{rosa_user}/{rosa_cluster_name}'
doc['users'][0]['user']['token'] = access_token

with open(local_kube_config_path, 'w') as f:
   yaml.safe_dump(doc, f, default_flow_style=False)

podRun = KubernetesPodOperator(
   namespace=rosa_namespace,
   image="ubuntu:18.04",
   cmds=["bash"],
   arguments=["-c", "ls"],
   labels={"foo": "bar"},
   name="mwaa-pod-test",
   task_id="pod-task",
   get_logs=True,
   dag=dag,
   is_delete_operator_pod=False,
   config_file=local_kube_config_path,
   in_cluster=False,
   cluster_context=f'{rosa_namespace}/{rosa_cluster_name}/{rosa_user}'
)