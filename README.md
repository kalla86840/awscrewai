# Build Agentic RAG Pipeline

This repository contains AWS CI/CD pipelines for OpenAI-backed real-time RAG endpoints.

It now includes two deployable endpoint paths:

1. `rag_endpoint/`: a multi-agent OpenAI RAG Lambda Function URL that retrieves from a plain text knowledge file and applies multiple agents before returning an answer.
2. `agentic_endpoint/`: an agentic hospital RAG Lambda Function URL that retrieves hospital context, runs three OpenAI agents, and returns a structured care-coordination inference.

## Recommendation Systems

This repository is centered on a Pinecone recommendation systems endpoint. It
uses OpenAI `text-embedding-3-small` with `PINECONE_DIMENSION=1024`, so the
target Pinecone index must also be created with dimension `1024`.

The endpoint recommends similar records by embedding a `seed_text`, known
Pinecone `seed_id`, or user interest profile and querying the
`open-ai-pinecone-duplicate-detection-1024` Pinecone index in real time.

## Validated Pipeline Configuration

The successful CodePipeline deployment uses the dedicated
`open-ai-pinecone-duplicate-detection-1024` Pinecone index. The Lambda endpoint,
CodeBuild environment, CloudFormation templates, and deployment examples all
use `PINECONE_DIMENSION=1024`. CI leaves `PINECONE_INDEX_HOST` empty so the
endpoint creates or uses the correctly dimensioned index by name, seeds the
bundled RAG documents, and verifies the real-time Lambda Function URL with
recommendation and semantic-search smoke tests.

The local detector is still available for finding exact duplicate files and
near-similar text/code files across generated packages:

```powershell
python scripts/detect_similarity.py --root . --threshold 0.95 --min-size 20 --exclude downloads --exclude *.zip
```

Useful options:

- `--threshold`: Jaccard similarity threshold for near-matches. Default is `0.85`.
- `--limit`: Max duplicate groups and similar pairs shown in text output. Use `0` for all.
- `--format json`: Emit a machine-readable report.
- `--csv report.csv`: Write near-similar pairs to CSV.

## Architecture

```text
GitHub repository
  -> AWS CodePipeline
  -> AWS CodeBuild packages endpoint code, dependencies, and RAG text files
  -> CodeBuild uploads Lambda artifacts to S3
  -> CloudFormation deploys Lambda Function URL endpoints
  -> Lambda embeds the query with OpenAI and retrieves relevant RAG context from Pinecone
  -> Lambda calls OpenAI
  -> Endpoint returns ranked recommendations or grounded real-time inference
```

## Standalone OpenAI RAG Endpoint

This endpoint answers questions from a bundled `.txt` user manual using multiple OpenAI agents. The Lambda loads `rag_endpoint/knowledge/open_ai_rag_knowledge.txt`, splits it into retrievable sections, embeds sections with OpenAI, upserts them into Pinecone, retrieves the most relevant sections for the user question, runs three agents over that retrieved context, and returns a final synthesized answer.

Open the deployed Lambda Function URL in a browser to use the chat interface.
The same URL accepts `POST` requests for API integrations and terminal tests.

Runtime files:

```text
rag_endpoint/app.py
rag_endpoint/chat.html
rag_endpoint/requirements.txt
rag_endpoint/knowledge/open_ai_rag_knowledge.txt
```

AWS pipeline files:

```text
buildspec-open-ai-rag-endpoint.yml
infrastructure/open-ai-rag-endpoint.yaml
infrastructure/open-ai-rag-endpoint-cicd.yaml
```

Sample files:

```text
samples/open_ai_rag_endpoint_request.json
samples/open_ai_rag_endpoint_response.example.json
samples/pinecone_chatbot_assistant_rag_request.json
samples/pinecone_semantic_search_request.json
samples/pinecone_multimodal_retrieval_request.json
samples/pinecone_recommendations_request.json
samples/pinecone_agent_memory_request.json
samples/pinecone_duplicate_similarity_request.json
```

Request shape:

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

Pinecone recommendation systems task:

```json
{
  "mode": "recommendations",
  "seed_text": "Recent earnings call transcripts and market news mentioning edge cloud, content delivery, and EGIO.",
  "interests": [
    "earnings calls",
    "edge cloud",
    "content delivery",
    "EGIO"
  ],
  "top_k": 5
}
```

You can also send `seed_id` instead of `seed_text` when you want recommendations
similar to a known Pinecone record. The endpoint excludes that seed record from
the returned `recommendations`.

Pinecone semantic search compatibility task:

```json
{
  "mode": "semantic_search",
  "question": "What safety checks are required before connecting laundry equipment?",
  "top_k": 5
}
```

Pinecone RAG for chatbots and assistants task:

```json
{
  "mode": "chatbot_rag",
  "conversation_id": "demo-chatbot-session-001",
  "assistant_id": "support-assistant",
  "question": "What context should the assistant use before answering a support question about edge cloud and content delivery?",
  "top_k": 5
}
```

Use `mode: "assistant_rag"` or `mode: "chatbot_assistant"` for the same
Pinecone-backed multi-agent answer path when naming the task for assistants.

Pinecone multimodal retrieval task:

```json
{
  "mode": "multimodal_retrieval",
  "question": "Find Pinecone records related to this image and edge cloud earnings context.",
  "image_urls": [
    "https://images.unsplash.com/photo-1558494949-ef010cbdcc31"
  ],
  "metadata": {
    "domain": "edge cloud",
    "ticker": "EGIO"
  },
  "top_k": 5
}
```

The endpoint uses OpenAI vision to describe submitted images, fuses those image
descriptions with the text query and metadata, embeds the fused query, and
retrieves matching records from Pinecone.

Pinecone memory for AI agents task:

```json
{
  "mode": "agent_memory",
  "action": "write",
  "agent_id": "research-agent",
  "task_id": "pinecone-memory-ci",
  "memory_type": "episodic",
  "content": "The agent deployed an AWS Lambda Function URL through CodePipeline, used OpenAI embeddings, stored task memory in Pinecone, and verified retrieval for future AI agent context.",
  "query": "What did the agent verify during the CodePipeline Pinecone memory task?",
  "top_k": 3
}
```

Use `action: "search"` with `query`, plus optional `agent_id`, `task_id`, or
`memory_type`, to recall stored memories from the Pinecone memory namespace.

Pinecone classification and clustering support task:

```json
{
  "mode": "classification_clustering",
  "text": "Recent market news about edge cloud, content delivery, and EGIO earnings momentum.",
  "top_k": 8,
  "n_clusters": 3,
  "label_field": "category",
  "namespace": "news"
}
```

The endpoint embeds the submitted text with OpenAI, queries Pinecone in real
time, predicts a label from weighted neighbor metadata, and clusters the
returned Pinecone vectors. Use `mode: "classification"` for classification-only
responses or `mode: "clustering"` for clustering-only responses.

Pinecone duplicate or similarity detection task:

```json
{
  "mode": "duplicate_similarity",
  "candidate_id": "candidate-egio-edge-cloud-news",
  "candidate_text": "Recent market news and earnings call transcripts discussing EGIO, edge cloud services, content delivery, and infrastructure strategy.",
  "top_k": 5,
  "duplicate_threshold": 0.98,
  "similarity_threshold": 0.85
}
```

The endpoint embeds the candidate with OpenAI, queries Pinecone, and classifies
matches as `duplicate`, `similar`, or `related` by score threshold.

Agent sequence:

- `manual_retrieval_agent`: identifies the most relevant manual sections and citations.
- `procedure_agent`: turns retrieved context into ordered steps.
- `safety_agent`: extracts warnings, stop conditions, and professional escalation guidance.

The endpoint response includes `agents`, `answer`, `steps`, `safety_notes`, `citations`, `agent_consensus`, and `retrieved_context`.

After deployment, get the URL from the `open-ai-pinecone-duplicate-detection-endpoint` CloudFormation stack output named `EndpointUrl`. The CodePipeline name is `open-ai-pinecone-duplicate-detection`.

## Agentic Hospital RAG Endpoint

This endpoint uses OpenAI to run three agents:

- Agent 1: `hospital`, for operational intake and coordination.
- Agent 2: `doctor`, for clinical review and escalation considerations.
- Agent 3: `nurse`, for bedside handoff and monitoring priorities.

Runtime files:

```text
agentic_endpoint/app.py
agentic_endpoint/agent_profiles.yaml
agentic_endpoint/hospital_agentic_rag_knowledge.txt
agentic_endpoint/requirements.txt
```

AWS pipeline files:

```text
buildspec-agentic.yml
infrastructure/agentic-endpoint.yaml
infrastructure/agentic-cicd.yaml
```

Sample files:

```text
data/hospital_aiops/patient_events.jsonl
samples/agentic_hospital_request.json
samples/agentic_hospital_sample_inference.json
```

After deployment, get the URL from the `agentic-open-ai-agentic-endpoint` CloudFormation stack output named `AgenticFunctionUrl`.

## AWS And OpenAI Configuration

The OpenAI API key comes from OpenAI. Store it in AWS Secrets Manager and pass the secret ARN to the pipeline. The Pinecone API key comes from Pinecone and is also stored in AWS Secrets Manager.

The AWS defaults currently filled in are:

- Region: `us-west-1`
- Artifact bucket: `mlopswithsagemaker111`
- CodeStar connection: `arn:aws:codeconnections:us-west-1:659613508664:connection/4ea8863c-728d-450a-8752-251946939b36`
- GitHub repository: `kalla86840/awspineconeragforchatbotsandassistants`
- OpenAI secret ARN: `arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ`
- Pinecone secret ARN: `arn:aws:secretsmanager:us-west-1:659613508664:secret:awspineconeapikey1-kiudra`
- Pinecone index: `open-ai-pinecone-duplicate-detection-1024`
- Pinecone host: empty by default so the endpoint creates/uses the named 1024-dimensional index.
- Pinecone namespace: `news`
- Pinecone memory namespace: `agent-memory`
- Pinecone duplicate namespace: `news`
- Pinecone classification namespace: `news`
- Pinecone clustering namespace: `news`
- Pinecone multimodal namespace: `news`
- Pinecone dimension: `1024`
- Duplicate score threshold: `0.98`
- Similarity score threshold: `0.85`
- Pinecone upsert on query: `true`, so CI seeds the 1024-dimensional index before smoke tests.

Update an existing secret:

```bash
aws secretsmanager put-secret-value \
  --region us-west-1 \
  --secret-id openai/api-key \
  --secret-string "sk-your-openai-api-key"
```

Create or update the Pinecone secret:

```bash
aws secretsmanager create-secret \
  --region us-west-1 \
  --name awspineconeapikey1 \
  --secret-string "pcsk-your-pinecone-api-key"

aws secretsmanager put-secret-value \
  --region us-west-1 \
  --secret-id awspineconeapikey1 \
  --secret-string "pcsk-your-pinecone-api-key"
```

If the pipeline parameter needs the full Pinecone secret ARN, capture it after
creation:

```bash
aws secretsmanager describe-secret \
  --region us-west-1 \
  --secret-id awspineconeapikey1 \
  --query ARN \
  --output text
```

## Deploy Standalone RAG Endpoint Pipeline

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
    RepositoryId=kalla86840/awspineconeragforchatbotsandassistants \
    BranchName=main \
    OpenAIApiKeySecretArn=arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ \
    PineconeApiKeySecretArn=arn:aws:secretsmanager:us-west-1:659613508664:secret:awspineconeapikey1-kiudra \
    PineconeIndexName=open-ai-pinecone-duplicate-detection-1024 \
    PineconeIndexHost="" \
    PineconeNamespace=news \
    PineconeMemoryNamespace=agent-memory \
    PineconeDuplicateNamespace=news \
    PineconeClassificationNamespace=news \
    PineconeClusteringNamespace=news \
    PineconeMultimodalNamespace=news \
    PineconeDimension=1024 \
    PineconeUpsertOnQuery=true \
    DuplicateScoreThreshold=0.98 \
    SimilarityScoreThreshold=0.85
```

Invoke after deployment:

```bash
curl -X POST "$ENDPOINT_URL" \
  -H "content-type: application/json" \
  -d @samples/open_ai_rag_endpoint_request.json
```

Run the Pinecone recommendation systems task:

```bash
curl -X POST "$ENDPOINT_URL" \
  -H "content-type: application/json" \
  -d @samples/pinecone_recommendations_request.json
```

Run the Pinecone semantic search compatibility task:

```bash
curl -X POST "$ENDPOINT_URL" \
  -H "content-type: application/json" \
  -d @samples/pinecone_semantic_search_request.json
```

Run the Pinecone multimodal retrieval task:

```bash
curl -X POST "$ENDPOINT_URL" \
  -H "content-type: application/json" \
  -d @samples/pinecone_multimodal_retrieval_request.json
```

Run the Pinecone memory for AI agents task:

```bash
curl -X POST "$ENDPOINT_URL" \
  -H "content-type: application/json" \
  -d @samples/pinecone_agent_memory_request.json
```

Run the Pinecone duplicate or similarity detection task:

```bash
curl -X POST "$ENDPOINT_URL" \
  -H "content-type: application/json" \
  -d @samples/pinecone_duplicate_similarity_request.json
```

Run the Pinecone classification and clustering support task:

```bash
curl -X POST "$ENDPOINT_URL" \
  -H "content-type: application/json" \
  -d @samples/pinecone_classification_clustering_request.json
```

## Deploy Agentic Hospital RAG Pipeline

```bash
aws cloudformation deploy \
  --region us-west-1 \
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

Because the agentic endpoint uses `AWS_IAM` auth, invoke it with a SigV4-capable client:

```bash
curl \
  --request POST "$AGENTIC_FUNCTION_URL" \
  --aws-sigv4 "aws:amz:us-west-1:lambda" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  --header "x-amz-security-token: $AWS_SESSION_TOKEN" \
  --header "content-type: application/json" \
  --data-binary @samples/agentic_hospital_request.json
```

## Local Validation

```bash
python -m compileall rag_endpoint agentic_endpoint src scripts pipelines
python -c "from rag_endpoint.app import load_documents, retrieve; docs=load_documents('rag_endpoint/knowledge/open_ai_rag_knowledge.txt'); print([d['title'] for d in retrieve('How do I connect a washer and dryer?', docs, 8)])"
python -c "import sys, types, json; sys.modules['boto3']=types.SimpleNamespace(client=lambda *a, **k: None); sys.modules['openai']=types.SimpleNamespace(OpenAI=object); sys.modules['yaml']=types.SimpleNamespace(safe_load=lambda f: {}); import agentic_endpoint.app as app; payload=json.load(open('samples/agentic_hospital_request.json', encoding='utf-8')); print([d['title'] for d in app.retrieve_context(payload)])"
```


