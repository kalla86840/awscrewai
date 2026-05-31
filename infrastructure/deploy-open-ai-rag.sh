#!/usr/bin/env bash
set -euo pipefail

aws cloudformation deploy \
  --region "${AWS_REGION:-us-west-1}" \
  --template-file infrastructure/codepipeline.yaml \
  --stack-name open-ai-rag-cicd \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName=open-ai-rag \
    ArtifactBucketName=mlopswithsagemaker111 \
    CodeStarConnectionArn=arn:aws:codeconnections:us-west-1:659613508664:connection/4ea8863c-728d-450a-8752-251946939b36 \
    RepositoryId=kalla86840/awspineconeragforchatbotsandassistants \
    BranchName=main \
    DeployEnvironment=staging \
    OpenAIApiKeySecretArn=arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ

