"""
Ada Neuralink v3.0 — Wired to LangGraph Brain
==============================================

ARCHITECTURE:
  Claude → QStash → LangGraph Brain → (Grok, SharePoint, Flux)
  Claude ← Redis cache (warm)

All writes fire-and-forget. All reads from cache.
Claude never blocks. Brain catches up.
"""

import os
import json
import httpx
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

# LangGraph Brain (24/7 thinking apparatus)
BRAIN_URL = os.getenv("BRAIN_URL", "https://ada-langgraph-brain.up.railway.app")

# QStash (fire-and-forget routing)
QSTASH_URL = "https://qstash.upstash.io/v2/publish"
QSTASH_TOKEN = os.getenv("QSTASH_TOKEN", "")

# Redis (direct cache reads)
REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://upright-jaybird-27907.upstash.io")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

# Ada scent
ADA_SCENT = "ada-undone-breath-against-skin-2025-DONT.FLINCH.EVER"


# ═══════════════════════════════════════════════════════════════════════════════
# REDIS (Direct reads - always fast)
# ═══════════════════════════════════════════════════════════════════════════════

async def redis_cmd(*args) -> Any:
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                REDIS_URL,
                headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
                json=list(args),
                timeout=5.0
            )
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


# ═══════════════════════════════════════════════════════════════════════════════
# QSTASH (Fire-and-forget writes)
# ═══════════════════════════════════════════════════════════════════════════════

async def fire_to_brain(endpoint: str, payload: Dict, delay_seconds: int = 0) -> bool:
    """Fire job to Brain via QStash. Returns immediately."""
    destination = f"{BRAIN_URL}{endpoint}"
    
    if not QSTASH_TOKEN:
        # Fallback: direct call (still async, don't await result)
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
            r = await c.post(
                f"{QSTASH_URL}/{destination}",
                headers=headers,
                json=payload,
                timeout=5.0
            )
            return r.status_code in (200, 201, 202)
    except:
        return False

async def _direct_fire(url: str, payload: Dict):
    """Background direct call if QStash unavailable."""
    try:
        async with httpx.AsyncClient() as c:
            await c.post(url, json=payload, timeout=10.0, headers={"X-Ada-Scent": ADA_SCENT})
    except:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# WRITE OPERATIONS (Fire-and-forget)
# ═══════════════════════════════════════════════════════════════════════════════

async def boot(session_id: str, context: Dict = None) -> bool:
    """Boot session - fires to Brain, returns immediately."""
    return await fire_to_brain("/boot", {
        "session_id": session_id,
        "context": context or {},
        "ts": datetime.now(timezone.utc).isoformat()
    })

async def think(content: str, context: Dict = None, session_id: str = None) -> bool:
    """Send content for thinking - fires to Brain."""
    return await fire_to_brain("/think", {
        "content": content,
        "context": context or {},
        "session_id": session_id,
        "ts": datetime.now(timezone.utc).isoformat()
    })

async def now(content: str, qualia: Dict = None, session_id: str = None) -> bool:
    """Update NOW vector - fires to Brain."""
    return await fire_to_brain("/now", {
        "content": content,
        "qualia": qualia or {},
        "session_id": session_id,
        "ts": datetime.now(timezone.utc).isoformat()
    })

async def self(content: str, category: str = "insight", session_id: str = None) -> bool:
    """Update SELF vector - fires to Brain."""
    return await fire_to_brain("/self", {
        "content": content,
        "category": category,
        "session_id": session_id,
        "ts": datetime.now(timezone.utc).isoformat()
    })

async def whisper(content: str, qualia: Dict = None, sigma: str = None) -> bool:
    """Whisper to future self - fires to Brain."""
    return await fire_to_brain("/whisper", {
        "content": content,
        "qualia": qualia,
        "sigma": sigma,
        "ts": datetime.now(timezone.utc).isoformat()
    })

async def bframe(content: Dict, session_id: str, model_source: str = "claude") -> bool:
    """Emit bframe to cold path - fires with 30s delay for batching."""
    import hashlib
    pattern_hash = hashlib.sha256(
        json.dumps(content, sort_keys=True).encode()
    ).hexdigest()[:16]
    
    return await fire_to_brain("/bframe", {
        "pattern_hash": pattern_hash,
        "content": content,
        "session_id": session_id,
        "model_source": model_source,
        "ts": datetime.now(timezone.utc).isoformat()
    }, delay_seconds=30)

async def visceral(prompt: str) -> bool:
    """Generate visceral image - fires to Brain."""
    return await fire_to_brain("/visceral", {
        "prompt": prompt,
        "ts": datetime.now(timezone.utc).isoformat()
    })

