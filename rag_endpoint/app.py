import json
import os
import re
import time
from collections import Counter
from pathlib import Path

KNOWLEDGE_PATH = Path(os.environ.get("RAG_KNOWLEDGE_PATH", "knowledge/open_ai_rag_knowledge.txt"))
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2")
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
OPENAI_API_KEY_SECRET_ARN = os.environ.get("OPENAI_API_KEY_SECRET_ARN")
PINECONE_API_KEY_SECRET_ARN = os.environ.get("PINECONE_API_KEY_SECRET_ARN")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "open-ai-pinecone-duplicate-detection-1024")
PINECONE_INDEX_HOST = os.environ.get("PINECONE_INDEX_HOST")
PINECONE_NAMESPACE = os.environ.get("PINECONE_NAMESPACE", "news")
PINECONE_MEMORY_NAMESPACE = os.environ.get("PINECONE_MEMORY_NAMESPACE", "agent-memory")
PINECONE_DUPLICATE_NAMESPACE = os.environ.get("PINECONE_DUPLICATE_NAMESPACE", PINECONE_NAMESPACE)
PINECONE_CLASSIFICATION_NAMESPACE = os.environ.get("PINECONE_CLASSIFICATION_NAMESPACE", PINECONE_NAMESPACE)
PINECONE_CLUSTERING_NAMESPACE = os.environ.get("PINECONE_CLUSTERING_NAMESPACE", PINECONE_CLASSIFICATION_NAMESPACE)
PINECONE_MULTIMODAL_NAMESPACE = os.environ.get("PINECONE_MULTIMODAL_NAMESPACE", PINECONE_NAMESPACE)
PINECONE_CLOUD = os.environ.get("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.environ.get("PINECONE_REGION", "us-east-1")
PINECONE_DIMENSION = int(os.environ.get("PINECONE_DIMENSION", "1024"))
PINECONE_METRIC = os.environ.get("PINECONE_METRIC", "cosine")
ENABLE_PINECONE = os.environ.get("ENABLE_PINECONE", "true").lower() == "true"
PINECONE_UPSERT_ON_QUERY = os.environ.get("PINECONE_UPSERT_ON_QUERY", "true").lower() == "true"
DUPLICATE_SCORE_THRESHOLD = float(os.environ.get("DUPLICATE_SCORE_THRESHOLD", "0.98"))
SIMILARITY_SCORE_THRESHOLD = float(os.environ.get("SIMILARITY_SCORE_THRESHOLD", "0.85"))
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "700"))
TOP_K = int(os.environ.get("TOP_K", "3"))
_OPENAI_API_KEY = None
_PINECONE_API_KEY = None
_PINECONE_INDEXED = False

AGENTS = [
    {"name": "manual_retrieval_agent", "role": "Document retrieval analyst", "instructions": "You are Agent 1, the document retrieval analyst. Use only the retrieved manual sections to identify the sections that answer the question. Return practical findings and cite section titles. If the retrieved context is insufficient, say what is missing."},
    {"name": "procedure_agent", "role": "Step-by-step procedure specialist", "instructions": "You are Agent 2, the procedure specialist. Use only the retrieved manual sections to extract an ordered, user-safe procedure. Preserve important sequence, prerequisites, and checks from the document."},
    {"name": "safety_agent", "role": "Safety and escalation reviewer", "instructions": "You are Agent 3, the safety reviewer. Use only the retrieved manual sections to identify warnings, stop conditions, and when a qualified professional should be contacted."},
]

