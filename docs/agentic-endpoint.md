# OpenAI Agentic Hospital Endpoint

This endpoint creates a real-time agentic RAG inference workflow for hospital coordination. It receives a hospital event, retrieves relevant context from a packaged text file, runs three OpenAI-backed agents, and returns structured JSON for care coordination.

## Files

- `agentic_endpoint/app.py`: Lambda handler.
- `agentic_endpoint/agent_profiles.yaml`: Hospital, doctor, and nurse agent prompts.
- `agentic_endpoint/hospital_agentic_rag_knowledge.txt`: RAG text file bundled with the endpoint.
- `agentic_endpoint/requirements.txt`: Lambda package dependencies.
- `infrastructure/agentic-endpoint.yaml`: Lambda Function URL CloudFormation template.
- `infrastructure/agentic-cicd.yaml`: CodePipeline/CodeBuild template for the endpoint.
- `buildspec-agentic.yml`: Packages and deploys the Lambda endpoint.
- `tests/agentic_event.json`: Example hospital event.

## Request

```json
{
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

- `hospital`: operational intake and coordination gaps.
- `doctor`: clinical review and escalation considerations.
- `nurse`: bedside handoff, monitoring priorities, and practical next actions.

The endpoint retrieves relevant RAG sections and passes them to every agent. It then runs a final coordinator pass that returns `retrieved_context`, agent outputs, and a structured inference with `case_summary`, `care_team_consensus`, `recommended_actions`, `signals_to_monitor`, `escalation_level`, and `handoff`.

## Deploy

Create the CI/CD pipeline:

```bash
aws cloudformation deploy \
  --template-file infrastructure/agentic-cicd.yaml \
  --stack-name agentic-open-ai-cicd \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName=agentic-open-ai \
    ArtifactBucketName=mlopswithsagemaker111 \
    CodeStarConnectionArn=arn:aws:codeconnections:us-west-1:659613508664:connection/4ea8863c-728d-450a-8752-251946939b36 \
    RepositoryId=kalla86840/awspineconeragforchatbotsandassistants \
    BranchName=main \
    OpenAIApiKeySecretArn=arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ \
    OpenAIModel=gpt-5.2
```

The pipeline is named `agentic-open-ai`. It creates a CodeBuild project named `agentic-open-ai-agentic-deploy`. CodeBuild packages the Lambda artifact and deploys `infrastructure/agentic-endpoint.yaml`.

