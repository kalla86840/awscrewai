# OpenAI Agentic Hospital Endpoint

This endpoint creates a real-time agentic RAG inference workflow for hospital coordination. It receives a hospital event, retrieves relevant context through Pinecone when a Pinecone secret is configured, falls back to packaged keyword retrieval when Pinecone is not configured, runs three CrewAI agents backed by OpenAI, and returns structured JSON for care coordination.

## Files

- `agentic_endpoint/app.py`: Lambda handler.
- `agentic_endpoint/agent_profiles.yaml`: Hospital, doctor, and nurse agent prompts.
- `agentic_endpoint/hospital_agentic_rag_knowledge.txt`: RAG text file bundled with the endpoint.
- `agentic_endpoint/requirements.txt`: Lambda package dependencies.
- `agentic_endpoint/Dockerfile`: Lambda container image definition for CrewAI dependencies.
- `infrastructure/agentic-endpoint.yaml`: Lambda Function URL CloudFormation template.
- `infrastructure/agentic-cicd.yaml`: CodePipeline/CodeBuild template for the endpoint.
- `buildspec-agentic.yml`: Packages and deploys the Lambda endpoint.
- `tests/agentic_event.json`: Example hospital event.

## Request

```json
{
  "agents": ["agent_1", "agent_2", "agent_3"],
  "patient_context": {
    "age": 64,
    "location": "emergency department",
    "arrival_mode": "ambulance"
  },
  "chief_concern": "Shortness of breath and chest pressure for two hours.",
  "vitals": {
    "heart_rate": 118,
    "blood_pressure": "92/58",
    "oxygen_saturation": 89,
    "temperature_f": 99.1
  },
  "notes": [
    "History of hypertension.",
    "Patient reports worsening symptoms when walking."
  ],
  "requested_inference": "Coordinate immediate triage, clinical review, and bedside handoff priorities."
}
```

## Agent Coordination

The default agent sequence is:

- `agent_1` / `hospital`: operational intake and coordination gaps.
- `agent_2` / `doctor`: clinical review and escalation considerations.
- `agent_3` / `nurse`: bedside handoff, monitoring priorities, and practical next actions.

The endpoint retrieves relevant RAG sections and passes them to every agent. It then runs a final coordinator pass that returns `retrieved_context`, agent outputs, and a structured inference with `case_summary`, `care_team_consensus`, `recommended_actions`, `signals_to_monitor`, `escalation_level`, and `handoff`.

Pinecone retrieval is controlled by these deployment parameters and Lambda environment variables:

- `PineconeApiKeySecretArn`: optional Secrets Manager ARN for the Pinecone API key. Leave it empty to use keyword retrieval only.
- `PineconeIndexName`: default `agentic-hospital-rag-1024`.
- `PineconeIndexHost`: optional existing Pinecone host. Leave empty to create or reuse `PineconeIndexName`.
- `PineconeNamespace`: default `hospital-agentic`.
- `PineconeDimension`: default `1024`, matching `text-embedding-3-small` with a 1024-dimensional embedding request.
- `PineconeUpsertOnQuery`: default `true`, so the bundled hospital knowledge is seeded before querying.

Request payloads can set `"disable_pinecone": true` for keyword retrieval or `"strict_pinecone": true` to fail instead of falling back when Pinecone returns an error.

## Deploy

Create the CI/CD pipeline:

```bash
aws cloudformation deploy \
  --template-file infrastructure/agentic-cicd.yaml \
  --stack-name aws-autogen-open-ai-pincone-cicd \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName=aws-autogen-open-ai-pincone \
    ArtifactBucketName=mlopswithsagemaker111 \
    CodeStarConnectionArn=arn:aws:codeconnections:us-west-1:659613508664:connection/4ea8863c-728d-450a-8752-251946939b36 \
    RepositoryId=kalla86840/awscrewai \
    BranchName=main \
    OpenAIApiKeySecretArn=arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ \
    OpenAIModel=gpt-5.2 \
    PineconeApiKeySecretArn="" \
    PineconeIndexName=agentic-hospital-rag-1024 \
    PineconeIndexHost="" \
    PineconeNamespace=hospital-agentic \
    PineconeDimension=1024 \
    PineconeCloud=aws \
    PineconeRegion=us-east-1 \
    PineconeUpsertOnQuery=true
```

Set `PineconeApiKeySecretArn` to your Pinecone Secrets Manager ARN when you want Pinecone-backed retrieval. The pipeline is named `aws-autogen-open-ai-pincone`. It creates a CodeBuild project named `aws-autogen-open-ai-pincone-agentic-deploy` and an ECR repository for the endpoint image. CodeBuild builds the CrewAI Lambda container image, pushes it to ECR, deploys `infrastructure/agentic-endpoint.yaml`, and writes the produced Lambda Function URL to `dist/agentic-endpoint-url.txt` as a build artifact.

The pipeline smoke test uses `dry_run: true` to validate the deployed AWS endpoint without calling OpenAI during deployment. Remove `dry_run` from inference requests to run the live CrewAI/OpenAI workflow.

By default, the Lambda Function URL uses `FunctionUrlAuthType=NONE` so the pipeline produces a directly callable HTTPS endpoint. Override it to `AWS_IAM` in `infrastructure/agentic-endpoint.yaml` deployments when signed requests are required.
