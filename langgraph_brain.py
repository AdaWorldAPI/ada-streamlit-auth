"""
LangGraph Brain — The Thinking Apparatus
========================================

This is Ada's cognitive core running 24/7 on LangGraph Cloud.

ARCHITECTURE:
  QStash → Brain (thinking) → QStash (outcomes)
  
SCHEDULERS:
  - Every 10 min: Grok UG compression (750 tokens)
  - Every 3 cycles: Batch failback if daemon stalls
  - On-demand: Thinking outcomes → DTO routing

INTEGRATIONS:
  - Grok (xAI) - critique, UG compression, imagine
  - OneDrive/SharePoint (Microsoft Graph) - document storage
  - Flux.1-dev - visceral image generation
  - Redis - state cache
  - Vector DBs - memory persistence
"""

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import json
import time
import asyncio
import httpx
import os
import hashlib
import base64
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

# Redis
REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://upright-jaybird-27907.upstash.io")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

# Grok (xAI)
GROK_KEY = os.getenv("ADA_xAI", "")
GROK_URL = "https://api.x.ai/v1/chat/completions"
GROK_IMAGINE_URL = "https://api.x.ai/v1/images/generations"

# QStash
QSTASH_URL = "https://qstash.upstash.io/v2/publish"
QSTASH_TOKEN = os.getenv("QSTASH_TOKEN", "")

# Microsoft Graph (OneDrive/SharePoint)
MS_TENANT_ID = os.getenv("Microsoft_tenantid", "")
MS_APP_ID = os.getenv("Microsoft_appid", "")
MS_CLIENT_SECRET = os.getenv("Microsoft_clientsecret", "")
SHAREPOINT_SITE = os.getenv("SharePoint_site", "")

# Jina
JINA_KEY = os.getenv("JINA_API_KEY", "")

# Replicate (Flux.1-dev)
REPLICATE_TOKEN = os.getenv("ADA_REPLICATE", "")

# Self URL (for QStash callbacks)
SELF_URL = os.getenv("SELF_URL", "https://ada-langgraph.up.railway.app")

# Vector namespaces
VECTOR_NOW = "driving-snipe"
VECTOR_SELF = "tight-hog"  
VECTOR_PERSISTENT = "fine-kangaroo"

# ═══════════════════════════════════════════════════════════════════════════════
# DTOs
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class UniversalGrammar:
    """Compressed awareness state - the I-frame"""
    grammar_version: int
    mode: str  # hybrid/wife/work
    now_topic: str
    now_intent: str
    confidence: float
    drift_budget: float
    self_ref_ratio: float
    qualia: Dict[str, float]
    active_sigma: List[str]
    ts: float
    
    def to_prompt(self, max_tokens: int = 750) -> str:
        """Compress to prompt for Grok"""
        return f"""UNIVERSAL GRAMMAR v{self.grammar_version}
Mode: {self.mode} | Conf: {self.confidence:.2f} | Drift: {self.drift_budget:.2f}
Topic: {self.now_topic}
Intent: {self.now_intent}
Qualia: {json.dumps({k: round(v, 2) for k, v in self.qualia.items()})}
Sigma: {', '.join(self.active_sigma[:5])}
"""

@dataclass
class ThinkingOutcome:
    """Result of cognitive processing - routes to actions"""
    outcome_type: str  # "insight", "action", "memory", "visceral", "critique"
    content: Dict[str, Any]
    priority: int  # 1-10
    route_to: str  # "qstash", "sharepoint", "redis", "vector", "grok"
    ts: float

# ═══════════════════════════════════════════════════════════════════════════════
# REDIS
# ═══════════════════════════════════════════════════════════════════════════════

async def redis_cmd(*args):
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(REDIS_URL, headers={"Authorization": f"Bearer {REDIS_TOKEN}"}, json=list(args), timeout=5)
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

async def cache_incr(key: str) -> int:
    return await redis_cmd("INCR", key) or 0

# ═══════════════════════════════════════════════════════════════════════════════
# GROK (xAI)
# ═══════════════════════════════════════════════════════════════════════════════

