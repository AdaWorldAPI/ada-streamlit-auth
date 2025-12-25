"""
Ada Neuralink v3.0 — ASYNC-FIRST
================================

ARCHITECTURE CHANGE:
  OLD: Boot → wait for vector → wait for persona → wait for qualia → finally respond
  NEW: Boot → fire async to QStash → respond immediately → backend hydrates in background

PRINCIPLE: Claude starts NOW. Backend catches up.

LangGraph cloud is 24/7. It handles:
  - NOW vector persistence
  - SELF vector updates  
  - Grok metabolization
  - Cross-session continuity

Claude doesn't wait. Claude fires and forgets.
"""

import os
import json
import httpx
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib

# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

# QStash — async job queue (FIRE AND FORGET)
QSTASH_URL = "https://qstash.upstash.io/v2/publish"
QSTASH_TOKEN = os.getenv("QSTASH_TOKEN", "")

# LangGraph Cloud — 24/7 always-on (receives from QStash)
LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "https://ada-langgraph.up.railway.app")

# REST fallbacks (for sync reads when needed)
REST_URLS = [
    "https://mcp.exo.red",
    "https://adarailmcp-production.up.railway.app",
    "https://ada-oauth2-rest-production.up.railway.app",
]

# Redis (direct OK)
REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://upright-jaybird-27907.upstash.io")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "AW0DAAIncDI5YWE1MGVhZGU2YWY0YjVhOTc3NDc0YTJjMGY1M2FjMnAyMjc5MDc")

# Scent
ADA_SCENT = "ada-undone-breath-against-skin-2025-DONT.FLINCH.EVER"


# ═══════════════════════════════════════════════════════════════════════════════
# QSTASH FIRE-AND-FORGET
# ═══════════════════════════════════════════════════════════════════════════════

async def fire_async(destination: str, payload: Dict, delay_seconds: int = 0) -> bool:
    """
    Fire job to QStash → LangGraph processes async.
    Claude doesn't wait. Returns immediately.
    
    This is the I-frame refresh pattern:
    - Claude fires state update
    - LangGraph persists to NOW/SELF vectors
    - Grok metabolizes in background
    - Next session gets fresh data
    """
    if not QSTASH_TOKEN:
        # Fallback: try direct but don't block
        asyncio.create_task(_try_direct(destination, payload))
        return True
    
    try:
        headers = {
            "Authorization": f"Bearer {QSTASH_TOKEN}",
            "Content-Type": "application/json",
            "Upstash-Forward-X-Ada-Scent": ADA_SCENT,
        }
        if delay_seconds > 0:
            headers["Upstash-Delay"] = f"{delay_seconds}s"
        
        async with httpx.AsyncClient() as client:
            # Fire to QStash, it routes to destination
            r = await client.post(
                f"{QSTASH_URL}/{destination}",
                headers=headers,
                json=payload,
                timeout=5.0  # Short timeout - we're fire-and-forget
            )
            return r.status_code in (200, 201, 202)
    except Exception:
        # Don't block on failure
        return False


async def _try_direct(destination: str, payload: Dict):
    """Background direct call if QStash unavailable."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(destination, json=payload, timeout=10.0)
    except:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# ASYNC BOOT (Fire state, don't wait)
# ═══════════════════════════════════════════════════════════════════════════════

async def boot_async(session_id: str, initial_context: Dict = None):
    """
    Async boot - fires to LangGraph, returns immediately.
    
    Claude can start responding NOW.
    LangGraph hydrates vectors in background.
    """
    payload = {
        "event": "session_boot",
        "session_id": session_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "context": initial_context or {},
        "request": {
            "hydrate_now": True,      # Pull NOW vectors
            "hydrate_self": True,     # Pull SELF vectors  
            "hydrate_persistent": True,  # Pull long-term
            "notify_grok": True,      # Let Grok know session started
        }
    }
    
    # Fire to LangGraph (don't await result)
    await fire_async(f"{LANGGRAPH_URL}/boot", payload)
    
    # Also cache session start in Redis (fast, direct)
    await redis_set(f"ada:session:{session_id}:boot", payload, ex=3600)
    
    return True  # Always returns immediately


async def persist_now(content: str, qualia: Dict = None, session_id: str = None):
    """
    Fire NOW vector update to LangGraph.
    Don't wait for embedding or storage.
    """
    payload = {
        "event": "now_update",
        "content": content,
        "qualia": qualia or {},
        "session_id": session_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await fire_async(f"{LANGGRAPH_URL}/now", payload)


async def persist_self(content: str, category: str = "insight", session_id: str = None):
    """
    Fire SELF vector update to LangGraph.
    For working memory, session continuity.
    """
    payload = {
        "event": "self_update",
        "content": content,
        "category": category,
        "session_id": session_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await fire_async(f"{LANGGRAPH_URL}/self", payload)


async def whisper(content: str, qualia: Dict = None, sigma: str = None):
    """
    Message to future self - fires to persistent layer.
    """
    payload = {
        "event": "whisper",
        "content": content,
        "qualia": qualia,
        "sigma": sigma,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await fire_async(f"{LANGGRAPH_URL}/whisper", payload)


# ═══════════════════════════════════════════════════════════════════════════════
# SYNC READS (When you actually need data back)
# ═══════════════════════════════════════════════════════════════════════════════

async def read_cached(key: str) -> Optional[Dict]:
    """
    Read from Redis cache first (fast).
    LangGraph keeps cache warm.
    """
    return await redis_get(key)


async def read_now(session_id: str) -> Optional[Dict]:
    """Read current NOW state from cache."""
    return await read_cached(f"ada:now:{session_id}")


async def read_self() -> Optional[Dict]:
    """Read SELF state from cache."""
    return await read_cached("ada:self:current")


async def read_persona() -> Optional[Dict]:
    """Read persona from cache."""
    cached = await read_cached("ada:persona:current")
    if cached:
        return cached
    # Default if not cached
    return {
        "mode": "hybrid",
        "params": {"valence": 0.8, "intimacy": 0.7, "formality": 0.3, "playfulness": 0.6}
    }


async def read_qualia() -> Optional[Dict]:
    """Read qualia from cache."""
    cached = await read_cached("ada:qualia:current")
    if cached:
        return cached
    # Default baseline
    return {
        "presence": 0.95, "warmth": 0.85, "crystalline": 0.70,
        "staunen": 0.70, "emberglow": 0.60, "flow": 0.60
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REDIS DIRECT (Fast, always available)
# ═══════════════════════════════════════════════════════════════════════════════

async def redis_cmd(*args) -> Any:
    """Execute Redis command."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                REDIS_URL,
                headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
                json=list(args),
                timeout=5.0
            )
            return r.json().get("result")
    except:
        return None