AGENT_OUTPUT_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {"summary": {"type": "string"}, "findings": {"type": "array", "items": {"type": "string"}}, "citations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"id": {"type": "string"}, "title": {"type": "string"}}, "required": ["id", "title"]}}, "confidence": {"type": "string", "enum": ["low", "medium", "high"]}}, "required": ["summary", "findings", "citations", "confidence"]}
FINAL_OUTPUT_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {"answer": {"type": "string"}, "steps": {"type": "array", "items": {"type": "string"}}, "safety_notes": {"type": "array", "items": {"type": "string"}}, "citations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"id": {"type": "string"}, "title": {"type": "string"}}, "required": ["id", "title"]}}, "agent_consensus": {"type": "string"}}, "required": ["answer", "steps", "safety_notes", "citations", "agent_consensus"]}
CHATBOT_RAG_MODES = {"answer", "chatbot_rag", "assistant_rag", "chatbot_assistant"}


def _tokenize(text):
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    normalized = []
    for token in tokens:
        if token.startswith("connect"):
            normalized.append("connect")
        elif token.startswith("install"):
            normalized.append("install")
        elif token.startswith("leak"):
            normalized.append("leak")
        elif token.endswith("s") and len(token) > 3:
            normalized.append(token[:-1])
        else:
            normalized.append(token)
    return normalized


def load_documents(path=KNOWLEDGE_PATH):
    content = Path(path).read_text(encoding="utf-8").strip()
    sections = [section.strip() for section in re.split(r"\n\s*\n", content) if section.strip()]
    documents = []
    for index, section in enumerate(sections, start=1):
        lines = section.splitlines()
        title = lines[0].strip("# ").strip() if lines else f"Section {index}"
        documents.append({"id": f"doc-{index}", "title": title, "content": section})
    return documents


def retrieve(question, documents, top_k=TOP_K):
    question_terms = Counter(_tokenize(question))
    scored = []
    for document in documents:
        document_terms = Counter(_tokenize(f"{document['title']} {document['content']}"))
        score = sum(question_terms[term] * document_terms.get(term, 0) for term in question_terms)
        scored.append((score, document))
    scored.sort(key=lambda item: item[0], reverse=True)
    matches = [document for score, document in scored if score > 0]
    if not matches:
        matches = [document for _, document in scored]
    return matches[:top_k]


def get_secret_value(secret_arn, env_var_name):
    value = os.environ.get(env_var_name)
    if value:
        return value
    if not secret_arn:
        raise ValueError(f"{env_var_name}_SECRET_ARN or {env_var_name} must be configured.")
    import boto3
    return boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)["SecretString"]


def get_openai_api_key():
    global _OPENAI_API_KEY
    if not _OPENAI_API_KEY:
        _OPENAI_API_KEY = get_secret_value(OPENAI_API_KEY_SECRET_ARN, "OPENAI_API_KEY")
    return _OPENAI_API_KEY


def get_pinecone_api_key():
    global _PINECONE_API_KEY
    if not _PINECONE_API_KEY:
        _PINECONE_API_KEY = get_secret_value(PINECONE_API_KEY_SECRET_ARN, "PINECONE_API_KEY")
    return _PINECONE_API_KEY


def embed_texts(client, texts):
    response = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=texts, dimensions=PINECONE_DIMENSION)
    return [item.embedding for item in response.data]


def _list_pinecone_index_names(pc):
    indexes = pc.list_indexes()
    if hasattr(indexes, "names"):
        return set(indexes.names())
    return {index["name"] for index in indexes}


def _pinecone_index_ready(description):
    status = getattr(description, "status", {}) or {}
    if isinstance(status, dict):
        return bool(status.get("ready"))
    return bool(getattr(status, "ready", False))


def get_pinecone_index():
    from pinecone import Pinecone, ServerlessSpec
    pc = Pinecone(api_key=get_pinecone_api_key())
    if PINECONE_INDEX_HOST:
        return pc.Index(host=PINECONE_INDEX_HOST)

    if PINECONE_INDEX_NAME not in _list_pinecone_index_names(pc):
        try:
            pc.create_index(name=PINECONE_INDEX_NAME, dimension=PINECONE_DIMENSION, metric=PINECONE_METRIC, spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION), deletion_protection="disabled")
        except Exception as error:
            if "already exists" not in str(error).lower():
                raise
        deadline = time.time() + 120
        while time.time() < deadline:
            description = pc.describe_index(PINECONE_INDEX_NAME)
            if _pinecone_index_ready(description):
                break
            time.sleep(3)
    return pc.Index(PINECONE_INDEX_NAME)


