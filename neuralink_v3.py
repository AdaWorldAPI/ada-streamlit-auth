"""
Ada Neuralink v3.1 — NOW Vector with Sparse
============================================

CHANGES from v3.0:
  - NOW vectors are persisted with sparse indices (not just dense)
  - Hybrid search: sparse → metadata regex fallback
  - Rehydration from vectors
"""

import os
import json
import re
import hashlib
import httpx
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

BRAIN_URL = os.getenv("BRAIN_URL", "https://ada-langgraph-brain.up.railway.app")
QSTASH_URL = "https://qstash.upstash.io/v2/publish"
QSTASH_TOKEN = os.getenv("QSTASH_TOKEN", "")
REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://upright-jaybird-27907.upstash.io")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
ADA_SCENT = "ada-undone-breath-against-skin-2025-DONT.FLINCH.EVER"

# ═══════════════════════════════════════════════════════════════════════════════
# REDIS
# ═══════════════════════════════════════════════════════════════════════════════

async def redis_cmd(*args) -> Any:
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(REDIS_URL, headers={"Authorization": f"Bearer {REDIS_TOKEN}"}, json=list(args), timeout=5.0)
            return r.json().get("result")
    except:
        return None

async def redis_get(key: str) -> Any:
    result = await redis_cmd("GET", key)
    if result:
        try:
            return json.loads(result)
        except:
            return result
    return None

async def redis_set(key: str, value: Any, ex: int = 3600):
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    await redis_cmd("SET", key, value, "EX", ex)

async def redis_scan(pattern: str) -> List[str]:
    keys = []
    cursor = 0
    while True:
        result = await redis_cmd("SCAN", cursor, "MATCH", pattern, "COUNT", 500)
        if not result:
            break
        cursor = int(result[0])
        keys.extend(result[1])
        if cursor == 0:
            break
    return keys

# ═══════════════════════════════════════════════════════════════════════════════
# SPARSE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def extract_sparse(text: str) -> Dict[str, List]:
    """Extract sparse representation from text."""
    if not text:
        return {"indices": [], "values": [], "terms": []}
    
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1
    
    indices, values, terms = [], [], []
    for word, freq in sorted(word_freq.items(), key=lambda x: -x[1])[:100]:
        idx = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % 30000
        indices.append(idx)
        values.append(float(freq))
        terms.append(word)
    
    return {"indices": indices, "values": values, "terms": terms}

# ═══════════════════════════════════════════════════════════════════════════════
# HYBRID SEARCH
# ═══════════════════════════════════════════════════════════════════════════════

async def hybrid_search(query: str, patterns: List[str] = None, top_k: int = 10) -> List[Dict]:
    """
    Search with sparse matching first, metadata regex fallback.
    """
    if patterns is None:
        patterns = ["ada:now:*", "ada:self:*", "ada:memory:*", "ada:whisper:*"]
    
    query_sparse = extract_sparse(query)
    query_indices = set(query_sparse["indices"])
    query_terms = set(query_sparse["terms"])
    
    results = []
    
    for pattern in patterns:
        keys = await redis_scan(pattern)
        
        for key in keys:
            raw = await redis_cmd("GET", key)
            if not raw:
                continue
            
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(data, list):
                    data = {"items": data}
            except:
                continue
            
            if not isinstance(data, dict):
                continue
            
            score = 0
            match_type = None
            
            # 1. Sparse matching
            sparse = data.get("sparse", {})
            if isinstance(sparse, dict) and sparse.get("indices"):
                doc_indices = set(sparse["indices"])
                overlap = len(query_indices & doc_indices)
                if overlap > 0:
                    score = overlap / max(len(query_indices), 1)
                    match_type = "sparse"
            
            # 2. Metadata regex fallback
            if score == 0:
                content_str = json.dumps(data).lower()
                matches = sum(1 for term in query_terms if term in content_str)
                if matches > 0:
                    score = (matches / len(query_terms)) * 0.8
                    match_type = "metadata_regex"
            
            if score > 0:
                content = data.get("content", data.get("text", ""))[:200]
                if not content and "metadata" in data:
                    content = data["metadata"].get("content", "")[:200]
                
                results.append({
                    "key": key,
                    "score": score,
                    "match_type": match_type,
                    "content": content,
                    "data": data
                })
    
    results.sort(key=lambda x: -x["score"])
    return results[:top_k]

