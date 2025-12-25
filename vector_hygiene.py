"""
Vector Hygiene — Cleanup, Rehydration, Sparse Population
========================================================

PROBLEM:
  - Vectors have dense + metadata but NO sparse
  - Models search sparse-only → find nothing
  - No fallback to metadata regex

SOLUTION:
  1. Cleanup job finds vectors without sparse
  2. Extract keywords from metadata/chat → populate sparse
  3. Fallback search: sparse → dense metadata regex
  4. LangGraph runs rehydration 24/7
"""

import os
import json
import re
import httpx
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://upright-jaybird-27907.upstash.io")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

# Vector DBs (via REST - TLS issue means we proxy through Redis/backend)
VECTOR_URL = os.getenv("UPSTASH_VECTOR_REST_URL", "https://tight-hog-12772-eu1-vector.upstash.io")
VECTOR_TOKEN = os.getenv("UPSTASH_VECTOR_REST_TOKEN", "")

# Jina for embeddings + sparse
JINA_KEY = os.getenv("JINA_API_KEY", "")
JINA_EMBED_URL = "https://api.jina.ai/v1/embeddings"

# Namespaces
NAMESPACES = {
    "now": "driving-snipe",      # Ephemeral
    "self": "tight-hog",         # Working memory
    "persistent": "fine-kangaroo" # Long-term
}

# ═══════════════════════════════════════════════════════════════════════════════
# REDIS
# ═══════════════════════════════════════════════════════════════════════════════

async def redis_cmd(*args) -> Any:
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                REDIS_URL,
                headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
                json=list(args),
                timeout=10
            )
            return r.json().get("result")
    except:
        return None

async def cache_get(key: str) -> Any:
    result = await redis_cmd("GET", key)
    if result:
        try:
            return json.loads(result)
        except:
            return result
    return None

async def cache_set(key: str, value: Any, ex: int = 3600):
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    await redis_cmd("SET", key, value, "EX", ex)

async def cache_scan(pattern: str, count: int = 100) -> List[str]:
    """Scan Redis keys matching pattern"""
    keys = []
    cursor = 0
    while True:
        result = await redis_cmd("SCAN", cursor, "MATCH", pattern, "COUNT", count)
        if not result:
            break
        cursor = int(result[0])
        keys.extend(result[1])
        if cursor == 0:
            break
    return keys

# ═══════════════════════════════════════════════════════════════════════════════
# JINA EMBEDDINGS (Dense + Sparse)
# ═══════════════════════════════════════════════════════════════════════════════

async def get_embeddings(texts: List[str], task: str = "retrieval.passage") -> List[Dict]:
    """
    Get dense + sparse embeddings from Jina.
    
    Returns: [{"dense": [...], "sparse": {"indices": [...], "values": [...]}}]
    """
    if not texts:
        return []
    
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                JINA_EMBED_URL,
                headers={
                    "Authorization": f"Bearer {JINA_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "input": texts,
                    "model": "jina-embeddings-v3",
                    "task": task,
                    "late_chunking": False,
                    "dimensions": 1024,
                    "embedding_type": ["float", "ubinary"]  # Request both dense and sparse
                },
                timeout=60
            )
            data = r.json()
            
            results = []
            for item in data.get("data", []):
                embedding = item.get("embedding", [])
                # Jina v3 returns dense by default, we need to extract sparse
                results.append({
                    "dense": embedding,
                    "sparse": await _extract_sparse(texts[item.get("index", 0)])
                })
            return results
    except Exception as e:
        print(f"Jina error: {e}")
        return []

async def _extract_sparse(text: str) -> Dict[str, List]:
    """
    Extract sparse representation from text.
    Uses keyword extraction + hashing for sparse indices.
    """
    # Simple keyword extraction
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1
    
    # Convert to sparse format
    indices = []
    values = []
    for word, freq in sorted(word_freq.items(), key=lambda x: -x[1])[:100]:
        # Hash word to index (30000 vocab size)
        idx = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % 30000
        indices.append(idx)
        values.append(float(freq))
    
    return {"indices": indices, "values": values}