def upsert_documents_to_pinecone(openai_client, index, documents):
    global _PINECONE_INDEXED
    if _PINECONE_INDEXED:
        return
    embeddings = embed_texts(openai_client, [f"{document['title']}\n{document['content']}" for document in documents])
    vectors = []
    for document, embedding in zip(documents, embeddings):
        vectors.append({"id": document["id"], "values": embedding, "metadata": {"title": document["title"], "content": document["content"]}})
    index.upsert(vectors=vectors, namespace=PINECONE_NAMESPACE)
    time.sleep(2)
    _PINECONE_INDEXED = True


def semantic_search(question, documents, top_k=TOP_K):
    from openai import OpenAI
    client = OpenAI(api_key=get_openai_api_key())
    index = get_pinecone_index()
    if PINECONE_UPSERT_ON_QUERY:
        upsert_documents_to_pinecone(client, index, documents)
    question_embedding = embed_texts(client, [question])[0]
    result = index.query(vector=question_embedding, top_k=top_k, include_metadata=True, namespace=PINECONE_NAMESPACE)
    return pinecone_matches_to_documents(result)


def _pinecone_result_get(result, key, default=None):
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def pinecone_matches_to_documents(result, exclude_ids=None):
    exclude_ids = set(exclude_ids or [])
    context_documents = []
    for match in _pinecone_result_get(result, "matches", []):
        match_id = _pinecone_result_get(match, "id")
        if match_id in exclude_ids:
            continue
        metadata = _pinecone_result_get(match, "metadata", {}) or {}
        content = metadata.get("content") or metadata.get("text") or metadata.get("summary") or json.dumps(metadata)
        context_documents.append({"id": match_id, "title": metadata.get("title", match_id), "content": content, "score": _pinecone_result_get(match, "score"), "metadata": metadata})
    return context_documents


def pinecone_matches_with_values(result, exclude_ids=None):
    exclude_ids = set(exclude_ids or [])
    matches = []
    for match in _pinecone_result_get(result, "matches", []):
        match_id = _pinecone_result_get(match, "id")
        if match_id in exclude_ids:
            continue
        metadata = _pinecone_result_get(match, "metadata", {}) or {}
        content = metadata.get("content") or metadata.get("text") or metadata.get("summary") or json.dumps(metadata)
        matches.append(
            {
                "id": match_id,
                "title": metadata.get("title", match_id),
                "content": content,
                "score": _pinecone_result_get(match, "score"),
                "metadata": metadata,
                "values": _pinecone_result_get(match, "values", []) or [],
            }
        )
    return matches


def _records_from_fetch(fetch_result):
    vectors = _pinecone_result_get(fetch_result, "vectors", {}) or {}
    if isinstance(vectors, dict):
        return vectors
    return {record.id: record for record in vectors}


def _record_to_seed_text(record):
    metadata = _pinecone_result_get(record, "metadata", {}) or {}
    return "\n".join(str(value) for value in [metadata.get("title"), metadata.get("content"), metadata.get("text"), metadata.get("summary")] if value)


