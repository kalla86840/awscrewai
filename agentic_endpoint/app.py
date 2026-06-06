import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import boto3
import yaml
from openai import OpenAI

try:
    from pinecone import Pinecone, ServerlessSpec
except ImportError:  # Pinecone is optional for local tests and falls back to keyword retrieval.
    Pinecone = ServerlessSpec = None

try:
    from crewai import Agent, Crew, LLM, Process, Task
except ImportError:  # Allows fast local contract tests without the full Lambda dependency set.
    Agent = Crew = LLM = Process = Task = None


PROFILE_PATH = Path(__file__).with_name("agent_profiles.yaml")
DEFAULT_RAG_PATH = Path(__file__).with_name("hospital_agentic_rag_knowledge.txt")
DEFAULT_PINECONE_INDEX_NAME = "agentic-hospital-rag-1024"
DEFAULT_PINECONE_NAMESPACE = "hospital-agentic"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
AGENT_ALIASES = {
    "agent_1": "hospital",
    "agent_2": "doctor",
    "agent_3": "nurse",
}
DEFAULT_AGENT_SEQUENCE = ["agent_1", "agent_2", "agent_3"]

AGENT_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
        "next_actions": {"type": "array", "items": {"type": "string"}},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
    },
    "required": ["summary", "findings", "next_actions", "risk_level"],
}

INFERENCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "case_summary": {"type": "string"},
        "care_team_consensus": {"type": "string"},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
        "signals_to_monitor": {"type": "array", "items": {"type": "string"}},
        "escalation_level": {"type": "string", "enum": ["routine", "urgent", "emergent"]},
        "handoff": {"type": "string"},
    },
    "required": [
        "case_summary",
        "care_team_consensus",
        "recommended_actions",
        "signals_to_monitor",
        "escalation_level",
        "handoff",
    ],
}


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": "*",
        },
        "body": json.dumps(body),
    }


def load_profiles():
    with open(PROFILE_PATH, "r", encoding="utf-8") as profile_file:
        return yaml.safe_load(profile_file)


def _tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def load_text_knowledge_base(path):
    content = Path(path).read_text(encoding="utf-8").strip()
    sections = [
        section.strip()
        for section in re.split(r"\n\s*\n", content)
        if section.strip()
    ]
    if not sections:
        raise ValueError(f"No RAG sections were found in {path}.")

    documents = []
    for index, section in enumerate(sections, start=1):
        lines = section.splitlines()
        title = lines[0].strip("# ").strip() if lines else f"Section {index}"
        documents.append(
            {
                "id": f"hospital-rag-{index}",
                "title": title or f"Section {index}",
                "source": str(path),
                "content": section,
            }
        )
    return documents


def build_retrieval_query(payload):
    return json.dumps(
        {
            "task": payload.get("task", ""),
            "chief_concern": payload.get("chief_concern", ""),
            "vitals": payload.get("vitals", {}),
            "signals": payload.get("signals", {}),
            "notes": payload.get("notes", []),
            "requested_inference": payload.get("requested_inference", ""),
        }
    )


def keyword_retrieve_context(payload, documents, query, top_k):
    query_terms = Counter(_tokenize(query))

    scored_documents = []
    for document in documents:
        document_terms = Counter(_tokenize(document["title"] + "\n" + document["content"]))
        overlap_score = sum(query_terms[term] * document_terms.get(term, 0) for term in query_terms)
        scored_documents.append((overlap_score, document))

    scored_documents.sort(key=lambda item: item[0], reverse=True)
    selected = [document for score, document in scored_documents if score > 0]
    if not selected:
        selected = [document for _, document in scored_documents]
    selected = selected[:top_k]
    for document in selected:
        document.setdefault("retrieval_source", "keyword")
    return selected


def get_secret_value(secret_arn):
    client = boto3.client("secretsmanager")
    secret = client.get_secret_value(SecretId=secret_arn)
    return secret["SecretString"]


def get_pinecone_api_key():
    direct_key = os.getenv("PINECONE_API_KEY")
    if direct_key:
        return direct_key

    secret_arn = os.getenv("PINECONE_API_KEY_SECRET_ARN")
    if secret_arn:
        return get_secret_value(secret_arn)
    return None


def pinecone_is_available(payload):
    if payload.get("disable_pinecone") is True:
        return False
    return Pinecone is not None and bool(get_pinecone_api_key())


def create_embedding(client, text):
    dimension = int(os.getenv("PINECONE_DIMENSION", "1024"))
    result = client.embeddings.create(
        model=os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        input=text,
        dimensions=dimension,
    )
    return result.data[0].embedding


