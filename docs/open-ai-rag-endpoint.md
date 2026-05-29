# OpenAI RAG Endpoint

This endpoint is a real-time AWS Lambda Function URL for OpenAI-backed multi-agent RAG inference. It retrieves context from a bundled `.txt` file, calls multiple OpenAI agents with the retrieved sections, and returns a final answer with agent outputs, steps, safety notes, citations, and retrieved context.

## Files

- `rag_endpoint/app.py`: Lambda handler and retrieval logic.
- `rag_endpoint/knowledge/open_ai_rag_knowledge.txt`: Plain text RAG source file.
- `rag_endpoint/requirements.txt`: Lambda package dependencies.
- `infrastructure/open-ai-rag-endpoint.yaml`: Lambda Function URL CloudFormation template.
- `infrastructure/open-ai-rag-endpoint-cicd.yaml`: CodePipeline/CodeBuild template for the endpoint.
- `buildspec-open-ai-rag-endpoint.yml`: Packages, deploys, and smoke-tests the endpoint.
- `docs/pinecone-semantic-search-task.txt`: Pinecone recommendation systems setup and test runbook.
- `samples/open_ai_rag_endpoint_request.json`: Example request.
- `samples/open_ai_rag_endpoint_response.example.json`: Example response.

## Request

```json
{
  "question": "How do I connect a washer and dryer?",
  "top_k": 8,
  "agents": [
    "manual_retrieval_agent",
    "procedure_agent",
    "safety_agent"
  ]
}
```

The default agents are:

- `manual_retrieval_agent`: document retrieval analyst.
- `procedure_agent`: step-by-step procedure specialist.
- `safety_agent`: safety and escalation reviewer.

## Response

The endpoint returns:

```json
{
  "question": "How do I connect a washer and dryer?",
  "agents": [],
  "answer": "OpenAI-generated answer grounded in retrieved context.",
  "steps": [],
  "safety_notes": [],
  "citations": [
    {
      "id": "doc-3",
      "title": "Washer Water Connections"
    }
  ],
  "agent_consensus": "Summary of how the agents agree.",
  "retrieved_context": []
}
```

## Deploy

Create the CI/CD pipeline:

```bash
aws cloudformation deploy \
  --region us-west-1 \
  --template-file infrastructure/open-ai-rag-endpoint-cicd.yaml \
  --stack-name open-ai-pinecone-duplicate-detection-cicd \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName=open-ai-pinecone-duplicate-detection \
    PipelineName=open-ai-pinecone-duplicate-detection \
    ArtifactBucketName=mlopswithsagemaker111 \
    CodeStarConnectionArn=arn:aws:codeconnections:us-west-1:659613508664:connection/4ea8863c-728d-450a-8752-251946939b36 \
    RepositoryId=kalla86840/awspineconeduplicateorsimilaritydetection \
    BranchName=main \
    OpenAIApiKeySecretArn=arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ \
    PineconeApiKeySecretArn=arn:aws:secretsmanager:us-west-1:659613508664:secret:awspineconeapikey1-kiudra \
    PineconeIndexName=news-demo \
    PineconeIndexHost=https://news-demo-4fe9eo0.svc.aped-4627-b74a.pinecone.io \
    PineconeNamespace=news \
    PineconeDuplicateNamespace=news \
    DuplicateScoreThreshold=0.98 \
    SimilarityScoreThreshold=0.85
```

The pipeline name is `open-ai-pinecone-duplicate-detection`. It deploys the `open-ai-pinecone-duplicate-detection-endpoint` stack. Use the `EndpointUrl` output for real-time inference.

Run the Pinecone recommendation systems task:

```bash
curl -X POST "$ENDPOINT_URL" \
  -H "content-type: application/json" \
  -d @samples/pinecone_recommendations_request.json
```

Run a Pinecone semantic search compatibility task:

```bash
curl -X POST "$ENDPOINT_URL" \
  -H "content-type: application/json" \
  -d @samples/pinecone_semantic_search_request.json
```