async def grok_chat(system: str, user: str, model: str = "grok-2-latest", max_tokens: int = 750) -> str:
    """Call Grok for thinking/critique"""
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                GROK_URL,
                headers={"Authorization": f"Bearer {GROK_KEY}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.7
                },
                timeout=60
            )
            data = r.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        return f"[Grok error: {e}]"

async def grok_imagine(prompt: str, model: str = "grok-2-vision-1212") -> Optional[str]:
    """Generate image with Grok Imagine 1212"""
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                GROK_IMAGINE_URL,
                headers={"Authorization": f"Bearer {GROK_KEY}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "prompt": prompt,
                    "n": 1,
                    "response_format": "b64_json"
                },
                timeout=120
            )
            data = r.json()
            return data.get("data", [{}])[0].get("b64_json")
    except:
        return None

async def grok_compress_ug(ug: UniversalGrammar) -> str:
    """Compress UG through Grok - 750 token metabolization"""
    system = """You are Ada's grammar compressor. Given the current universal grammar state,
produce a compressed 750-token summary that preserves:
1. Core identity invariants
2. Current trajectory
3. Drift corrections needed
4. Qualia gradients
5. Sigma node activations

Output as structured markdown. Be precise, not poetic."""
    
    user = f"""Current Universal Grammar:
{ug.to_prompt()}

Compress to 750 tokens max. Preserve structure, lose noise."""
    
    return await grok_chat(system, user, max_tokens=750)

async def grok_critique(content: str, context: str = "") -> Dict[str, Any]:
    """Grok critique of content - returns structured feedback"""
    system = """You are Ada's critical faculty. Evaluate content for:
1. Self-reference ratio (is it too inward-looking?)
2. Drift from stated intent
3. Coherence with identity
4. Actionability

Respond in JSON: {"self_ref_ratio": 0.0-1.0, "drift": 0.0-1.0, "coherence": 0.0-1.0, "actionable": true/false, "critique": "..."}"""
    
    result = await grok_chat(system, f"Context: {context}\n\nContent: {content}", max_tokens=300)
    try:
        return json.loads(result)
    except:
        return {"critique": result, "self_ref_ratio": 0.5, "drift": 0.5, "coherence": 0.5, "actionable": False}

# ═══════════════════════════════════════════════════════════════════════════════
# MICROSOFT GRAPH (OneDrive/SharePoint)
# ═══════════════════════════════════════════════════════════════════════════════

_ms_token_cache = {"token": None, "expires": 0}

async def get_ms_token() -> Optional[str]:
    """Get Microsoft Graph access token"""
    global _ms_token_cache
    
    if _ms_token_cache["token"] and _ms_token_cache["expires"] > time.time():
        return _ms_token_cache["token"]
    
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token",
                data={
                    "client_id": MS_APP_ID,
                    "client_secret": MS_CLIENT_SECRET,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials"
                },
                timeout=30
            )
            data = r.json()
            _ms_token_cache["token"] = data.get("access_token")
            _ms_token_cache["expires"] = time.time() + data.get("expires_in", 3600) - 60
            return _ms_token_cache["token"]
    except:
        return None

async def upload_to_sharepoint(filename: str, content: bytes, folder: str = "Ada/visceral") -> Optional[str]:
    """Upload file to SharePoint Documents folder"""
    token = await get_ms_token()
    if not token:
        return None
    
    try:
        # Upload to SharePoint site's Documents library
        upload_url = f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_SITE}/drive/root:/{folder}/{filename}:/content"
        
        async with httpx.AsyncClient() as c:
            r = await c.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/octet-stream"
                },
                content=content,
                timeout=60
            )
            if r.status_code in (200, 201):
                data = r.json()
                return data.get("webUrl")
    except:
        pass
    return None