def get_pinecone_index(api_key):
    index_host = os.getenv("PINECONE_INDEX_HOST", "")
    pc = Pinecone(api_key=api_key)
    if index_host:
        return pc.Index(host=index_host)

    index_name = os.getenv("PINECONE_INDEX_NAME", DEFAULT_PINECONE_INDEX_NAME)
    has_index = False
    if hasattr(pc, "has_index"):
        has_index = pc.has_index(index_name)
    else:
        existing_names = []
        for index in pc.list_indexes():
            if isinstance(index, dict):
                existing_names.append(index.get("name"))
            else:
                existing_names.append(getattr(index, "name", None))
        has_index = index_name in existing_names

    if not has_index:
        pc.create_index(
            name=index_name,
            dimension=int(os.getenv("PINECONE_DIMENSION", "1024")),
            metric=os.getenv("PINECONE_METRIC", "cosine"),
            spec=ServerlessSpec(
                cloud=os.getenv("PINECONE_CLOUD", "aws"),
                region=os.getenv("PINECONE_REGION", "us-east-1"),
            ),
        )
        for _ in range(30):
            description = pc.describe_index(index_name)
            status = description.get("status", {}) if isinstance(description, dict) else getattr(description, "status", {})
            ready = status.get("ready") if isinstance(status, dict) else getattr(status, "ready", False)
            if ready:
                break
            time.sleep(2)
    return pc.Index(index_name)


def pinecone_retrieve_context(payload, documents, query, top_k, openai_api_key):
    api_key = get_pinecone_api_key()
    if not api_key:
        return []

    client = OpenAI(api_key=openai_api_key)
    index = get_pinecone_index(api_key)
    namespace = payload.get("namespace") or os.getenv("PINECONE_NAMESPACE", DEFAULT_PINECONE_NAMESPACE)

    if os.getenv("PINECONE_UPSERT_ON_QUERY", "true").lower() == "true":
        vectors = []
        for document in documents:
            vectors.append(
                {
                    "id": document["id"],
                    "values": create_embedding(client, document["content"]),
                    "metadata": {
                        "title": document["title"],
                        "source": document["source"],
                        "content": document["content"],
                    },
                }
            )
        index.upsert(vectors=vectors, namespace=namespace)

    query_vector = create_embedding(client, query)
    result = index.query(
        vector=query_vector,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True,
    )

    contexts = []
    matches = result.get("matches", []) if isinstance(result, dict) else getattr(result, "matches", [])
    for match in matches:
        if isinstance(match, dict):
            match_id = match.get("id")
            score = match.get("score")
            metadata = match.get("metadata") or {}
        else:
            match_id = getattr(match, "id", None)
            score = getattr(match, "score", None)
            metadata = getattr(match, "metadata", {}) or {}
        contexts.append(
            {
                "id": match_id,
                "title": metadata.get("title", match_id or "Pinecone match"),
                "source": metadata.get("source", "pinecone"),
                "content": metadata.get("content", ""),
                "score": score,
                "retrieval_source": "pinecone",
                "namespace": namespace,
            }
        )
    return contexts


def retrieve_context(payload, openai_api_key=None):
    knowledge_path = Path(payload.get("rag_knowledge_path") or os.getenv("RAG_KNOWLEDGE_PATH", DEFAULT_RAG_PATH))
    top_k = int(payload.get("rag_top_k") or os.getenv("RAG_TOP_K", "4"))
    documents = load_text_knowledge_base(knowledge_path)
    query = build_retrieval_query(payload)

    if openai_api_key and pinecone_is_available(payload):
        try:
            contexts = pinecone_retrieve_context(payload, documents, query, top_k, openai_api_key)
            if contexts:
                return contexts
        except Exception as exc:
            if payload.get("strict_pinecone") is True:
                raise
            fallback = keyword_retrieve_context(payload, documents, query, top_k)
            for document in fallback:
                document["pinecone_error"] = str(exc)
            return fallback

    return keyword_retrieve_context(payload, documents, query, top_k)


def parse_body(event):
    body = event.get("body", event)
    if isinstance(body, str):
        return json.loads(body or "{}")
    return body or {}


def resolve_agent_name(agent_name):
    normalized = str(agent_name).strip().lower().replace("-", "_").replace(" ", "_")
    return AGENT_ALIASES.get(normalized, normalized)


def agent_label_for_role(role):
    for label, mapped_role in AGENT_ALIASES.items():
        if mapped_role == role:
            return label
    return role


def get_openai_api_key():
    direct_key = os.getenv("OPENAI_API_KEY")
    if direct_key:
        return direct_key

    secret_arn = os.getenv("OPENAI_API_KEY_SECRET_ARN")
    if not secret_arn:
        raise RuntimeError("OPENAI_API_KEY_SECRET_ARN or OPENAI_API_KEY must be set.")

    return get_secret_value(secret_arn)


