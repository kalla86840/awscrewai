# OpenAI Prompt Ops AIOps Endpoint

This endpoint is for prompt engineering and AIOps inference. It does not train or host a SageMaker model. It receives an operations event, selects a prompt profile, calls the OpenAI Responses API, and returns structured JSON for triage or remediation.

## Files

- `aiops_endpoint/app.py`: Lambda handler.
- `aiops_endpoint/prompt_profiles.yaml`: Editable prompt profiles.
- `aiops_endpoint/requirements.txt`: Lambda package dependencies.
- `infrastructure/aiops-endpoint.yaml`: Lambda Function URL CloudFormation template.
- `infrastructure/aiops-cicd.yaml`: CodePipeline/CodeBuild template for the AIOps endpoint.
- `buildspec-aiops.yml`: Packages and deploys the Lambda endpoint.
- `tests/aiops_event.json`: Example incident event.

## Request

```json
{
  "profile": "incident_triage",
  "service": "checkout-api",
  "environment": "production",
  "event": "HTTP 5xx rate increased after deployment.",
  "metrics": {
    "p95_latency_ms": 2400,
    "error_rate_percent": 8.7
  },
  "logs": [
    "TimeoutError: payment provider request exceeded 2000ms"
  ],
  "runbook_context": "Rollback is available through CodeDeploy.",
  "prompt_notes": "Keep output short enough for an on-call Slack message."
}
```

## Prompt Engineering

Edit `aiops_endpoint/prompt_profiles.yaml` to tune behavior. The built-in profiles are:

- `incident_triage`
- `remediation_plan`
- `prompt_review`

You can also pass `instructions` in the request body for one-off prompt experiments.

## Deploy

Create the CI/CD pipeline:

```bash
aws cloudformation deploy \
  --template-file infrastructure/aiops-cicd.yaml \
  --stack-name openai-prompt-ops-aiops-cicd \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName=openai-prompt-ops \
    ArtifactBucketName=mlopswithsagemaker111 \
    CodeStarConnectionArn=arn:aws:codeconnections:us-west-1:659613508664:connection/4ea8863c-728d-450a-8752-251946939b36 \
    RepositoryId=kalla86840/awspineconeragforchatbotsandassistants \
    BranchName=main \
    OpenAIApiKeySecretArn=arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ \
    OpenAIModel=gpt-5.2
```

The pipeline creates a CodeBuild project named `openai-prompt-ops-aiops-deploy`. CodeBuild packages the Lambda artifact and deploys `infrastructure/aiops-endpoint.yaml`.