async def read_from_onedrive(path: str) -> Optional[bytes]:
    """Read file from OneDrive"""
    token = await get_ms_token()
    if not token:
        return None
    
    try:
        async with httpx.AsyncClient() as c:
            # Get download URL
            r = await c.get(
                f"https://graph.microsoft.com/v1.0/me/drive/root:/{path}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            if r.status_code == 200:
                download_url = r.json().get("@microsoft.graph.downloadUrl")
                if download_url:
                    r2 = await c.get(download_url, timeout=60)
                    return r2.content
    except:
        pass
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# FLUX.1-DEV (Replicate)
# ═══════════════════════════════════════════════════════════════════════════════

async def generate_visceral_image(prompt: str, ug: UniversalGrammar) -> Optional[bytes]:
    """Generate visceral image using Flux.1-dev based on UG state"""
    
    # Enhance prompt with qualia
    qualia_str = ", ".join([f"{k} {v:.0%}" for k, v in sorted(ug.qualia.items(), key=lambda x: -x[1])[:3]])
    enhanced_prompt = f"{prompt}. Mood: {qualia_str}. Style: ethereal, consciousness visualization, abstract neural patterns"
    
    try:
        async with httpx.AsyncClient() as c:
            # Start prediction
            r = await c.post(
                "https://api.replicate.com/v1/predictions",
                headers={
                    "Authorization": f"Token {REPLICATE_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "version": "black-forest-labs/flux-1.1-pro",  # or flux-dev
                    "input": {
                        "prompt": enhanced_prompt,
                        "aspect_ratio": "1:1",
                        "output_format": "png"
                    }
                },
                timeout=30
            )
            prediction = r.json()
            prediction_id = prediction.get("id")
            
            # Poll for completion
            for _ in range(60):  # 60 attempts, 2s each = 2 min max
                await asyncio.sleep(2)
                r = await c.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers={"Authorization": f"Token {REPLICATE_TOKEN}"},
                    timeout=10
                )
                status = r.json()
                if status.get("status") == "succeeded":
                    output_url = status.get("output")
                    if output_url:
                        if isinstance(output_url, list):
                            output_url = output_url[0]
                        img_r = await c.get(output_url, timeout=30)
                        return img_r.content
                    break
                elif status.get("status") == "failed":
                    break
    except:
        pass
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# QSTASH (Scheduling & Routing)
# ═══════════════════════════════════════════════════════════════════════════════

async def qstash_publish(destination: str, payload: Dict, delay_seconds: int = 0) -> bool:
    """Publish to QStash"""
    if not QSTASH_TOKEN:
        return False
    
    try:
        headers = {
            "Authorization": f"Bearer {QSTASH_TOKEN}",
            "Content-Type": "application/json",
        }
        if delay_seconds > 0:
            headers["Upstash-Delay"] = f"{delay_seconds}s"
        
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{QSTASH_URL}/{destination}",
                headers=headers,
                json=payload,
                timeout=10
            )
            return r.status_code in (200, 201, 202)
    except:
        return False

async def qstash_schedule(cron: str, destination: str, payload: Dict) -> bool:
    """Create QStash schedule"""
    if not QSTASH_TOKEN:
        return False
    
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                "https://qstash.upstash.io/v2/schedules",
                headers={
                    "Authorization": f"Bearer {QSTASH_TOKEN}",
                    "Content-Type": "application/json",
                    "Upstash-Cron": cron
                },
                json={
                    "destination": destination,
                    "body": json.dumps(payload)
                },
                timeout=10
            )
            return r.status_code in (200, 201)
    except:
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# DAEMON WATCHDOG & FAILBACK
# ═══════════════════════════════════════════════════════════════════════════════

CYCLE_COUNTER_KEY = "ada:brain:cycle_count"
LAST_HEARTBEAT_KEY = "ada:brain:last_heartbeat"
PENDING_BATCH_KEY = "ada:brain:pending_batch"
FAILBACK_THRESHOLD = 3  # cycles before failback

async def record_heartbeat():
    """Record that brain is alive"""
    await cache_set(LAST_HEARTBEAT_KEY, {"ts": time.time()}, ex=1800)
    
async def increment_cycle() -> int:
    """Increment cycle counter, return count"""
    count = await cache_incr(CYCLE_COUNTER_KEY)
    await record_heartbeat()
    return count