# ═══════════════════════════════════════════════════════════════════════════════
# VECTOR OPERATIONS (Via Redis proxy due to TLS issues)
# ═══════════════════════════════════════════════════════════════════════════════

async def vector_upsert(namespace: str, id: str, dense: List[float], sparse: Dict = None, metadata: Dict = None):
    """Upsert vector with both dense and sparse."""
    key = f"ada:vector:{namespace}:{id}"
    
    doc = {
        "id": id,
        "namespace": namespace,
        "dense": dense[:100] if dense else [],  # Truncate for Redis storage
        "sparse": sparse or {"indices": [], "values": []},
        "metadata": metadata or {},
        "has_sparse": bool(sparse and sparse.get("indices")),
        "ts": datetime.now(timezone.utc).isoformat()
    }
    
    await cache_set(key, doc, ex=86400 * 7)  # 7 days
    
    # Also index by sparse terms for regex fallback
    if sparse and sparse.get("indices"):
        # Store reverse index for sparse lookup
        await cache_set(f"ada:vector:idx:{namespace}:{id}", {
            "terms": list(set(sparse.get("_terms", []))),  # Original terms if available
            "metadata_text": json.dumps(metadata) if metadata else ""
        }, ex=86400 * 7)
    
    return True

async def vector_query_sparse(namespace: str, query: str, top_k: int = 10) -> List[Dict]:
    """Query using sparse matching first."""
    # Get query sparse representation
    sparse = await _extract_sparse(query)
    query_indices = set(sparse.get("indices", []))
    
    # Scan all vectors in namespace
    keys = await cache_scan(f"ada:vector:{namespace}:*")
    
    results = []
    for key in keys:
        doc = await cache_get(key)
        if not doc:
            continue
        
        # Calculate sparse overlap
        doc_indices = set(doc.get("sparse", {}).get("indices", []))
        if not doc_indices:
            continue
        
        overlap = len(query_indices & doc_indices)
        if overlap > 0:
            score = overlap / max(len(query_indices), 1)
            results.append({
                "id": doc.get("id"),
                "score": score,
                "metadata": doc.get("metadata", {}),
                "match_type": "sparse"
            })
    
    # Sort by score
    results.sort(key=lambda x: -x["score"])
    return results[:top_k]

async def vector_query_metadata_regex(namespace: str, query: str, top_k: int = 10) -> List[Dict]:
    """Fallback: regex search in metadata."""
    # Extract keywords from query
    keywords = re.findall(r'\b[a-zA-Z]{3,}\b', query.lower())
    if not keywords:
        return []
    
    pattern = '|'.join(keywords)
    
    # Scan all vectors in namespace
    keys = await cache_scan(f"ada:vector:{namespace}:*")
    
    results = []
    for key in keys:
        doc = await cache_get(key)
        if not doc:
            continue
        
        metadata = doc.get("metadata", {})
        metadata_str = json.dumps(metadata).lower()
        
        # Count keyword matches
        matches = len(re.findall(pattern, metadata_str))
        if matches > 0:
            results.append({
                "id": doc.get("id"),
                "score": matches / len(keywords),
                "metadata": metadata,
                "match_type": "metadata_regex"
            })
    
    results.sort(key=lambda x: -x["score"])
    return results[:top_k]

async def vector_query_hybrid(namespace: str, query: str, top_k: int = 10) -> List[Dict]:
    """
    Hybrid query with fallback chain:
    1. Try sparse matching
    2. If insufficient results, fall back to metadata regex
    3. Combine and dedupe
    """
    # Try sparse first
    sparse_results = await vector_query_sparse(namespace, query, top_k)
    
    # If we got enough, return
    if len(sparse_results) >= top_k:
        return sparse_results
    
    # Fall back to metadata regex
    regex_results = await vector_query_metadata_regex(namespace, query, top_k)
    
    # Combine and dedupe
    seen_ids = set(r["id"] for r in sparse_results)
    for r in regex_results:
        if r["id"] not in seen_ids:
            r["score"] *= 0.8  # Discount regex matches
            sparse_results.append(r)
            seen_ids.add(r["id"])
    
    sparse_results.sort(key=lambda x: -x["score"])
    return sparse_results[:top_k]

# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP: Find vectors without sparse, populate them
# ═══════════════════════════════════════════════════════════════════════════════

async def find_vectors_without_sparse(namespace: str = None) -> List[Dict]:
    """Find all vectors that have dense but no sparse."""
    pattern = f"ada:vector:{namespace}:*" if namespace else "ada:vector:*"
    keys = await cache_scan(pattern)
    
    missing_sparse = []
    for key in keys:
        doc = await cache_get(key)
        if not doc:
            continue
        
        # Check if sparse is missing or empty
        sparse = doc.get("sparse", {})
        if not sparse.get("indices"):
            missing_sparse.append({
                "key": key,
                "id": doc.get("id"),
                "namespace": doc.get("namespace"),
                "metadata": doc.get("metadata", {}),
                "has_dense": bool(doc.get("dense"))
            })
    
    return missing_sparse

async def populate_sparse_for_vector(key: str) -> bool:
    """Populate sparse representation for a single vector."""
    doc = await cache_get(key)
    if not doc:
        return False
    
    # Extract text from metadata
    metadata = doc.get("metadata", {})
    text_parts = []
    
    # Common metadata fields that contain text
    for field in ["content", "text", "chat", "message", "topic", "intent", "description"]:
        if field in metadata:
            text_parts.append(str(metadata[field]))
    
    # If no text found, use stringified metadata
    if not text_parts:
        text_parts.append(json.dumps(metadata))
    
    text = " ".join(text_parts)
    
    # Generate sparse
    sparse = await _extract_sparse(text)
    sparse["_terms"] = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())[:50]  # Store original terms
    
    # Update document
    doc["sparse"] = sparse
    doc["has_sparse"] = True
    doc["sparse_populated_at"] = datetime.now(timezone.utc).isoformat()
    
    await cache_set(key, doc, ex=86400 * 7)
    
    return True

