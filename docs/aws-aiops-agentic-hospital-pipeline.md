# AWS AIOps Agentic Hospital CI/CD Pipeline

This package adds an AWS AIOps-style CI/CD path for a real-time OpenAI agentic RAG hospital endpoint. The runtime endpoint is `agentic_endpoint/app.py`, deployed by CodePipeline and CodeBuild as a Lambda Function URL.

## Agentic Task

Task: use retrieved hospital operations context plus three OpenAI agent passes to create a real-time care-coordination inference for an acute hospital event.

Agent sequence:

1. `hospital`: operational intake, capacity constraints, missing coordination data.
2. `doctor`: clinical review, risk considerations, escalation needs.
3. `nurse`: bedside handoff, monitoring priorities, practical next actions.

The endpoint first retrieves relevant sections from `agentic_endpoint/hospital_agentic_rag_knowledge.txt`, passes that context to each agent, and then runs a coordinator pass. The structured response includes `retrieved_context`, each agent output, and final JSON with `case_summary`, `care_team_consensus`, `recommended_actions`, `signals_to_monitor`, `escalation_level`, and `handoff`.

## CI/CD Flow

```text
GitHub source repository
  -> AWS CodePipeline source stage
  -> AWS CodeBuild project aws-autogen-open-ai-pincone-agentic-deploy
  -> Package agentic_endpoint/app.py, agent_profiles.yaml, RAG text file, and dependencies
  -> Upload dist/agentic-endpoint.zip to S3
  -> CloudFormation deploy infrastructure/agentic-endpoint.yaml
  -> Lambda Function URL real-time endpoint
  -> Invoke aws-autogen-open-ai-pincone-agentic-endpoint with samples/agentic_hospital_request.json
  -> POST hospital event JSON for OpenAI-backed agentic RAG inference
```

## Real-Time Endpoint Reference

The endpoint is created by `infrastructure/agentic-endpoint.yaml`.

CloudFormation output:

```text
AgenticFunctionUrl
```

Endpoint behavior:

```text
POST https://<lambda-function-url-id>.lambda-url.<region>.on.aws/
Authorization: AWS_IAM
Content-Type: application/json
```

The CodePipeline stack is defined in `infrastructure/agentic-cicd.yaml`, and the deployment build is defined in `buildspec-agentic.yml`.

## RAG Text File

The endpoint packages and reads:

```text
agentic_endpoint/hospital_agentic_rag_knowledge.txt
```

The file is split on blank lines into retrievable sections. It contains the agentic task contract, agent guidance, escalation mapping, safety boundary, and sample event patterns for ED chest pressure and dyspnea, post-operative fever, and telemetry rhythm alerts. The request can set `rag_top_k`; otherwise the endpoint uses `RAG_TOP_K=4`.

## Meaningful Data

Sample hospital events live in:

```text
data/hospital_aiops/patient_events.jsonl
```

The primary sample request lives in:

```text
samples/agentic_hospital_request.json
```

The sample inference output lives in:

```text
samples/agentic_hospital_sample_inference.json
```

## Deploy Pipeline

```bash
aws cloudformation deploy \
  --template-file infrastructure/agentic-cicd.yaml \
  --stack-name aws-autogen-open-ai-pincone-cicd \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName=aws-autogen-open-ai-pincone \
    ArtifactBucketName=mlopswithsagemaker111 \
    CodeStarConnectionArn=arn:aws:codeconnections:us-west-1:659613508664:connection/4ea8863c-728d-450a-8752-251946939b36 \
    RepositoryId=kalla86840/awspineconeragforchatbotsandassistants \
    BranchName=main \
    OpenAIApiKeySecretArn=arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ \
    OpenAIModel=gpt-5.2
```

## Invoke Endpoint

After deployment, use the `AgenticFunctionUrl` CloudFormation output with a SigV4-capable HTTP client because the Function URL uses `AWS_IAM` auth:

```bash
curl \
  --request POST "$AGENTIC_FUNCTION_URL" \
  --aws-sigv4 "aws:amz:us-west-1:lambda" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  --header "x-amz-security-token: $AWS_SESSION_TOKEN" \
  --header "content-type: application/json" \
  --data-binary @samples/agentic_hospital_request.json
```

For direct Lambda testing inside AWS, invoke the function by name:

```bash
aws lambda invoke \
  --function-name aws-autogen-open-ai-pincone-agentic-endpoint \
  --payload fileb://samples/agentic_hospital_request.json \
  response.json
```

The expected response shape is shown in `samples/agentic_hospital_sample_inference.json`.