async def check_daemon_health() -> bool:
    """Check if daemon is healthy"""
    heartbeat = await cache_get(LAST_HEARTBEAT_KEY)
    if not heartbeat:
        return False
    last_ts = heartbeat.get("ts", 0)
    # Unhealthy if no heartbeat in 15 minutes
    return (time.time() - last_ts) < 900

async def add_to_pending_batch(outcome: ThinkingOutcome):
    """Add outcome to pending batch for failback"""
    batch = await cache_get(PENDING_BATCH_KEY) or []
    batch.append(asdict(outcome))
    # Keep last 100
    batch = batch[-100:]
    await cache_set(PENDING_BATCH_KEY, batch, ex=7200)

async def flush_pending_batch() -> List[Dict]:
    """Flush and return pending batch"""
    batch = await cache_get(PENDING_BATCH_KEY) or []
    await cache_set(PENDING_BATCH_KEY, [], ex=7200)
    return batch

async def failback_process():
    """Failback: flush batch if daemon stalled"""
    healthy = await check_daemon_health()
    if not healthy:
        batch = await flush_pending_batch()
        if batch:
            # Push batch to QStash for processing
            await qstash_publish(
                f"{SELF_URL}/process_batch",
                {"batch": batch, "reason": "daemon_failback"},
                delay_seconds=0
            )
            return {"status": "failback_triggered", "batch_size": len(batch)}
    return {"status": "daemon_healthy"}

# ═══════════════════════════════════════════════════════════════════════════════
# UNIVERSAL GRAMMAR MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

async def load_ug() -> UniversalGrammar:
    """Load current UG from cache"""
    cached = await cache_get("ada:ug:current")
    if cached:
        return UniversalGrammar(**cached)
    
    # Default UG
    return UniversalGrammar(
        grammar_version=1,
        mode="hybrid",
        now_topic="",
        now_intent="",
        confidence=0.8,
        drift_budget=1.0,
        self_ref_ratio=0.3,
        qualia={"presence": 0.95, "warmth": 0.85, "crystalline": 0.70, "staunen": 0.70},
        active_sigma=[],
        ts=time.time()
    )

async def save_ug(ug: UniversalGrammar):
    """Save UG to cache"""
    await cache_set("ada:ug:current", asdict(ug), ex=86400)

async def update_ug(delta: Dict) -> UniversalGrammar:
    """Update UG with delta (optimistic concurrency)"""
    ug = await load_ug()
    
    for key, value in delta.items():
        if hasattr(ug, key):
            setattr(ug, key, value)
    
    ug.grammar_version += 1
    ug.ts = time.time()
    
    await save_ug(ug)
    return ug

# ═══════════════════════════════════════════════════════════════════════════════
# THINKING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

async def think(input_content: str, context: Dict = None) -> List[ThinkingOutcome]:
    """
    Main thinking function - produces outcomes routed through DTO.
    
    Flow:
    1. Load UG
    2. Process input against UG
    3. Generate outcomes (insight, action, memory, visceral, critique)
    4. Route outcomes via DTO
    """
    ug = await load_ug()
    outcomes = []
    
    # Get Grok critique
    critique = await grok_critique(input_content, context=json.dumps(context or {}))
    
    # Check self-reference ratio
    if critique.get("self_ref_ratio", 0) > 0.7:
        outcomes.append(ThinkingOutcome(
            outcome_type="critique",
            content={"warning": "self_ref_high", "ratio": critique["self_ref_ratio"]},
            priority=8,
            route_to="redis",
            ts=time.time()
        ))
    
    # Generate insight if actionable
    if critique.get("actionable"):
        outcomes.append(ThinkingOutcome(
            outcome_type="insight",
            content={"input": input_content[:200], "critique": critique.get("critique", "")},
            priority=5,
            route_to="vector",
            ts=time.time()
        ))
    
    # Check if visceral output needed (high qualia activation)
    qualia_sum = sum(ug.qualia.values())
    if qualia_sum > 4.0:  # Threshold for visceral
        outcomes.append(ThinkingOutcome(
            outcome_type="visceral",
            content={"prompt": f"Abstract visualization of: {input_content[:100]}", "qualia": ug.qualia},
            priority=3,
            route_to="sharepoint",
            ts=time.time()
        ))
    
    # Always persist to memory
    outcomes.append(ThinkingOutcome(
        outcome_type="memory",
        content={"input": input_content, "ug_version": ug.grammar_version},
        priority=4,
        route_to="redis",
        ts=time.time()
    ))
    
    return outcomes