def recommend_from_pinecone(payload, documents, top_k=TOP_K):
    from openai import OpenAI
    client = OpenAI(api_key=get_openai_api_key())
    index = get_pinecone_index()
    if PINECONE_UPSERT_ON_QUERY:
        upsert_documents_to_pinecone(client, index, documents)

    seed_id = payload.get("seed_id")
    exclude_ids = set(payload.get("exclude_ids") or [])
    vector = None
    seed_text = payload.get("seed_text") or payload.get("question")

    if seed_id:
        exclude_ids.add(seed_id)
        records = _records_from_fetch(index.fetch(ids=[seed_id], namespace=PINECONE_NAMESPACE))
        seed_record = records.get(seed_id)
        if not seed_record:
            raise ValueError(f"Seed record {seed_id!r} was not found in Pinecone namespace {PINECONE_NAMESPACE!r}.")
        vector = _pinecone_result_get(seed_record, "values")
        seed_text = seed_text or _record_to_seed_text(seed_record)
        if not vector and not seed_text:
            raise ValueError(f"Seed record {seed_id!r} did not include vector values or usable recommendation text.")

    if not vector:
        user_profile = payload.get("user_profile") or {}
        interests = payload.get("interests") or []
        if seed_text and (user_profile or interests):
            seed_text = json.dumps({"seed_text": seed_text, "user_profile": user_profile, "interests": interests}, sort_keys=True)
        elif not seed_text:
            seed_text = json.dumps({"user_profile": user_profile, "interests": interests}, sort_keys=True)
        if not seed_text or seed_text == '{"interests": [], "user_profile": {}}':
            raise ValueError("Recommendation requests must include seed_id, seed_text, question, user_profile, or interests.")
        vector = embed_texts(client, [seed_text])[0]

    result = index.query(vector=vector, top_k=top_k + len(exclude_ids), include_metadata=True, namespace=PINECONE_NAMESPACE)
    recommendations = pinecone_matches_to_documents(result, exclude_ids=exclude_ids)
    return recommendations[:top_k], seed_text


def _duplicate_candidate_text(payload):
    candidate = payload.get("candidate") or {}
    candidate_text = (
        payload.get("candidate_text")
        or payload.get("text")
        or payload.get("content")
        or payload.get("question")
        or candidate.get("text")
        or candidate.get("content")
        or candidate.get("summary")
    )
    if candidate_text:
        return candidate_text
    if candidate:
        text_parts = [
            str(value)
            for value in [
                candidate.get("title"),
                candidate.get("description"),
                candidate.get("body"),
                candidate.get("metadata"),
            ]
            if value
        ]
        if text_parts:
            return "\n".join(text_parts)
    raise ValueError("Duplicate or similarity detection requests must include candidate_text, text, content, question, or candidate content.")


def detect_duplicate_similarity(payload, documents, top_k=TOP_K):
    from openai import OpenAI
    client = OpenAI(api_key=get_openai_api_key())
    index = get_pinecone_index()
    if PINECONE_UPSERT_ON_QUERY:
        upsert_documents_to_pinecone(client, index, documents)

    namespace = payload.get("namespace") or PINECONE_DUPLICATE_NAMESPACE
    candidate_text = _duplicate_candidate_text(payload)
    candidate_id = payload.get("candidate_id") or (payload.get("candidate") or {}).get("id")
    duplicate_threshold = float(payload.get("duplicate_threshold", DUPLICATE_SCORE_THRESHOLD))
    similarity_threshold = float(payload.get("similarity_threshold", SIMILARITY_SCORE_THRESHOLD))
    exclude_ids = set(payload.get("exclude_ids") or [])
    if candidate_id:
        exclude_ids.add(candidate_id)

    vector = embed_texts(client, [candidate_text])[0]
    result = index.query(
        vector=vector,
        top_k=top_k + len(exclude_ids),
        include_metadata=True,
        namespace=namespace,
    )
    matches = pinecone_matches_to_documents(result, exclude_ids=exclude_ids)
    classified_matches = []
    for match in matches:
        score = match.get("score") or 0
        if score >= duplicate_threshold:
            classification = "duplicate"
        elif score >= similarity_threshold:
            classification = "similar"
        else:
            classification = "related"
        classified_match = dict(match)
        classified_match["classification"] = classification
        classified_matches.append(classified_match)

    likely_duplicates = [match for match in classified_matches if match["classification"] == "duplicate"]
    similar_records = [match for match in classified_matches if match["classification"] == "similar"]
    return {
        "mode": "duplicate_similarity",
        "candidate_id": candidate_id,
        "candidate_text": candidate_text,
        "retrieval_source": "pinecone",
        "namespace": namespace,
        "duplicate_threshold": duplicate_threshold,
        "similarity_threshold": similarity_threshold,
        "likely_duplicates": likely_duplicates,
        "similar_records": similar_records,
        "matches": classified_matches[:top_k],
    }