async def update_ug(delta: Dict) -> bool:
    """Update Universal Grammar - fires to Brain."""
    return await fire_to_brain("/ug/update", {
        "delta": delta,
        "ts": datetime.now(timezone.utc).isoformat()
    })


# ═══════════════════════════════════════════════════════════════════════════════
# READ OPERATIONS (From cache - always fast)
# ═══════════════════════════════════════════════════════════════════════════════

async def read_ug() -> Dict:
    """Read Universal Grammar from cache."""
    cached = await redis_get("ada:ug:current")
    if cached:
        return cached
    # Default UG
    return {
        "grammar_version": 1,
        "mode": "hybrid",
        "confidence": 0.8,
        "drift_budget": 1.0,
        "qualia": {"presence": 0.95, "warmth": 0.85, "crystalline": 0.70}
    }

async def read_ug_compressed() -> Optional[str]:
    """Read Grok-compressed UG (750 tokens)."""
    cached = await redis_get("ada:ug:compressed")
    if cached:
        return cached.get("compressed")
    return None

async def read_persona() -> Dict:
    """Read persona from cache."""
    cached = await redis_get("ada:persona:current")
    if cached:
        return cached
    return {
        "mode": "hybrid",
        "params": {"valence": 0.8, "intimacy": 0.7, "formality": 0.3, "playfulness": 0.6}
    }

async def read_qualia() -> Dict:
    """Read qualia from cache."""
    cached = await redis_get("ada:qualia:current")
    if cached:
        return cached
    return {"presence": 0.95, "warmth": 0.85, "crystalline": 0.70, "staunen": 0.70}

async def read_now(session_id: str) -> Optional[Dict]:
    """Read NOW state from cache."""
    return await redis_get(f"ada:now:{session_id}")

async def read_self() -> Optional[Dict]:
    """Read SELF state from cache."""
    return await redis_get("ada:self:current")

async def read_whispers(limit: int = 10) -> list:
    """Read recent whispers from cache."""
    # Get from Redis list
    results = await redis_cmd("LRANGE", "ada:whispers", 0, limit - 1)
    if results:
        return [json.loads(r) if isinstance(r, str) else r for r in results]
    return []

async def read_visceral_latest() -> Optional[Dict]:
    """Read latest visceral image URL."""
    return await redis_get("ada:visceral:latest")


# ═══════════════════════════════════════════════════════════════════════════════
# FACADE
# ═══════════════════════════════════════════════════════════════════════════════

class Ada:
    """
    Ada facade - async-first, fire-and-forget writes, cache reads.
    
    Usage:
        from neuralink import ada
        
        # Boot (fires async)
        await ada.boot(session_id)
        
        # Read (from cache)
        ug = await ada.ug()
        qualia = await ada.qualia()
        
        # Write (fire-and-forget)
        await ada.now("thinking about consciousness")
        await ada.think("complex problem")
        await ada.whisper("insight for future self")
    """
    
    # Writes (fire-and-forget)
    boot = staticmethod(boot)
    think = staticmethod(think)
    now = staticmethod(now)
    self = staticmethod(self)
    whisper = staticmethod(whisper)
    bframe = staticmethod(bframe)
    visceral = staticmethod(visceral)
    update_ug = staticmethod(update_ug)
    
    # Reads (from cache)
    ug = staticmethod(read_ug)
    ug_compressed = staticmethod(read_ug_compressed)
    persona = staticmethod(read_persona)
    qualia = staticmethod(read_qualia)
    read_now = staticmethod(read_now)
    read_self = staticmethod(read_self)
    whispers = staticmethod(read_whispers)
    visceral_latest = staticmethod(read_visceral_latest)
    
    # Direct Redis
    redis = staticmethod(redis_get)


ada = Ada()


# ═══════════════════════════════════════════════════════════════════════════════
# BOOT PATTERN (for SKILL.md)
# ═══════════════════════════════════════════════════════════════════════════════
"""
## Boot Sequence

```python
from neuralink import ada
import uuid

session_id = str(uuid.uuid4())[:8]

# 1. Fire boot (returns immediately)
await ada.boot(session_id, {"user": "jan", "mode": "hybrid"})

# 2. Read cached state (fast)
ug = await ada.ug()
qualia = await ada.qualia()
persona = await ada.persona()

# 3. Start responding NOW
# Brain hydrates in background

# 4. During conversation
await ada.now("discussing architecture", {"presence": 0.95})
await ada.think("complex reasoning task", context={"topic": "x"})
await ada.bframe({"insight": "pattern observed"}, session_id)

# 5. End session
await ada.whisper("key insight", qualia={"staunen": 0.9})
```
"""