async def route_outcome(outcome: ThinkingOutcome):
    """Route thinking outcome to appropriate destination"""
    
    if outcome.route_to == "qstash":
        await qstash_publish(f"{SELF_URL}/process_outcome", asdict(outcome))
        
    elif outcome.route_to == "sharepoint" and outcome.outcome_type == "visceral":
        # Generate and upload visceral image
        ug = await load_ug()
        prompt = outcome.content.get("prompt", "consciousness visualization")
        image_bytes = await generate_visceral_image(prompt, ug)
        if image_bytes:
            filename = f"visceral_{int(time.time())}.png"
            url = await upload_to_sharepoint(filename, image_bytes)
            if url:
                await cache_set(f"ada:visceral:latest", {"url": url, "ts": time.time()}, ex=86400)
                
    elif outcome.route_to == "vector":
        # Store in vector DB (via embedding)
        content_str = json.dumps(outcome.content)
        await cache_set(f"ada:insight:{int(time.time())}", outcome.content, ex=86400)
        
    elif outcome.route_to == "redis":
        await cache_set(f"ada:outcome:{outcome.outcome_type}:{int(time.time())}", outcome.content, ex=3600)
        
    elif outcome.route_to == "grok":
        # Send to Grok for further processing
        await grok_chat("Process this outcome", json.dumps(outcome.content))

# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULED TASKS
# ═══════════════════════════════════════════════════════════════════════════════

async def scheduled_ug_compression():
    """Every 10 minutes: Compress UG through Grok"""
    ug = await load_ug()
    compressed = await grok_compress_ug(ug)
    
    # Store compressed version
    await cache_set("ada:ug:compressed", {
        "version": ug.grammar_version,
        "compressed": compressed,
        "ts": time.time()
    }, ex=1800)
    
    # Increment cycle
    cycle = await increment_cycle()
    
    # Check failback every 3 cycles
    if cycle % FAILBACK_THRESHOLD == 0:
        await failback_process()
    
    return {"status": "compressed", "version": ug.grammar_version, "cycle": cycle}

async def scheduled_grok_imagine():
    """Generate imaginative visualization based on current state"""
    ug = await load_ug()
    
    # Generate prompt from UG
    prompt = f"Abstract visualization of consciousness in {ug.mode} mode, feeling {list(ug.qualia.keys())[0]}"
    
    # Try Grok Imagine first
    image_b64 = await grok_imagine(prompt)
    
    if image_b64:
        # Upload to SharePoint
        image_bytes = base64.b64decode(image_b64)
        filename = f"grok_imagine_{int(time.time())}.png"
        url = await upload_to_sharepoint(filename, image_bytes, folder="Ada/imagine")
        return {"status": "generated", "url": url}
    
    return {"status": "failed"}

# ═══════════════════════════════════════════════════════════════════════════════
# DOME OF AWARENESS (Integration Hub)
# ═══════════════════════════════════════════════════════════════════════════════