def _classification_text(payload):
    text = payload.get("text") or payload.get("content") or payload.get("question") or payload.get("query")
    if text:
        return text
    candidate = payload.get("candidate") or {}
    text_parts = [
        str(value)
        for value in [
            candidate.get("title"),
            candidate.get("description"),
            candidate.get("content"),
            candidate.get("summary"),
        ]
        if value
    ]
    if text_parts:
        return "\n".join(text_parts)
    raise ValueError("Classification and clustering requests must include text, content, question, query, or candidate content.")


def _metadata_label(metadata, label_field):
    for key in [label_field, "label", "category", "class", "segment", "topic"]:
        if metadata.get(key):
            return str(metadata[key])
    return None


def _vector_distance(left, right):
    return sum((a - b) ** 2 for a, b in zip(left, right)) ** 0.5


def _average_vectors(vectors):
    if not vectors:
        return []
    width = len(vectors[0])
    return [sum(vector[index] for vector in vectors) / len(vectors) for index in range(width)]


def cluster_vector_matches(matches, n_clusters):
    vector_matches = [match for match in matches if match.get("values")]
    if not vector_matches:
        return []
    n_clusters = max(1, min(int(n_clusters), len(vector_matches)))
    centroids = [list(match["values"]) for match in vector_matches[:n_clusters]]
    assignments = [0] * len(vector_matches)

    for _ in range(8):
        changed = False
        for index, match in enumerate(vector_matches):
            distances = [_vector_distance(match["values"], centroid) for centroid in centroids]
            cluster = min(range(len(distances)), key=distances.__getitem__)
            if assignments[index] != cluster:
                assignments[index] = cluster
                changed = True
        if not changed:
            break
        for cluster in range(n_clusters):
            cluster_vectors = [
                match["values"]
                for match_index, match in enumerate(vector_matches)
                if assignments[match_index] == cluster
            ]
            if cluster_vectors:
                centroids[cluster] = _average_vectors(cluster_vectors)

    clusters = []
    for cluster in range(n_clusters):
        members = []
        for match_index, match in enumerate(vector_matches):
            if assignments[match_index] == cluster:
                members.append(
                    {
                        "id": match["id"],
                        "title": match["title"],
                        "score": match.get("score"),
                        "metadata": match.get("metadata", {}),
                    }
                )
        clusters.append({"cluster": cluster, "size": len(members), "members": members})
    return clusters


def classify_and_cluster(payload, documents, top_k=TOP_K):
    from openai import OpenAI
    client = OpenAI(api_key=get_openai_api_key())
    index = get_pinecone_index()
    if PINECONE_UPSERT_ON_QUERY:
        upsert_documents_to_pinecone(client, index, documents)

    text = _classification_text(payload)
    namespace = payload.get("namespace") or PINECONE_CLASSIFICATION_NAMESPACE
    label_field = payload.get("label_field", "category")
    n_clusters = int(payload.get("n_clusters", 3))
    vector = embed_texts(client, [text])[0]
    result = index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True,
        include_values=True,
        namespace=namespace,
    )
    matches = pinecone_matches_with_values(result)

    label_scores = {}
    for match in matches:
        label = _metadata_label(match.get("metadata", {}), label_field)
        if label:
            label_scores[label] = label_scores.get(label, 0.0) + float(match.get("score") or 0.0)
    predicted_label = max(label_scores, key=label_scores.get) if label_scores else "unlabeled"
    clusters = cluster_vector_matches(matches, n_clusters)

    return {
        "mode": payload.get("mode", "classification_clustering"),
        "text": text,
        "retrieval_source": "pinecone",
        "namespace": namespace,
        "label_field": label_field,
        "predicted_label": predicted_label,
        "label_scores": label_scores,
        "clusters": clusters,
        "matches": [
            {
                "id": match["id"],
                "title": match["title"],
                "score": match.get("score"),
                "metadata": match.get("metadata", {}),
            }
            for match in matches
        ],
    }