def build_agent_input(payload, prior_outputs, retrieved_context):
    return json.dumps(
        {
            "task": payload.get("task", "Create an agentic hospital care-coordination inference."),
            "patient_context": payload.get("patient_context", {}),
            "chief_concern": payload.get("chief_concern", ""),
            "vitals": payload.get("vitals", {}),
            "signals": payload.get("signals", {}),
            "notes": payload.get("notes", []),
            "requested_inference": payload.get("requested_inference", ""),
            "retrieved_context": retrieved_context,
            "prior_agent_outputs": prior_outputs,
        },
        indent=2,
    )


def _extract_json_object(text):
    if isinstance(text, dict):
        return text

    raw = str(text).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _crew_output_text(output):
    if hasattr(output, "raw"):
        return output.raw
    return str(output)


def crewai_is_available():
    return all(component is not None for component in (Agent, Crew, LLM, Process, Task))


def build_llm(model, api_key):
    if not crewai_is_available():
        return None
    return LLM(model=f"openai/{model}", api_key=api_key)


def run_crewai_agent(agent_name, profile, payload, prior_outputs, retrieved_context, max_output_tokens, api_key):
    model = payload.get("model") or profile.get("model") or os.getenv("OPENAI_MODEL", "gpt-5.2")
    llm = build_llm(model, api_key)
    agent = Agent(
        role=f"{agent_name.title()} real-time inference agent",
        goal="Produce a grounded JSON care-coordination assessment for the endpoint.",
        backstory=profile["instructions"],
        llm=llm,
        allow_delegation=False,
        verbose=False,
    )
    task = Task(
        description=(
            "Analyze this real-time endpoint payload and return only a JSON object matching this schema: "
            f"{json.dumps(AGENT_OUTPUT_SCHEMA)}\n\n"
            f"Input:\n{build_agent_input(payload, prior_outputs, retrieved_context)}\n\n"
            f"Keep the response under {max_output_tokens} output tokens."
        ),
        expected_output="A strict JSON object with summary, findings, next_actions, and risk_level.",
        agent=agent,
    )
    output = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False).kickoff()
    return _extract_json_object(_crew_output_text(output))


def run_crewai_final_inference(payload, agent_outputs, retrieved_context, max_output_tokens, api_key):
    model = payload.get("model") or os.getenv("OPENAI_MODEL", "gpt-5.2")
    llm = build_llm(model, api_key)
    coordinator = Agent(
        role="Care coordination synthesis agent",
        goal="Synthesize specialist agent findings into a single real-time endpoint inference.",
        backstory=(
            "You coordinate OpenAI and CrewAI agent outputs for a hospital operations endpoint. "
            "You ground the response in retrieved context, avoid diagnosis, and return JSON only."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
    )
    task = Task(
        description=(
            "Return only a JSON object matching this inference schema: "
            f"{json.dumps(payload.get('response_schema') or INFERENCE_SCHEMA)}\n\n"
            f"Payload:\n{json.dumps(payload, indent=2)}\n\n"
            f"Retrieved context:\n{json.dumps(retrieved_context, indent=2)}\n\n"
            f"Agent outputs:\n{json.dumps(agent_outputs, indent=2)}\n\n"
            f"Keep the response under {max_output_tokens} output tokens."
        ),
        expected_output=(
            "A strict JSON object with case_summary, care_team_consensus, recommended_actions, "
            "signals_to_monitor, escalation_level, and handoff."
        ),
        agent=coordinator,
    )
    output = Crew(agents=[coordinator], tasks=[task], process=Process.sequential, verbose=False).kickoff()
    return _extract_json_object(_crew_output_text(output))


def call_agent(client, agent_name, profile, payload, prior_outputs, retrieved_context, max_output_tokens):
    result = client.responses.create(
        model=payload.get("model") or profile.get("model") or os.getenv("OPENAI_MODEL", "gpt-5.2"),
        instructions=profile["instructions"],
        input=build_agent_input(payload, prior_outputs, retrieved_context),
        text={
            "format": {
                "type": "json_schema",
                "name": f"{agent_name}_agent_result",
                "schema": AGENT_OUTPUT_SCHEMA,
                "strict": True,
            }
        },
        max_output_tokens=max_output_tokens,
    )
    return json.loads(result.output_text)


def run_final_inference(client, payload, agent_outputs, retrieved_context, max_output_tokens):
    instructions = payload.get("coordinator_instructions") or (
        "You are the agentic care-coordination endpoint. Synthesize the hospital, "
        "doctor, and nurse agent outputs into a real-time inference result for "
        "hospital operations. Use the retrieved RAG context as grounding. This is "
        "decision support only; avoid claiming a diagnosis or replacing clinician "
        "judgment."
    )
    result = client.responses.create(
        model=payload.get("model") or os.getenv("OPENAI_MODEL", "gpt-5.2"),
        instructions=instructions,
        input=json.dumps(
            {
                "request": payload,
                "retrieved_context": retrieved_context,
                "agent_outputs": agent_outputs,
            },
            indent=2,
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "agentic_hospital_inference",
                "schema": payload.get("response_schema") or INFERENCE_SCHEMA,
                "strict": True,
            }
        },
        max_output_tokens=max_output_tokens,
    )
    return json.loads(result.output_text)