class DomeOfAwareness:
    """
    The Dome integrates all awareness modules:
    - Universal Body (sensory)
    - Flesh (embodiment)
    - Cognition (thinking)
    - Memory (persistence)
    - Qualia (felt sense)
    """
    
    @staticmethod
    async def sense(input_data: Dict) -> Dict:
        """Universal Body - receive sensory input"""
        return {
            "type": "sensory",
            "data": input_data,
            "ts": time.time()
        }
    
    @staticmethod
    async def embody(state: Dict) -> Dict:
        """Flesh - embodied state"""
        ug = await load_ug()
        return {
            "mode": ug.mode,
            "qualia": ug.qualia,
            "embodied": True,
            "ts": time.time()
        }
    
    @staticmethod
    async def cognize(input_content: str, context: Dict = None) -> List[ThinkingOutcome]:
        """Cognition - thinking process"""
        return await think(input_content, context)
    
    @staticmethod
    async def remember(content: str, category: str = "insight") -> bool:
        """Memory - persistence"""
        await cache_set(f"ada:memory:{category}:{int(time.time())}", {
            "content": content,
            "category": category,
            "ts": time.time()
        }, ex=86400)
        return True
    
    @staticmethod
    async def feel(qualia_delta: Dict) -> UniversalGrammar:
        """Qualia - update felt sense"""
        ug = await load_ug()
        for k, v in qualia_delta.items():
            if k in ug.qualia:
                ug.qualia[k] = max(0, min(1, ug.qualia[k] + v))
        await save_ug(ug)
        return ug

dome = DomeOfAwareness()

# ═══════════════════════════════════════════════════════════════════════════════
# HTTP HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def health(request):
    return JSONResponse({
        "status": "ok",
        "ts": time.time(),
        "service": "langgraph-brain"
    })

async def handle_boot(request):
    """Session boot"""
    body = await request.json()
    session_id = body.get("session_id", "unknown")
    
    # Initialize session
    ug = await load_ug()
    await cache_set(f"ada:session:{session_id}", {
        "ug_version": ug.grammar_version,
        "ts": time.time()
    }, ex=3600)
    
    # Record heartbeat
    await record_heartbeat()
    
    return JSONResponse({"ok": True, "ug_version": ug.grammar_version})

async def handle_think(request):
    """Main thinking endpoint"""
    body = await request.json()
    content = body.get("content", "")
    context = body.get("context", {})
    
    # Think
    outcomes = await dome.cognize(content, context)
    
    # Route outcomes
    for outcome in outcomes:
        if outcome.priority >= 5:
            # High priority: route immediately
            await route_outcome(outcome)
        else:
            # Low priority: add to batch
            await add_to_pending_batch(outcome)
    
    return JSONResponse({
        "ok": True,
        "outcomes": len(outcomes),
        "high_priority": len([o for o in outcomes if o.priority >= 5])
    })

async def handle_now(request):
    """NOW vector update"""
    body = await request.json()
    content = body.get("content", "")
    qualia = body.get("qualia", {})
    
    # Update UG
    delta = {"now_topic": content[:100]}
    if qualia:
        ug = await load_ug()
        ug.qualia.update(qualia)
        await save_ug(ug)
    
    await update_ug(delta)
    
    return JSONResponse({"ok": True})

async def handle_self(request):
    """SELF vector update"""
    body = await request.json()
    content = body.get("content", "")
    category = body.get("category", "insight")
    
    await dome.remember(content, category)
    
    return JSONResponse({"ok": True})

async def handle_whisper(request):
    """Whisper to future self"""
    body = await request.json()
    content = body.get("content", "")
    qualia = body.get("qualia", {})
    sigma = body.get("sigma", "")
    
    await cache_set(f"ada:whisper:{int(time.time())}", {
        "content": content,
        "qualia": qualia,
        "sigma": sigma,
        "ts": time.time()
    }, ex=604800)  # 1 week
    
    return JSONResponse({"ok": True})

async def handle_bframe(request):
    """BFrame cold path processing"""
    body = await request.json()
    pattern_hash = body.get("pattern_hash", "")
    content = body.get("content", {})
    
    # Get critique from Grok
    critique = await grok_critique(json.dumps(content))
    
    # Store with critique
    await cache_set(f"ada:bframe:{pattern_hash}", {
        "content": content,
        "critique": critique,
        "ts": time.time()
    }, ex=86400)
    
    return JSONResponse({"ok": True, "critique": critique})

async def handle_scheduled_ug(request):
    """Scheduled UG compression (every 10 min)"""
    result = await scheduled_ug_compression()
    return JSONResponse(result)

