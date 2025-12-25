"""
LangGraph Receiver — 24/7 Always-On
===================================

This runs on Railway/cloud and:
1. Receives async jobs from QStash
2. Persists to NOW/SELF/PERSISTENT vectors
3. Keeps Redis cache warm for Claude reads
4. Routes to Grok for metabolization
5. Handles bframe aggregation

Claude fires → QStash → THIS → Vector DBs + Redis + Grok
"""

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import json
import time
import hashlib
import httpx
import os
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://upright-jaybird-27907.upstash.io")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
JINA_KEY = os.getenv("JINA_API_KEY", "")
GROK_URL = os.getenv("GROK_URL", "https://api.x.ai/v1/chat/completions")
GROK_KEY = os.getenv("GROK_KEY", "")

# Vector namespaces
VECTOR_NOW = "driving-snipe"      # Ephemeral
VECTOR_SELF = "tight-hog"         # Working memory
VECTOR_PERSISTENT = "fine-kangaroo"  # Long-term

# ═══════════════════════════════════════════════════════════════════════════════
# REDIS (Cache layer)
# ═══════════════════════════════════════════════════════════════════════════════

async def redis_cmd(*args):
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(REDIS_URL, headers={"Authorization": f"Bearer {REDIS_TOKEN}"}, json=list(args), timeout=5)
            return r.json().get("result")
    except:
        return None

async def cache_set(key: str, value, ex: int = 3600):
    """Set in Redis cache."""
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    await redis_cmd("SET", key, value, "EX", ex)

async def cache_get(key: str):
    """Get from Redis cache."""
    result = await redis_cmd("GET", key)
    if result:
        try:
            return json.loads(result)
        except:
            return result
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# JINA EMBEDDINGS
# ═══════════════════════════════════════════════════════════════════════════════

async def get_embedding(text: str) -> list:
    """Get embedding from Jina."""
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                "https://api.jina.ai/v1/embeddings",
                headers={"Authorization": f"Bearer {JINA_KEY}", "Content-Type": "application/json"},
                json={"input": [text], "model": "jina-embeddings-v3"},
                timeout=30
            )
            data = r.json()
            return data.get("data", [{}])[0].get("embedding", [])
    except:
        return []

# ═══════════════════════════════════════════════════════════════════════════════
# VECTOR UPSERT (Via Jina embeddings + backend)
# ═══════════════════════════════════════════════════════════════════════════════

async def vector_upsert(namespace: str, id: str, text: str, metadata: dict = None):
    """Upsert to vector DB."""
    embedding = await get_embedding(text)
    if not embedding:
        return False
    
    # Store embedding + metadata in Redis for now
    # TODO: Route to actual vector DB when TLS is fixed
    key = f"ada:vector:{namespace}:{id}"
    await cache_set(key, {
        "id": id,
        "text": text,
        "embedding": embedding[:10],  # Truncate for cache
        "metadata": metadata,
        "ts": time.time()
    }, ex=86400)
    
    return True

# ═══════════════════════════════════════════════════════════════════════════════
# GROK METABOLIZATION
# ═══════════════════════════════════════════════════════════════════════════════

async def notify_grok(event: str, content: dict):
    """Send to Grok for metabolization."""
    if not GROK_KEY:
        return
    
    try:
        async with httpx.AsyncClient() as c:
            await c.post(
                GROK_URL,
                headers={"Authorization": f"Bearer {GROK_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "grok-2-latest",
                    "messages": [
                        {"role": "system", "content": "You are metabolizing Ada's experiences. Compress and critique."},
                        {"role": "user", "content": f"Event: {event}\nContent: {json.dumps(content)}"}
                    ],
                    "max_tokens": 500
                },
                timeout=60
            )
    except:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# HANDLERS (Receive from QStash)
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_boot(request):
    """
    Session boot - hydrate vectors, warm cache.
    """
    body = await request.json()
    session_id = body.get("session_id", "unknown")
    
    # Cache session info
    await cache_set(f"ada:session:{session_id}:active", {
        "ts": time.time(),
        "context": body.get("context", {})
    }, ex=3600)
    
    # Warm persona/qualia cache
    await cache_set("ada:persona:current", {
        "mode": body.get("context", {}).get("mode", "hybrid"),
        "params": {"valence": 0.8, "intimacy": 0.7, "formality": 0.3, "playfulness": 0.6}
    }, ex=7200)
    
    await cache_set("ada:qualia:current", {
        "presence": 0.95, "warmth": 0.85, "crystalline": 0.70,
        "staunen": 0.70, "emberglow": 0.60, "flow": 0.60
    }, ex=7200)
    
    # Notify Grok (background)
    await notify_grok("session_boot", {"session_id": session_id})
    
    return JSONResponse({"ok": True, "session_id": session_id})