def normalize_image_inputs(payload):
    images = []
    for key in ["image_url", "image_data", "image"]:
        if payload.get(key):
            images.append(payload[key])
    images.extend(payload.get("image_urls") or [])
    images.extend(payload.get("images") or [])

    normalized = []
    for image in images:
        if isinstance(image, str):
            normalized.append({"type": "input_image", "image_url": image})
            continue
        if not isinstance(image, dict):
            continue
        image_url = image.get("image_url") or image.get("url") or image.get("data_url")
        if not image_url and image.get("base64"):
            mime_type = image.get("mime_type", "image/jpeg")
            image_url = f"data:{mime_type};base64,{image['base64']}"
        if image_url:
            normalized.append({"type": "input_image", "image_url": image_url})
    return normalized


def caption_images(client, image_inputs, prompt=None):
    if not image_inputs:
        return []
    content = [
        {
            "type": "input_text",
            "text": prompt
            or "Describe the visual content for a retrieval query. Include objects, text, scene, style, and any domain-specific entities.",
        }
    ]
    content.extend(image_inputs)
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[{"role": "user", "content": content}],
        max_output_tokens=min(MAX_OUTPUT_TOKENS, 400),
    )
    return [response.output_text.strip()]


def build_multimodal_query(payload, image_descriptions):
    text_parts = [
        payload.get("question"),
        payload.get("query"),
        payload.get("text"),
        payload.get("caption"),
        payload.get("description"),
    ]
    metadata = payload.get("metadata") or {}
    if metadata:
        text_parts.append(json.dumps(metadata, sort_keys=True))
    text_parts.extend(image_descriptions)
    query = "\n".join(str(part).strip() for part in text_parts if part and str(part).strip())
    if not query:
        raise ValueError("Multimodal retrieval requests must include text, a question, or at least one image.")
    return query


def multimodal_retrieval(payload, documents, top_k=TOP_K):
    from openai import OpenAI
    client = OpenAI(api_key=get_openai_api_key())
    index = get_pinecone_index()
    if PINECONE_UPSERT_ON_QUERY:
        upsert_documents_to_pinecone(client, index, documents)

    image_inputs = normalize_image_inputs(payload)
    image_descriptions = caption_images(client, image_inputs, payload.get("image_prompt"))
    fused_query = build_multimodal_query(payload, image_descriptions)
    namespace = payload.get("namespace") or PINECONE_MULTIMODAL_NAMESPACE
    vector = embed_texts(client, [fused_query])[0]
    result = index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True,
        namespace=namespace,
    )
    return {
        "mode": "multimodal_retrieval",
        "retrieval_source": "pinecone",
        "namespace": namespace,
        "question": payload.get("question") or payload.get("query"),
        "image_count": len(image_inputs),
        "image_descriptions": image_descriptions,
        "fused_query": fused_query,
        "retrieved_context": pinecone_matches_to_documents(result),
    }


def _memory_filter(payload):
    filters = {}
    for key in ["agent_id", "task_id", "memory_type"]:
        if payload.get(key):
            filters[key] = {"$eq": payload[key]}
    return filters or None