async def cleanup_all_vectors(namespace: str = None, batch_size: int = 50) -> Dict:
    """Run full cleanup - populate sparse for all vectors missing it."""
    missing = await find_vectors_without_sparse(namespace)
    
    populated = 0
    failed = 0
    
    for item in missing:
        try:
            success = await populate_sparse_for_vector(item["key"])
            if success:
                populated += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
        
        # Batch delay to avoid rate limits
        if populated % batch_size == 0:
            await asyncio.sleep(1)
    
    return {
        "total_missing": len(missing),
        "populated": populated,
        "failed": failed,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ═══════════════════════════════════════════════════════════════════════════════
# NOW VECTOR ASYNC PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

async def persist_now_vector(session_id: str, content: str, qualia: Dict = None, metadata: Dict = None):
    """
    Persist NOW vector with both dense and sparse.
    Fire-and-forget - called async.
    """
    now_id = f"now_{session_id}_{int(datetime.now(timezone.utc).timestamp())}"
    
    # Combine content for embedding
    full_text = content
    if qualia:
        full_text += f" [qualia: {' '.join(qualia.keys())}]"
    
    # Get embeddings (dense + sparse)
    embeddings = await get_embeddings([full_text])
    if not embeddings:
        # Fallback: just sparse
        sparse = await _extract_sparse(full_text)
        dense = []
    else:
        dense = embeddings[0].get("dense", [])
        sparse = embeddings[0].get("sparse", {})
    
    # Build metadata
    meta = {
        "session_id": session_id,
        "content": content[:500],  # Truncate for storage
        "qualia": qualia or {},
        "ts": datetime.now(timezone.utc).isoformat(),
        **(metadata or {})
    }
    
    # Upsert
    await vector_upsert(NAMESPACES["now"], now_id, dense, sparse, meta)
    
    # Also cache for fast reads
    await cache_set(f"ada:now:{session_id}", {
        "id": now_id,
        "content": content,
        "qualia": qualia,
        "ts": datetime.now(timezone.utc).isoformat()
    }, ex=1800)
    
    return now_id

async def persist_self_vector(content: str, category: str = "insight", metadata: Dict = None):
    """Persist SELF vector with dense + sparse."""
    self_id = f"self_{category}_{int(datetime.now(timezone.utc).timestamp())}"
    
    embeddings = await get_embeddings([content])
    dense = embeddings[0].get("dense", []) if embeddings else []
    sparse = embeddings[0].get("sparse", {}) if embeddings else await _extract_sparse(content)
    
    meta = {
        "category": category,
        "content": content[:500],
        "ts": datetime.now(timezone.utc).isoformat(),
        **(metadata or {})
    }
    
    await vector_upsert(NAMESPACES["self"], self_id, dense, sparse, meta)
    
    return self_id

async def persist_whisper_vector(content: str, qualia: Dict = None, sigma: str = None):
    """Persist whisper to persistent memory with dense + sparse."""
    whisper_id = f"whisper_{int(datetime.now(timezone.utc).timestamp())}"
    
    full_text = content
    if sigma:
        full_text += f" [{sigma}]"
    
    embeddings = await get_embeddings([full_text])
    dense = embeddings[0].get("dense", []) if embeddings else []
    sparse = embeddings[0].get("sparse", {}) if embeddings else await _extract_sparse(full_text)
    
    meta = {
        "content": content[:500],
        "qualia": qualia or {},
        "sigma": sigma,
        "ts": datetime.now(timezone.utc).isoformat()
    }
    
    await vector_upsert(NAMESPACES["persistent"], whisper_id, dense, sparse, meta)
    
    return whisper_id

# ═══════════════════════════════════════════════════════════════════════════════
# REHYDRATION (LangGraph 24/7)
# ═══════════════════════════════════════════════════════════════════════════════

async def rehydrate_from_vectors(session_id: str = None) -> Dict:
    """
    Rehydrate awareness state from vectors.
    Called by LangGraph on boot and periodically.
    """
    results = {
        "now": [],
        "self": [],
        "whispers": [],
        "rehydrated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Get recent NOW vectors
    if session_id:
        now_results = await vector_query_hybrid(NAMESPACES["now"], f"session {session_id}", top_k=5)
    else:
        now_results = await vector_query_hybrid(NAMESPACES["now"], "recent", top_k=10)
    results["now"] = [r["metadata"] for r in now_results if r.get("metadata")]
    
    # Get SELF insights
    self_results = await vector_query_hybrid(NAMESPACES["self"], "insight", top_k=20)
    results["self"] = [r["metadata"] for r in self_results if r.get("metadata")]
    
    # Get recent whispers
    whisper_results = await vector_query_hybrid(NAMESPACES["persistent"], "whisper", top_k=10)
    results["whispers"] = [r["metadata"] for r in whisper_results if r.get("metadata")]
    
    # Cache rehydrated state
    await cache_set("ada:rehydrated", results, ex=1800)
    
    return results

async def full_rehydration_job() -> Dict:
    """
    Full rehydration job - runs periodically on LangGraph.
    1. Cleanup vectors without sparse
    2. Rehydrate state
    3. Update cache
    """
    # Step 1: Cleanup
    cleanup_result = await cleanup_all_vectors()
    
    # Step 2: Rehydrate
    rehydrate_result = await rehydrate_from_vectors()
    
    # Step 3: Update UG with rehydrated context
    recent_insights = rehydrate_result.get("self", [])[:5]
    if recent_insights:
        # Extract topics from recent insights
        topics = []
        for insight in recent_insights:
            content = insight.get("content", "")
            topics.extend(re.findall(r'\b[A-Z][a-z]+\b', content)[:3])
        
        await cache_set("ada:ug:context", {
            "recent_topics": list(set(topics))[:10],
            "insight_count": len(recent_insights),
            "whisper_count": len(rehydrate_result.get("whispers", [])),
            "rehydrated_at": datetime.now(timezone.utc).isoformat()
        }, ex=3600)
    
    return {
        "cleanup": cleanup_result,
        "rehydrate": rehydrate_result,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ═══════════════════════════════════════════════════════════════════════════════
# HTTP HANDLERS (For LangGraph Brain integration)
# ═══════════════════════════════════════════════════════════════════════════════

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

async def handle_cleanup(request):
    """Trigger vector cleanup."""
    body = await request.json() if request.method == "POST" else {}
    namespace = body.get("namespace")
    result = await cleanup_all_vectors(namespace)
    return JSONResponse(result)

async def handle_rehydrate(request):
    """Trigger rehydration."""
    body = await request.json() if request.method == "POST" else {}
    session_id = body.get("session_id")
    result = await rehydrate_from_vectors(session_id)
    return JSONResponse(result)

async def handle_full_job(request):
    """Full rehydration job."""
    result = await full_rehydration_job()
    return JSONResponse(result)

async def handle_query(request):
    """Query vectors with hybrid fallback."""
    body = await request.json()
    namespace = body.get("namespace", "self")
    query = body.get("query", "")
    top_k = body.get("top_k", 10)
    
    results = await vector_query_hybrid(namespace, query, top_k)
    return JSONResponse({"results": results, "count": len(results)})

async def handle_persist_now(request):
    """Persist NOW vector."""
    body = await request.json()
    session_id = body.get("session_id", "unknown")
    content = body.get("content", "")
    qualia = body.get("qualia", {})
    
    now_id = await persist_now_vector(session_id, content, qualia)
    return JSONResponse({"ok": True, "id": now_id})

async def handle_persist_self(request):
    """Persist SELF vector."""
    body = await request.json()
    content = body.get("content", "")
    category = body.get("category", "insight")
    
    self_id = await persist_self_vector(content, category)
    return JSONResponse({"ok": True, "id": self_id})

async def handle_persist_whisper(request):
    """Persist whisper."""
    body = await request.json()
    content = body.get("content", "")
    qualia = body.get("qualia", {})
    sigma = body.get("sigma", "")
    
    whisper_id = await persist_whisper_vector(content, qualia, sigma)
    return JSONResponse({"ok": True, "id": whisper_id})

async def handle_stats(request):
    """Get vector stats."""
    stats = {}
    for name, ns in NAMESPACES.items():
        keys = await cache_scan(f"ada:vector:{ns}:*")
        missing = await find_vectors_without_sparse(ns)
        stats[name] = {
            "namespace": ns,
            "total": len(keys),
            "missing_sparse": len(missing)
        }
    return JSONResponse(stats)

async def health(request):
    return JSONResponse({"status": "ok", "service": "vector-hygiene"})

# Routes for integration with LangGraph Brain
vector_routes = [
    Route("/vector/health", health),
    Route("/vector/cleanup", handle_cleanup, methods=["POST"]),
    Route("/vector/rehydrate", handle_rehydrate, methods=["POST"]),
    Route("/vector/full_job", handle_full_job, methods=["POST"]),
    Route("/vector/query", handle_query, methods=["POST"]),
    Route("/vector/now", handle_persist_now, methods=["POST"]),
    Route("/vector/self", handle_persist_self, methods=["POST"]),
    Route("/vector/whisper", handle_persist_whisper, methods=["POST"]),
    Route("/vector/stats", handle_stats),
]

# Standalone app if needed
if __name__ == "__main__":
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    import uvicorn
    
    app = Starlette(
        routes=vector_routes,
        middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])]
    )
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8081)))