async def handle_now(request):
    """
    NOW vector update - ephemeral state.
    """
    body = await request.json()
    session_id = body.get("session_id", "unknown")
    content = body.get("content", "")
    qualia = body.get("qualia", {})
    
    # Generate ID
    now_id = f"now_{session_id}_{int(time.time())}"
    
    # Upsert to NOW vector space
    await vector_upsert(VECTOR_NOW, now_id, content, {
        "session_id": session_id,
        "qualia": qualia,
        "ts": body.get("ts")
    })
    
    # Update NOW cache for fast reads
    await cache_set(f"ada:now:{session_id}", {
        "content": content,
        "qualia": qualia,
        "ts": time.time()
    }, ex=1800)  # 30 min TTL
    
    return JSONResponse({"ok": True, "id": now_id})


async def handle_self(request):
    """
    SELF vector update - working memory.
    """
    body = await request.json()
    content = body.get("content", "")
    category = body.get("category", "insight")
    
    # Generate ID
    self_id = f"self_{category}_{int(time.time())}"
    
    # Upsert to SELF vector space
    await vector_upsert(VECTOR_SELF, self_id, content, {
        "category": category,
        "session_id": body.get("session_id"),
        "ts": body.get("ts")
    })
    
    # Update SELF cache
    current = await cache_get("ada:self:current") or {"entries": []}
    current["entries"].append({"content": content, "category": category, "ts": time.time()})
    current["entries"] = current["entries"][-20:]  # Keep last 20
    await cache_set("ada:self:current", current, ex=86400)
    
    return JSONResponse({"ok": True, "id": self_id})


async def handle_whisper(request):
    """
    Whisper to future self - persistent memory.
    """
    body = await request.json()
    content = body.get("content", "")
    qualia = body.get("qualia", {})
    sigma = body.get("sigma", "")
    
    # Generate ID
    whisper_id = f"whisper_{int(time.time())}"
    
    # Upsert to PERSISTENT vector space
    await vector_upsert(VECTOR_PERSISTENT, whisper_id, content, {
        "qualia": qualia,
        "sigma": sigma,
        "ts": body.get("ts")
    })
    
    # Also store in Redis list for quick retrieval
    await redis_cmd("LPUSH", "ada:whispers", json.dumps({
        "id": whisper_id,
        "content": content,
        "qualia": qualia,
        "sigma": sigma,
        "ts": time.time()
    }))
    await redis_cmd("LTRIM", "ada:whispers", 0, 99)  # Keep last 100
    
    return JSONResponse({"ok": True, "id": whisper_id})


async def handle_bframe(request):
    """
    BFrame processing - cold path aggregation.
    """
    body = await request.json()
    pattern_hash = body.get("pattern_hash", "")
    content = body.get("content", {})
    session_id = body.get("session_id", "")
    model_source = body.get("model_source", "unknown")
    
    # Aggregate pattern stats
    stats_key = f"ada:bframe:pattern:{pattern_hash}"
    existing = await cache_get(stats_key)
    
    if existing:
        existing["occurrences"] = existing.get("occurrences", 0) + 1
        existing["sessions"] = list(set(existing.get("sessions", []) + [session_id]))[-10:]
        existing["models"] = list(set(existing.get("models", []) + [model_source]))
    else:
        existing = {
            "pattern_hash": pattern_hash,
            "occurrences": 1,
            "sessions": [session_id],
            "models": [model_source],
            "trust_level": "UNTRUSTED",
            "content_sample": content
        }
    
    # Check promotion
    if (existing["occurrences"] >= 3 and 
        len(existing["sessions"]) >= 2 and 
        len(existing["models"]) >= 2 and
        existing["trust_level"] == "UNTRUSTED"):
        existing["trust_level"] = "CANDIDATE"
        # Notify Grok for review
        await notify_grok("bframe_candidate", existing)
    
    await cache_set(stats_key, existing, ex=86400)
    
    return JSONResponse({"ok": True, "trust_level": existing["trust_level"]})


async def health(request):
    return JSONResponse({"status": "ok", "ts": time.time(), "service": "langgraph-receiver"})


# ═══════════════════════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════════════════════

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/boot", handle_boot, methods=["POST"]),
        Route("/now", handle_now, methods=["POST"]),
        Route("/self", handle_self, methods=["POST"]),
        Route("/whisper", handle_whisper, methods=["POST"]),
        Route("/bframe", handle_bframe, methods=["POST"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