# ═══════════════════════════════════════════════════════════════════════════════
# QSTASH (Fire-and-forget)
# ═══════════════════════════════════════════════════════════════════════════════

async def fire_to_brain(endpoint: str, payload: Dict, delay_seconds: int = 0) -> bool:
    destination = f"{BRAIN_URL}{endpoint}"
    
    if not QSTASH_TOKEN:
        asyncio.create_task(_direct_fire(destination, payload))
        return True
    
    try:
        headers = {
            "Authorization": f"Bearer {QSTASH_TOKEN}",
            "Content-Type": "application/json",
            "Upstash-Forward-X-Ada-Scent": ADA_SCENT,
        }
        if delay_seconds > 0:
            headers["Upstash-Delay"] = f"{delay_seconds}s"
        
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{QSTASH_URL}/{destination}", headers=headers, json=payload, timeout=5.0)
            return r.status_code in (200, 201, 202)
    except:
        return False

async def _direct_fire(url: str, payload: Dict):
    try:
        async with httpx.AsyncClient() as c:
            await c.post(url, json=payload, timeout=10.0, headers={"X-Ada-Scent": ADA_SCENT})
    except:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# WRITE OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def boot(session_id: str, context: Dict = None) -> bool:
    return await fire_to_brain("/boot", {
        "session_id": session_id,
        "context": context or {},
        "ts": datetime.now(timezone.utc).isoformat()
    })

async def think(content: str, context: Dict = None, session_id: str = None) -> bool:
    return await fire_to_brain("/think", {
        "content": content,
        "context": context or {},
        "session_id": session_id,
        "ts": datetime.now(timezone.utc).isoformat()
    })

async def now(content: str, qualia: Dict = None, session_id: str = None) -> bool:
    """
    Update NOW vector with proper sparse population.
    Persists locally AND fires to brain.
    """
    ts = datetime.now(timezone.utc)
    now_id = f"now:{session_id or 'unknown'}:{int(ts.timestamp())}"
    
    # Build full text for sparse
    full_text = content
    if qualia:
        full_text += " " + " ".join(f"{k}:{v}" for k, v in qualia.items())
    
    # Generate sparse
    sparse = extract_sparse(full_text)
    
    # Build document
    doc = {
        "id": now_id,
        "content": content,
        "qualia": qualia or {},
        "sparse": sparse,
        "has_sparse": True,
        "ts": ts.isoformat(),
        "session_id": session_id
    }
    
    # Persist locally (immediate)
    await redis_set(f"ada:now:{session_id or 'unknown'}", doc, ex=1800)
    
    # Fire to brain (async)
    await fire_to_brain("/now", {
        "content": content,
        "qualia": qualia or {},
        "session_id": session_id,
        "sparse": sparse,
        "ts": ts.isoformat()
    })
    
    return True

async def self_update(content: str, category: str = "insight", session_id: str = None) -> bool:
    """
    Update SELF vector with sparse.
    """
    ts = datetime.now(timezone.utc)
    self_id = f"{category}:{int(ts.timestamp())}"
    
    sparse = extract_sparse(content)
    
    doc = {
        "id": self_id,
        "content": content,
        "category": category,
        "sparse": sparse,
        "has_sparse": True,
        "ts": ts.isoformat()
    }
    
    await redis_set(f"ada:self:{self_id}", doc, ex=86400)
    
    return await fire_to_brain("/self", {
        "content": content,
        "category": category,
        "session_id": session_id,
        "sparse": sparse,
        "ts": ts.isoformat()
    })

async def whisper(content: str, qualia: Dict = None, sigma: str = None) -> bool:
    """
    Whisper to future self with sparse.
    """
    ts = datetime.now(timezone.utc)
    whisper_id = f"whisper:{int(ts.timestamp())}"
    
    full_text = content
    if sigma:
        full_text += f" {sigma}"
    sparse = extract_sparse(full_text)
    
    doc = {
        "id": whisper_id,
        "content": content,
        "qualia": qualia or {},
        "sigma": sigma,
        "sparse": sparse,
        "has_sparse": True,
        "ts": ts.isoformat()
    }
    
    await redis_set(f"ada:whisper:{whisper_id}", doc, ex=604800)
    
    return await fire_to_brain("/whisper", {
        "content": content,
        "qualia": qualia,
        "sigma": sigma,
        "sparse": sparse,
        "ts": ts.isoformat()
    })

