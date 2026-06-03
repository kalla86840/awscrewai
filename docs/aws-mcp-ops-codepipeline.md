# AWS MCP Ops CodePipeline

This repo is configured to deploy a real-time OpenAI/Pinecone inference endpoint from GitHub through AWS CodePipeline.

## GitHub Source

Use the repository shown in the screenshot:

```text
kalla86840/awsmcpops
```

The pipeline watches the `main` branch by default.

## What Gets Deployed

```text
GitHub awsmcpops repo
  -> AWS CodePipeline source stage
  -> AWS CodeBuild package/deploy stage
  -> S3 Lambda deployment artifact
  -> CloudFormation endpoint stack
  -> Lambda Function URL for real-time inferencing
  -> OpenAI model call with optional Pinecone retrieval
```

Runtime endpoint files:

```text
rag_endpoint/app.py
rag_endpoint/chat.html
rag_endpoint/requirements.txt
rag_endpoint/knowledge/open_ai_rag_knowledge.txt
```

AWS files:

```text
buildspec-open-ai-rag-endpoint.yml
infrastructure/open-ai-rag-endpoint.yaml
infrastructure/open-ai-rag-endpoint-cicd.yaml
infrastructure/open-ai-rag-endpoint-cicd-parameters.example.json
infrastructure/open-ai-rag-endpoint-cicd-parameters.example.env
```

## Required AWS Inputs

Create these before deploying the pipeline:

```text
ArtifactBucketName        S3 bucket for CodePipeline and Lambda zips
CodeStarConnectionArn     AWS CodeConnections connection authorized for GitHub
OpenAIApiKeySecretArn     Secrets Manager ARN containing the OpenAI API key
PineconeApiKeySecretArn   Secrets Manager ARN containing the Pinecone API key
```

The provided examples currently default to:

```text
ProjectName=awsmcpops
PipelineName=awsmcpops-realtime-inference
RepositoryId=kalla86840/awsmcpops
BranchName=main
PineconeIndexName=awsmcpops-realtime-inference-1024
PineconeDimension=1024
```

## Deploy The Pipeline

Update the values in `infrastructure/open-ai-rag-endpoint-cicd-parameters.example.json`, especially the artifact bucket, connection ARN, and secret ARNs. Then deploy:

```powershell
aws cloudformation deploy `
  --region us-west-1 `
  --template-file infrastructure/open-ai-rag-endpoint-cicd.yaml `
  --stack-name awsmcpops-realtime-inference-pipeline `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides file://infrastructure/open-ai-rag-endpoint-cicd-parameters.example.json
```

After the stack is created, commit and push the repo to `kalla86840/awsmcpops`. CodePipeline will run automatically.

## Get The Real-Time Endpoint URL

When the pipeline completes, read the endpoint stack output:

```powershell
aws cloudformation describe-stacks `
  --region us-west-1 `
  --stack-name awsmcpops-realtime-inference-endpoint `
  --query "Stacks[0].Outputs[?OutputKey=='EndpointUrl'].OutputValue | [0]" `
  --output text
```

## Test Inferencing

Replace `$ENDPOINT_URL` with the Lambda Function URL from the previous command:

```powershell
curl.exe -sS -X POST "$ENDPOINT_URL" `
  -H "content-type: application/json" `
  -d "@samples/pinecone_semantic_search_request.json"
```

For browser testing, open the same Function URL with `GET`; it serves the bundled chat UI.

## Notes

OpenAI model, embedding model, Pinecone index, namespace, and thresholds are environment-driven. Keep real API keys in Secrets Manager only; do not commit them to GitHub.