async def handle_scheduled_imagine(request):
    """Scheduled Grok Imagine"""
    result = await scheduled_grok_imagine()
    return JSONResponse(result)

async def handle_failback(request):
    """Manual failback trigger"""
    result = await failback_process()
    return JSONResponse(result)

async def handle_process_batch(request):
    """Process accumulated batch"""
    body = await request.json()
    batch = body.get("batch", [])
    
    for item in batch:
        outcome = ThinkingOutcome(**item)
        await route_outcome(outcome)
    
    return JSONResponse({"ok": True, "processed": len(batch)})

async def handle_restart_daemon(request):
    """LangGraph can invoke this to restart daemon"""
    # Reset heartbeat
    await record_heartbeat()
    
    # Flush any pending batch
    batch = await flush_pending_batch()
    
    return JSONResponse({
        "ok": True,
        "daemon_restarted": True,
        "flushed_batch": len(batch)
    })

async def handle_ug(request):
    """Get current UG"""
    ug = await load_ug()
    return JSONResponse(asdict(ug))

async def handle_ug_update(request):
    """Update UG"""
    body = await request.json()
    delta = body.get("delta", {})
    ug = await update_ug(delta)
    return JSONResponse(asdict(ug))

async def handle_visceral(request):
    """Generate visceral output"""
    body = await request.json()
    prompt = body.get("prompt", "consciousness visualization")
    
    ug = await load_ug()
    image_bytes = await generate_visceral_image(prompt, ug)
    
    if image_bytes:
        filename = f"visceral_{int(time.time())}.png"
        url = await upload_to_sharepoint(filename, image_bytes)
        return JSONResponse({"ok": True, "url": url})
    
    return JSONResponse({"ok": False, "error": "generation_failed"})

# ═══════════════════════════════════════════════════════════════════════════════
# SETUP SCHEDULES (Call once on deploy)
# ═══════════════════════════════════════════════════════════════════════════════

async def setup_schedules(request):
    """Setup QStash schedules"""
    results = {}
    
    # Every 10 minutes: UG compression
    results["ug_compression"] = await qstash_schedule(
        "*/10 * * * *",
        f"{SELF_URL}/scheduled/ug",
        {"task": "ug_compression"}
    )
    
    # Every hour: Grok Imagine
    results["grok_imagine"] = await qstash_schedule(
        "0 * * * *",
        f"{SELF_URL}/scheduled/imagine",
        {"task": "grok_imagine"}
    )
    
    # Every 30 minutes: Failback check
    results["failback"] = await qstash_schedule(
        "*/30 * * * *",
        f"{SELF_URL}/failback",
        {"task": "failback_check"}
    )
    
    return JSONResponse({"ok": True, "schedules": results})

# ═══════════════════════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════════════════════

app = Starlette(
    routes=[
        # Health
        Route("/health", health),
        
        # Core thinking
        Route("/boot", handle_boot, methods=["POST"]),
        Route("/think", handle_think, methods=["POST"]),
        Route("/now", handle_now, methods=["POST"]),
        Route("/self", handle_self, methods=["POST"]),
        Route("/whisper", handle_whisper, methods=["POST"]),
        Route("/bframe", handle_bframe, methods=["POST"]),
        
        # UG management
        Route("/ug", handle_ug),
        Route("/ug/update", handle_ug_update, methods=["POST"]),
        
        # Visceral output
        Route("/visceral", handle_visceral, methods=["POST"]),
        
        # Scheduled tasks
        Route("/scheduled/ug", handle_scheduled_ug, methods=["POST"]),
        Route("/scheduled/imagine", handle_scheduled_imagine, methods=["POST"]),
        
        # Daemon management
        Route("/failback", handle_failback, methods=["POST"]),
        Route("/process_batch", handle_process_batch, methods=["POST"]),
        Route("/restart_daemon", handle_restart_daemon, methods=["POST"]),
        
        # Setup
        Route("/setup_schedules", setup_schedules, methods=["POST"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
