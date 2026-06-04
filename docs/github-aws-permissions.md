# GitHub AWS Permissions

GitHub should use AWS OIDC instead of long-lived AWS access keys. The workflow in this repo requests only:

```yaml
permissions:
  contents: read
  id-token: write
```

AWS grants deployment permissions through the IAM role created by:

```text
infrastructure/github-aws-oidc-role.yaml
```

## Deploy The AWS OIDC Role

Run this once from an AWS-authenticated terminal:

```powershell
aws cloudformation deploy `
  --region us-west-1 `
  --template-file infrastructure/github-aws-oidc-role.yaml `
  --stack-name awsmcpops-github-aws-oidc-role `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides `
    ProjectName=awsmcpops `
    GitHubOwner=kalla86840 `
    GitHubRepo=awsmcpops `
    GitHubBranch=main `
    ArtifactBucketName=mlopswithsagemaker111 `
    OpenAIApiKeySecretArn=arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ `
    PineconeApiKeySecretArn=arn:aws:secretsmanager:us-west-1:659613508664:secret:awspineconeapikey1-kiudra
```

If the AWS account already has an IAM OIDC provider for GitHub, add:

```powershell
ExistingGitHubOidcProviderArn=arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com
```

Then get the role ARN:

```powershell
aws cloudformation describe-stacks `
  --region us-west-1 `
  --stack-name awsmcpops-github-aws-oidc-role `
  --query "Stacks[0].Outputs[?OutputKey=='GitHubActionsRoleArn'].OutputValue | [0]" `
  --output text
```

## GitHub Repository Secrets

Set these under GitHub repository settings:

```text
AWS_ROLE_ARN
OPENAI_API_KEY_SECRET_ARN
PINECONE_API_KEY_SECRET_ARN
```

Optional, only when using the manual workflow input to deploy/update the AWS CodePipeline stack:

```text
CODESTAR_CONNECTION_ARN
```

## GitHub Repository Variables

Set these under repository variables:

```text
AWS_REGION=us-west-1
PROJECT_NAME=awsmcpops
ENDPOINT_STACK_NAME=awsmcpops-realtime-inference-endpoint
PIPELINE_STACK_NAME=awsmcpops-realtime-inference-pipeline
ARTIFACT_BUCKET=mlopswithsagemaker111
OPENAI_MODEL=gpt-5.2
PINECONE_INDEX_NAME=awsmcpops-realtime-inference-1024
PINECONE_INDEX_HOST=
PINECONE_NAMESPACE=news
PINECONE_MEMORY_NAMESPACE=agent-memory
PINECONE_DUPLICATE_NAMESPACE=news
PINECONE_CLASSIFICATION_NAMESPACE=news
PINECONE_CLUSTERING_NAMESPACE=news
PINECONE_MULTIMODAL_NAMESPACE=news
PINECONE_DIMENSION=1024
PINECONE_UPSERT_ON_QUERY=true
DUPLICATE_SCORE_THRESHOLD=0.98
SIMILARITY_SCORE_THRESHOLD=0.85
```

## AWS Permissions Included

The OIDC role grants the deployment actions required by this repo:

```text
CloudFormation stack deploy/update
Lambda function and Function URL deploy/update
S3 artifact upload/read for the configured artifact bucket
Secrets Manager read for the configured OpenAI and Pinecone secrets
IAM role/policy operations for CloudFormation-managed awsmcpops roles
Optional CodeBuild/CodePipeline/CodeConnections actions for the pipeline stack
CloudWatch Logs diagnostics
```

The trust policy is limited to:

```text
repo:kalla86840/awsmcpops:ref:refs/heads/main
```

That is the important guardrail: GitHub receives no stored AWS key, and only this repo branch can assume the role.