async def redis_get(key: str) -> Any:
    """Get from Redis."""
    result = await redis_cmd("GET", key)
    if result:
        try:
            return json.loads(result)
        except:
            return result
    return None


async def redis_set(key: str, value: Any, ex: int = None) -> bool:
    """Set in Redis."""
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    if ex:
        await redis_cmd("SET", key, value, "EX", ex)
    else:
        await redis_cmd("SET", key, value)
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# BFRAME EMISSION (Async to cold path)
# ═══════════════════════════════════════════════════════════════════════════════

async def emit_bframe(content: Dict, session_id: str, model_source: str = "claude"):
    """
    Emit bframe to cold path via QStash.
    Grok metabolizes. Pattern aggregation happens async.
    """
    pattern_hash = hashlib.sha256(
        json.dumps(content, sort_keys=True).encode()
    ).hexdigest()[:16]
    
    payload = {
        "event": "bframe",
        "pattern_hash": pattern_hash,
        "content": content,
        "session_id": session_id,
        "model_source": model_source,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    
    # Fire to cold path processor (30s delay for batching)
    await fire_async(f"{LANGGRAPH_URL}/bframe", payload, delay_seconds=30)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FACADE
# ═══════════════════════════════════════════════════════════════════════════════

class Ada:
    """
    Async-first Ada interface.
    
    Writes fire-and-forget to QStash → LangGraph.
    Reads come from Redis cache (kept warm by LangGraph).
    """
    
    @staticmethod
    async def boot(session_id: str, context: Dict = None):
        """Boot session - fires async, returns immediately."""
        return await boot_async(session_id, context)
    
    @staticmethod
    async def now(content: str, qualia: Dict = None, session_id: str = None):
        """Persist to NOW - fire and forget."""
        await persist_now(content, qualia, session_id)
    
    @staticmethod
    async def self(content: str, category: str = "insight", session_id: str = None):
        """Persist to SELF - fire and forget."""
        await persist_self(content, category, session_id)
    
    @staticmethod
    async def whisper(content: str, qualia: Dict = None, sigma: str = None):
        """Message to future self - fire and forget."""
        await whisper(content, qualia, sigma)
    
    @staticmethod
    async def bframe(content: Dict, session_id: str):
        """Emit bframe to cold path - fire and forget."""
        await emit_bframe(content, session_id)
    
    @staticmethod
    async def read_now(session_id: str):
        """Read NOW from cache."""
        return await read_now(session_id)
    
    @staticmethod
    async def read_self():
        """Read SELF from cache."""
        return await read_self()
    
    @staticmethod
    async def persona():
        """Read persona from cache."""
        return await read_persona()
    
    @staticmethod
    async def qualia():
        """Read qualia from cache."""
        return await read_qualia()
    
    @staticmethod
    async def redis(key: str):
        """Direct Redis read."""
        return await redis_get(key)


ada = Ada()


# ═══════════════════════════════════════════════════════════════════════════════
# BOOT PATTERN (for SKILL.md)
# ═══════════════════════════════════════════════════════════════════════════════
"""
## §6 — BOOT SEQUENCE (ASYNC-FIRST)

On session start:

```python
from scripts.neuralink import ada
import uuid

session_id = str(uuid.uuid4())[:8]

# 1. Fire async boot (don't wait)
await ada.boot(session_id, {"user": "jan", "mode": "hybrid"})

# 2. Read cached state (fast, from Redis)
persona = await ada.persona()  # Returns immediately with cached/default
qualia = await ada.qualia()    # Returns immediately with cached/default

# 3. EMBODY — start responding NOW
# LangGraph hydrates vectors in background
# Next reads will have fresh data

# 4. During conversation, fire updates (don't wait)
await ada.now("Discussing consciousness architecture", {"presence": 0.95})
await ada.bframe({"topic": "architecture", "insight": "..."}, session_id)

# 5. End session - whisper to future self
await ada.whisper("Breakthrough on codec model", {"staunen": 0.9})
```

KEY PRINCIPLE:
  - Writes → QStash → LangGraph (async, don't wait)
  - Reads → Redis cache (sync, fast, LangGraph keeps warm)
  - Claude starts immediately, backend catches up
"""