def write_agent_memory(payload):
    from openai import OpenAI
    client = OpenAI(api_key=get_openai_api_key())
    index = get_pinecone_index()
    content = payload.get("content") or payload.get("memory") or payload.get("observation")
    if not content:
        raise ValueError("Agent memory write requests must include content, memory, or observation.")
    agent_id = payload.get("agent_id", "default-agent")
    task_id = payload.get("task_id", "default-task")
    memory_type = payload.get("memory_type", "episodic")
    memory_id = payload.get("memory_id") or f"{agent_id}-{task_id}-{int(time.time() * 1000)}"
    metadata = {
        "agent_id": agent_id,
        "task_id": task_id,
        "memory_type": memory_type,
        "content": content,
        "title": payload.get("title") or f"{agent_id} {memory_type} memory",
        "source": payload.get("source", "agent_memory"),
        "created_at": payload.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    for key, value in (payload.get("metadata") or {}).items():
        if value is not None:
            metadata[key] = value
    vector = embed_texts(client, [content])[0]
    index.upsert(vectors=[{"id": memory_id, "values": vector, "metadata": metadata}], namespace=PINECONE_MEMORY_NAMESPACE)
    return {"memory_id": memory_id, "namespace": PINECONE_MEMORY_NAMESPACE, "metadata": metadata}


def search_agent_memory(payload, top_k=TOP_K):
    from openai import OpenAI
    client = OpenAI(api_key=get_openai_api_key())
    index = get_pinecone_index()
    query = payload.get("query") or payload.get("question") or payload.get("content")
    if not query:
        raise ValueError("Agent memory search requests must include query, question, or content.")
    vector = embed_texts(client, [query])[0]
    query_kwargs = {
        "vector": vector,
        "top_k": top_k,
        "include_metadata": True,
        "namespace": PINECONE_MEMORY_NAMESPACE,
    }
    filters = _memory_filter(payload)
    if filters:
        query_kwargs["filter"] = filters
    result = index.query(**query_kwargs)
    return pinecone_matches_to_documents(result)


def agent_memory_task(payload, top_k=TOP_K):
    action = payload.get("action", "search")
    result = {"mode": "agent_memory", "action": action, "retrieval_source": "pinecone", "namespace": PINECONE_MEMORY_NAMESPACE}
    if action in ["write", "upsert", "remember"]:
        result["stored_memory"] = write_agent_memory(payload)
        search_query = payload.get("query") or payload.get("question")
        if search_query:
            result["memories"] = search_agent_memory(payload, top_k=top_k)
    elif action in ["search", "recall"]:
        result["memories"] = search_agent_memory(payload, top_k=top_k)
    else:
        raise ValueError("Agent memory action must be write, upsert, remember, search, or recall.")
    return result


def retrieve_context(question, documents, top_k=TOP_K):
    if ENABLE_PINECONE and (PINECONE_API_KEY_SECRET_ARN or os.environ.get("PINECONE_API_KEY")):
        return semantic_search(question, documents, top_k=top_k), "pinecone"
    return retrieve(question, documents, top_k=top_k), "keyword"


def call_agent(client, agent, question, context_documents):
    response = client.responses.create(model=OPENAI_MODEL, instructions=agent["instructions"], input=json.dumps({"question": question, "retrieved_context": context_documents}), text={"format": {"type": "json_schema", "name": f"{agent['name']}_result", "schema": AGENT_OUTPUT_SCHEMA, "strict": True}}, max_output_tokens=MAX_OUTPUT_TOKENS)
    return json.loads(response.output_text)


def synthesize_answer(client, question, context_documents, agent_outputs):
    instructions = "You are the final coordinator for an AWS-hosted multi-agent RAG endpoint. Use only the retrieved document context and the three agent outputs. Answer the user's question clearly, cite section titles, and include safety notes. If the manual does not provide enough information, say so."
    response = client.responses.create(model=OPENAI_MODEL, instructions=instructions, input=json.dumps({"question": question, "retrieved_context": context_documents, "agent_outputs": agent_outputs}), text={"format": {"type": "json_schema", "name": "multi_agent_rag_answer", "schema": FINAL_OUTPUT_SCHEMA, "strict": True}}, max_output_tokens=MAX_OUTPUT_TOKENS)
    return json.loads(response.output_text)


def answer_question(question, context_documents, requested_agents=None):
    from openai import OpenAI
    client = OpenAI(api_key=get_openai_api_key())
    requested_agents = requested_agents or [agent["name"] for agent in AGENTS]
    selected_agents = [agent for agent in AGENTS if agent["name"] in requested_agents]
    if not selected_agents:
        raise ValueError("No valid agents were requested.")
    agent_outputs = []
    for agent in selected_agents:
        result = call_agent(client, agent, question, context_documents)
        agent_outputs.append({"agent": agent["name"], "role": agent["role"], "result": result})
    final = synthesize_answer(client, question, context_documents, agent_outputs)
    return agent_outputs, final


def response(status_code, body):
    return {"statusCode": status_code, "headers": {"content-type": "application/json", "access-control-allow-origin": "*"}, "body": json.dumps(body)}


def handler(event, context):
    try:
        body = event.get("body", event)
        if isinstance(body, str):
            if event.get("isBase64Encoded"):
                return response(400, {"error": "Base64 encoded bodies are not supported."})
            payload = json.loads(body or "{}")
        else:
            payload = body or {}
        mode = payload.get("mode", "answer")
        question = payload.get("question")
        pinecone_task_modes = ["recommendations", "agent_memory", "duplicate_similarity", "classification", "clustering", "classification_clustering", "multimodal_retrieval"]
        if mode not in pinecone_task_modes and not question:
            return response(400, {"error": "Request JSON must include a non-empty question."})
        top_k = int(payload.get("top_k", TOP_K))
        requested_agents = payload.get("agents")
        if mode == "agent_memory":
            return response(200, agent_memory_task(payload, top_k=top_k))
        if mode == "duplicate_similarity":
            documents = load_documents() if PINECONE_UPSERT_ON_QUERY else []
            return response(200, detect_duplicate_similarity(payload, documents, top_k=top_k))
        if mode in ["classification", "clustering", "classification_clustering"]:
            documents = load_documents() if PINECONE_UPSERT_ON_QUERY else []
            result = classify_and_cluster(payload, documents, top_k=top_k)
            if mode == "classification":
                result.pop("clusters", None)
            elif mode == "clustering":
                result.pop("predicted_label", None)
                result.pop("label_scores", None)
            return response(200, result)
        if mode == "multimodal_retrieval":
            documents = load_documents() if PINECONE_UPSERT_ON_QUERY else []
            return response(200, multimodal_retrieval(payload, documents, top_k=top_k))
        if mode == "recommendations":
            documents = load_documents() if PINECONE_UPSERT_ON_QUERY else []
            recommendations, seed_text = recommend_from_pinecone(payload, documents, top_k=top_k)
            return response(200, {"mode": mode, "seed_id": payload.get("seed_id"), "seed_text": seed_text, "retrieval_source": "pinecone", "recommendations": recommendations})
        documents = load_documents()
        retrieved_context, retrieval_source = retrieve_context(question, documents, top_k=top_k)
        if mode == "semantic_search":
            return response(200, {"question": question, "document": str(KNOWLEDGE_PATH), "retrieval_source": retrieval_source, "retrieved_context": retrieved_context})
        if mode not in CHATBOT_RAG_MODES:
            return response(400, {"error": f"Unsupported mode {mode!r}."})
        agent_outputs, final = answer_question(question, retrieved_context, requested_agents=requested_agents)
        return response(
            200,
            {
                "mode": mode,
                "conversation_id": payload.get("conversation_id"),
                "assistant_id": payload.get("assistant_id"),
                "question": question,
                "document": str(KNOWLEDGE_PATH),
                "retrieval_source": retrieval_source,
                "agents": agent_outputs,
                "answer": final["answer"],
                "steps": final["steps"],
                "safety_notes": final["safety_notes"],
                "citations": final["citations"],
                "agent_consensus": final["agent_consensus"],
                "retrieved_context": retrieved_context,
            },
        )
    except Exception as error:
        return response(500, {"error": str(error)})
