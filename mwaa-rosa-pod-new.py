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
from airflow.decorators import task
from airflow.models.baseoperator import chain
from airflow.models import Connection
from airflow import settings
import requests
import yaml
import boto3
import json
# import random
# import string

default_args = {
   'owner': 'aws',
   'depends_on_past': False,
   'start_date': datetime(2024, 3, 15),
   'provide_context': True
}

# use a kube_config template stored in s3 dags folder
template_kube_config_path = '/usr/local/airflow/dags/template_kube_config.yaml'

# set variables
rosa_cluster_name = '<ROSA Cluster name>:6443'
rosa_url = '<ROSA URL>:6443'
sm_secret_id = '<Secret ID>'
# run `oc get route oauth-openshift -n openshift-authentication -o json | jq .spec.host` to get the oauth URI
rosa_oauth_uri = '<ROSA OAuth URL>/oauth/authorize?client_id=openshift-challenging-client&response_type=token'

def retrieve_from_secrets_manager(secret_id):
   sm = boto3.client('secretsmanager')
   response = sm.get_secret_value(
      SecretId=secret_id,
   )
   creds = json.loads(response['SecretString'])

   return creds

def construct_kube_config(template_kube_config_path, cluster_url, cluster_name, namespace, user, access_token):
   # construct kube_config file using the access token
   with open(template_kube_config_path) as f:
      kubeconfig_json = yaml.safe_load(f)

   kubeconfig_json['clusters'][0]['cluster']['server'] = cluster_url
   kubeconfig_json['clusters'][0]['name'] = cluster_name
   kubeconfig_json['contexts'][0]['context']['cluster'] = cluster_name
   kubeconfig_json['contexts'][0]['context']['namespace'] = namespace
   kubeconfig_json['contexts'][0]['context']['user'] = f'{user}/{cluster_name}'
   kubeconfig_json['contexts'][0]['name'] = f'{namespace}/{cluster_name}/{user}'
   kubeconfig_json['current-context'] = f'{namespace}/{cluster_name}/{user}'
   kubeconfig_json['users'][0]['name'] = f'{user}/{cluster_name}'
   kubeconfig_json['users'][0]['user']['token'] = access_token

   return kubeconfig_json

@task(multiple_outputs=True)
def create_k8s_connection(sm_secret_id, rosa_cluster_name, rosa_oauth_uri, template_kube_config_path, rosa_url):
   # get username and password from AWS Secrets Manager
   creds = retrieve_from_secrets_manager(sm_secret_id)
   rosa_namespace = creds['namespace']
   rosa_user = creds['username']
   rosa_password = creds['password']

   # generate access token to OpenShift cluster using the retrieved credentials
   response = requests.get(rosa_oauth_uri, auth=(rosa_user, rosa_password), allow_redirects=False)
   res_location = response.headers['Location']
   access_token = res_location.split('#')[1].split('&')[0].split('=')[1]

   kubeconfig_json = construct_kube_config(template_kube_config_path, rosa_url, rosa_cluster_name, rosa_namespace, rosa_user, access_token)

   # generate a random 4-character string to ensure uniqueness
   # conn_name = 'rosa_kubernetes_conn_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k = 4))
   conn_name = 'rosa_kubernetes_conn'

   # reference: https://airflow.apache.org/docs/apache-airflow-providers-cncf-kubernetes/stable/connections/kubernetes.html
   new_k8s_conn = Connection(
      conn_id=conn_name,
      conn_type="kubernetes",
      extra={
         "kube_config": json.dumps(kubeconfig_json),
         "namespace": rosa_namespace
      },
   )
   session = settings.Session()
   session.add(new_k8s_conn)
   session.commit()

   return {
      'rosa_namespace': rosa_namespace, 
      'rosa_user': rosa_user,
      # 'connection_name': conn_name,
      'connection_id': new_k8s_conn.id # get integer ID of the created connection
   }

@task
def delete_connection(connection_id):
   session = settings.Session()
   curr_conn = session.get(Connection, connection_id)
   session.delete(curr_conn)

with DAG(
   'kubernetes_pod_example_new', default_args=default_args, schedule_interval=None
) as dag:
   
   connection_details = create_k8s_connection(sm_secret_id, rosa_cluster_name, rosa_oauth_uri, template_kube_config_path, rosa_url)

   run_in_pod = KubernetesPodOperator(
      kubernetes_conn_id='rosa_kubernetes_conn',
      image="ubuntu:18.04",
      cmds=["bash"],
      arguments=["-c", "ls"],
      labels={"foo": "bar"},
      name="mwaa-pod-test",
      task_id="pod-task",
      get_logs=True,
      dag=dag,
      is_delete_operator_pod=False,
      in_cluster=False,
   )

   connection_details >> run_in_pod >> delete_connection(connection_details['connection_id'])
