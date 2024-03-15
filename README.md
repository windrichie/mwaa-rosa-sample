# Using MWAA KubernetesPodOperator with ROSA

This repository provides sample Apache Airflow DAG file that triggers a Kubernetes pod to run on an RedHat OpenShift on AWS (ROSA) cluster.

## Disclaimer
This project is used for demo purposes only and should NOT be considered for production use.

## Pre-requisites

This repository provides the DAG file. As such there are several pre-requisites that you would need to complete before you can use the DAG.

1. **Create ROSA cluster**

    If you do not have an existing ROSA cluster, you may refer to [this workshop](https://catalog.workshops.aws/aws-openshift-workshop/en-US) on a guide to create one. You would need to first [enable ROSA](https://catalog.workshops.aws/aws-openshift-workshop/en-US/1-getting-started/1-enabling-rosa) in your AWS account, [install CLI tools](https://catalog.workshops.aws/aws-openshift-workshop/en-US/1-getting-started/2-deployment-tools) such as OpenShift and ROSA CLI, and [create a cluster](https://catalog.workshops.aws/aws-openshift-workshop/en-US/1-getting-started/3-create-cluster) using ROSA CLI or Terraform.  

1. **ROSA setup - create IdP, Project and User**

    For MWAA to be able to spin up pods in the ROSA cluster, you need to pre-create a Project (namespace) and user in your ROSA cluster. There are several identity provider (IdP) options for your ROSA cluster, but in this repository, we set up a local LDAP as the IdP. Follow [this workshop section](https://catalog.workshops.aws/aws-openshift-workshop/en-US/1-getting-started/4-create-users) to set-up an LDAP and create users and projects (MWAA only needs 1). In this repository, we are using `user1` Project and user.  <br/>

1. **Create MWAA environment**

    To create an MWAA environment, you may follow [this documentation](https://docs.aws.amazon.com/mwaa/latest/userguide/create-environment.html).

1. **Create secret in AWS Secrets Manager**

    Create a secret in AWS Secrets Manager that contains the ROSA username, password and namespace that MWAA will be using. This way there is no need to hardcode credentials in the DAG file. Alternatively, you can also set-up Secrets Manager as the secret backend for your MWAA environment (see [this page](https://docs.aws.amazon.com/mwaa/latest/userguide/connections-secrets-manager.html)).

## Deployment & Testing Steps

1. **Replace the placeholder values in `mwaa-rosa-pod.py` such as `rosa_cluster_name`, `rosa_url` and `sm_secret_id`.**

1. **Upload files to MWAA S3 buckets**

    In this repository, we are using the Apache Airflow [KubernetesPodOperator](https://airflow.apache.org/docs/apache-airflow-providers-cncf-kubernetes/stable/operators.html) which requires several packages to be installed in the MWAA environment. Add the packages listed in `requirements.txt` to the existing file in the MWAA S3 bucket, or create one if not existing. See [this page](https://docs.aws.amazon.com/mwaa/latest/userguide/working-dags-dependencies.html) for more information about installing Python dependencies on MWAA.

    Next, upload both the `mwaa-rosa-pod.py` and `template_kube_config.yaml` into the MWAA DAGs folder.

1. **Ensure that there is network connectivity from the MWAA environment to the ROSA cluster. If they are in different VPCs, configure VPC peering or AWS Transit Gateway to establish connectivity between the VPCs.**

1. **Trigger DAG from Airflow console**

    In MWAA console, open the Airflow UI, find the `kubernetes_pod_example` DAG and trigger it. After a few seconds you should see that the task has been successfully run. Inspect the logs and you should see a list of directories being printed (the DAG simply does an `ls` command in the container)

    On ROSA side, you can run `kubectl get pods -n user1` and you should see that a pod has been spin up with status Completed.