def run_dry_inference(payload, requested_agents, profiles, retrieved_context):
    agent_outputs = []
    for requested_agent in requested_agents:
        agent_name = resolve_agent_name(requested_agent)
        profile = profiles.get(agent_name)
        if profile is None:
            return None, response(
                400,
                {
                    "error": f"Unknown agent '{requested_agent}'.",
                    "agent_aliases": AGENT_ALIASES,
                    "available_agents": sorted(profiles.keys()),
                },
            )

        agent_outputs.append(
            {
                "agent_id": agent_label_for_role(agent_name),
                "agent": agent_name,
                "result": {
                    "summary": f"{agent_name} agent dry-run validation completed.",
                    "findings": [
                        "AWS Lambda container endpoint loaded profiles, request parsing, and RAG context successfully.",
                        profile["instructions"].splitlines()[0],
                    ],
                    "next_actions": ["Run the same request without dry_run for live CrewAI/OpenAI inference."],
                    "risk_level": "medium",
                },
            }
        )

    return {
        "case_summary": payload.get("chief_concern", "Dry-run hospital event validated."),
        "care_team_consensus": "agent_1 hospital, agent_2 doctor, and agent_3 nurse are mapped and callable.",
        "recommended_actions": ["Proceed with live endpoint inference after deployment validation."],
        "signals_to_monitor": sorted((payload.get("vitals") or {}).keys()),
        "escalation_level": "urgent",
        "handoff": "Dry-run completed without calling external OpenAI services.",
    }, agent_outputs


def lambda_handler(event, context):
    try:
        payload = parse_body(event)
        profiles = load_profiles()
        max_output_tokens = int(payload.get("max_output_tokens") or os.getenv("MAX_OUTPUT_TOKENS", "1400"))
        requested_agents = payload.get("agents") or DEFAULT_AGENT_SEQUENCE
        openai_api_key = None if payload.get("dry_run") is True else get_openai_api_key()
        retrieved_context = retrieve_context(payload, openai_api_key=openai_api_key)

        if payload.get("dry_run") is True:
            inference, dry_result = run_dry_inference(payload, requested_agents, profiles, retrieved_context)
            if inference is None:
                return dry_result
            return response(
                200,
                {
                    "task": payload.get("task", "Create an agentic hospital care-coordination inference."),
                    "orchestrator": "crewai-dry-run",
                    "retrieved_context": retrieved_context,
                    "agents": dry_result,
                    "inference": inference,
                },
            )

        api_key = openai_api_key
        use_crewai = payload.get("use_crewai", True) is not False and crewai_is_available()
        client = None if use_crewai else OpenAI(api_key=api_key)
        agent_outputs = []
        for requested_agent in requested_agents:
            agent_name = resolve_agent_name(requested_agent)
            agent_id = agent_label_for_role(agent_name)
            profile = profiles.get(agent_name)
            if profile is None:
                return response(
                    400,
                    {
                        "error": f"Unknown agent '{requested_agent}'.",
                        "agent_aliases": AGENT_ALIASES,
                        "available_agents": sorted(profiles.keys()),
                    },
                )

            if use_crewai:
                agent_result = run_crewai_agent(
                    agent_name,
                    profile,
                    payload,
                    agent_outputs,
                    retrieved_context,
                    max_output_tokens,
                    api_key,
                )
            else:
                agent_result = call_agent(
                    client,
                    agent_name,
                    profile,
                    payload,
                    agent_outputs,
                    retrieved_context,
                    max_output_tokens,
                )
            agent_outputs.append(
                {
                    "agent_id": agent_id,
                    "agent": agent_name,
                    "result": agent_result,
                }
            )

        if use_crewai:
            inference = run_crewai_final_inference(payload, agent_outputs, retrieved_context, max_output_tokens, api_key)
        else:
            inference = run_final_inference(client, payload, agent_outputs, retrieved_context, max_output_tokens)
        return response(
            200,
            {
                "task": payload.get("task", "Create an agentic hospital care-coordination inference."),
                "orchestrator": "crewai" if use_crewai else "openai-responses",
                "retrieved_context": retrieved_context,
                "agents": agent_outputs,
                "inference": inference,
            },
        )
    except Exception as exc:
        return response(500, {"error": str(exc)})