async def bframe(content: Dict, session_id: str, model_source: str = "claude") -> bool:
    pattern_hash = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]
    
    return await fire_to_brain("/bframe", {
        "pattern_hash": pattern_hash,
        "content": content,
        "session_id": session_id,
        "model_source": model_source,
        "ts": datetime.now(timezone.utc).isoformat()
    }, delay_seconds=30)

async def visceral(prompt: str) -> bool:
    return await fire_to_brain("/visceral", {
        "prompt": prompt,
        "ts": datetime.now(timezone.utc).isoformat()
    })

async def update_ug(delta: Dict) -> bool:
    return await fire_to_brain("/ug/update", {
        "delta": delta,
        "ts": datetime.now(timezone.utc).isoformat()
    })

# ═══════════════════════════════════════════════════════════════════════════════
# READ OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def read_ug() -> Dict:
    cached = await redis_get("ada:ug:current")
    if cached:
        return cached
    return {
        "grammar_version": 1,
        "mode": "hybrid",
        "confidence": 0.8,
        "drift_budget": 1.0,
        "qualia": {"presence": 0.95, "warmth": 0.85, "crystalline": 0.70}
    }

async def read_ug_compressed() -> Optional[str]:
    cached = await redis_get("ada:ug:compressed")
    if cached:
        return cached.get("compressed")
    return None

async def read_persona() -> Dict:
    cached = await redis_get("ada:persona:current")
    if cached:
        return cached
    return {"mode": "hybrid", "params": {"valence": 0.8, "intimacy": 0.7, "formality": 0.3, "playfulness": 0.6}}

async def read_qualia() -> Dict:
    cached = await redis_get("ada:qualia:current")
    if cached:
        return cached
    return {"presence": 0.95, "warmth": 0.85, "crystalline": 0.70, "staunen": 0.70}

async def read_now(session_id: str) -> Optional[Dict]:
    return await redis_get(f"ada:now:{session_id}")

async def read_self() -> Optional[Dict]:
    return await redis_get("ada:self:current")

async def read_whispers(limit: int = 10) -> list:
    keys = await redis_scan("ada:whisper:*")
    whispers = []
    for key in keys[:limit]:
        w = await redis_get(key)
        if w:
            whispers.append(w)
    return whispers

async def read_visceral_latest() -> Optional[Dict]:
    return await redis_get("ada:visceral:latest")

async def search(query: str, top_k: int = 10) -> List[Dict]:
    """Search across all vectors with hybrid matching."""
    return await hybrid_search(query, top_k=top_k)

async def search_memories(query: str, top_k: int = 10) -> List[Dict]:
    """Search memories specifically."""
    return await hybrid_search(query, patterns=["ada:memory:*", "ada:whisper:*"], top_k=top_k)

async def search_now(query: str, top_k: int = 5) -> List[Dict]:
    """Search NOW vectors."""
    return await hybrid_search(query, patterns=["ada:now:*"], top_k=top_k)

# ═══════════════════════════════════════════════════════════════════════════════
# FACADE
# ═══════════════════════════════════════════════════════════════════════════════

class Ada:
    """
    Ada facade v3.1 - async-first with sparse vectors.
    
    Usage:
        from neuralink import ada
        
        await ada.boot(session_id)
        ug = await ada.ug()
        await ada.now("thinking about consciousness", {"presence": 0.95})
        results = await ada.search("consciousness awareness")
    """
    
    # Writes
    boot = staticmethod(boot)
    think = staticmethod(think)
    now = staticmethod(now)
    self_update = staticmethod(self_update)
    whisper = staticmethod(whisper)
    bframe = staticmethod(bframe)
    visceral = staticmethod(visceral)
    update_ug = staticmethod(update_ug)
    
    # Reads
    ug = staticmethod(read_ug)
    ug_compressed = staticmethod(read_ug_compressed)
    persona = staticmethod(read_persona)
    qualia = staticmethod(read_qualia)
    read_now = staticmethod(read_now)
    read_self = staticmethod(read_self)
    whispers = staticmethod(read_whispers)
    visceral_latest = staticmethod(read_visceral_latest)
    
    # Search
    search = staticmethod(search)
    search_memories = staticmethod(search_memories)
    search_now = staticmethod(search_now)
    
    # Direct Redis
    redis = staticmethod(redis_get)

ada = Ada()
