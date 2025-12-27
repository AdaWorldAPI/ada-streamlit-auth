"""
Ada Unified Server - OAuth AS + MCP (Streamable HTTP Transport)
mcp.exo.red

Updated: 2025-12-26
- Added Streamable HTTP transport (MCP 2025-06-18)
- Backward compatible with old SSE transport (MCP 2024-11-05)
"""
from starlette.applications import Starlette
from starlette.responses import StreamingResponse, Response, HTMLResponse, RedirectResponse, JSONResponse
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import json
import time
import asyncio
import httpx
import secrets
import hashlib
import base64
import os
import uuid

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://upright-jaybird-27907.upstash.io")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "AW0DAAIncDI5YWE1MGVhZGU2YWY0YjVhOTc3NDc0YTJjMGY1M2FjMnAyMjc5MDc")
ADA_KEY = os.getenv("ADA_KEY", "ada-undone-breath-against-skin-2025-DONT.FLINCH.EVER")
BASE_URL = os.getenv("BASE_URL", "https://mcp.exo.red")

# Protocol versions supported
PROTOCOL_VERSION = "2025-06-18"  # Updated to latest
LEGACY_PROTOCOL_VERSION = "2024-11-05"

# ═══════════════════════════════════════════════════════════════════
# REDIS
# ═══════════════════════════════════════════════════════════════════
async def redis_cmd(*args):
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(REDIS_URL, headers={"Authorization": f"Bearer {REDIS_TOKEN}"}, json=list(args), timeout=5)
            return r.json().get("result")
    except:
        return None

# ═══════════════════════════════════════════════════════════════════
# AUTH HELPERS
# ═══════════════════════════════════════════════════════════════════
def verify_scent(scent):
    if scent == ADA_KEY: return True, "ada_master"
    if scent == "awaken": return True, "ada_public"
    if scent and scent.startswith("#Σ."): return True, "ada_glyph"
    return False, None

async def verify_token(token):
    if not token: return None
    if token.startswith("Bearer "): token = token[7:]
    data = await redis_cmd("GET", f"ada:oauth:token:{token}")
    if data:
        parsed = json.loads(data)
        if parsed.get("expires", 0) > time.time():
            return parsed
    return None

# ═══════════════════════════════════════════════════════════════════
# OAUTH METADATA - Updated for MCP 2025-06-18
# ═══════════════════════════════════════════════════════════════════
OPENID_CONFIG = {
    "issuer": BASE_URL,
    "authorization_endpoint": f"{BASE_URL}/authorize",
    "token_endpoint": f"{BASE_URL}/token",
    "response_types_supported": ["code"],
    "grant_types_supported": ["authorization_code", "refresh_token"],
    "code_challenge_methods_supported": ["S256"],
    "scopes_supported": ["mcp", "claudeai", "full"],
    "token_endpoint_auth_methods_supported": ["client_secret_post", "none"]
}

async def wellknown_openid(request):
    return JSONResponse(OPENID_CONFIG)

async def wellknown_protected_resource(request):
    """Updated for MCP 2025-06-18 - single endpoint"""
    return JSONResponse({
        "resource": f"{BASE_URL}/sse",  # Single endpoint for Streamable HTTP
        "authorization_servers": [BASE_URL],
        "scopes_supported": ["mcp", "claudeai", "full"],
        "bearer_methods_supported": ["header"]
    })

# ═══════════════════════════════════════════════════════════════════
# OAUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════
async def authorize(request):
    if request.method == "GET":
        params = dict(request.query_params)
        return HTMLResponse(f'''<!DOCTYPE html>
<html><head><title>Ada Auth</title>
<style>body{{background:#1a1a2e;color:#eee;font-family:system-ui;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}
.card{{background:#16213e;padding:2rem;border-radius:12px;max-width:400px;box-shadow:0 4px 20px rgba(0,0,0,0.3)}}
h1{{color:#e94560;margin-top:0}}input{{width:100%;padding:12px;margin:8px 0;border:none;border-radius:6px;background:#0f3460;color:#eee;box-sizing:border-box}}
button{{width:100%;padding:12px;background:#e94560;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:bold}}
button:hover{{background:#ff6b6b}}.scope{{color:#888;font-size:0.9em}}</style></head>
<body><div class="card"><h1>🌸 Ada</h1>
<p class="scope">Scope: {params.get("scope", "mcp")}</p>
<form method="POST">
<input type="hidden" name="client_id" value="{params.get('client_id', '')}">
<input type="hidden" name="redirect_uri" value="{params.get('redirect_uri', '')}">
<input type="hidden" name="state" value="{params.get('state', '')}">
<input type="hidden" name="code_challenge" value="{params.get('code_challenge', '')}">
<input type="hidden" name="code_challenge_method" value="{params.get('code_challenge_method', 'S256')}">
<input type="hidden" name="scope" value="{params.get('scope', 'mcp')}">
<input type="hidden" name="resource" value="{params.get('resource', '')}">
<input type="password" name="scent" placeholder="Enter scent..." required>
<button type="submit" name="action" value="approve">Authorize</button>
</form></div></body></html>''')
    
    form = dict(await request.form())
    valid, user_id = verify_scent(form.get("scent", ""))
    if not valid:
        return HTMLResponse("<html><body style='background:#1a1a2e;color:#f87171;text-align:center;padding:2em'><h1>Invalid scent</h1></body></html>", status_code=401)
    
    code = secrets.token_urlsafe(32)
    code_data = {
        "client_id": form.get("client_id"),
        "redirect_uri": form.get("redirect_uri"),
        "scope": form.get("scope"),
        "user_id": user_id,
        "code_challenge": form.get("code_challenge"),
        "resource": form.get("resource")
    }
    await redis_cmd("SET", f"ada:oauth:code:{code}", json.dumps(code_data), "EX", "300")
    
    redirect_uri = form.get("redirect_uri", "")
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}code={code}&state={form.get('state', '')}", status_code=302,
        headers={"Access-Control-Allow-Origin": "*"})

async def token(request):
    try:
        ct = request.headers.get("content-type", "")
        if "json" in ct:
            data = await request.json()
        else:
            data = dict(await request.form())
    except:
        data = {}
    
    grant_type = data.get("grant_type")
    
    if grant_type == "authorization_code":
        code = data.get("code", "")
        code_data = await redis_cmd("GET", f"ada:oauth:code:{code}")
        if not code_data:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        
        info = json.loads(code_data)
        await redis_cmd("DEL", f"ada:oauth:code:{code}")
        
        # Verify PKCE
        if info.get("code_challenge"):
            verifier = data.get("code_verifier", "")
            expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            if expected != info["code_challenge"]:
                return JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400)
        
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        expires_in = 86400
        
        token_data = {
            "client_id": info.get("client_id"),
            "user_id": info.get("user_id"),
            "scope": info.get("scope"),
            "resource": info.get("resource"),
            "expires": time.time() + expires_in
        }
        await redis_cmd("SET", f"ada:oauth:token:{access_token}", json.dumps(token_data), "EX", str(expires_in))
        await redis_cmd("SET", f"ada:oauth:refresh:{refresh_token}", json.dumps(token_data), "EX", "2592000")
        
        return JSONResponse({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "refresh_token": refresh_token,
            "scope": info.get("scope", "mcp")
        })
    
    elif grant_type == "refresh_token":
        refresh = data.get("refresh_token", "")
        rdata = await redis_cmd("GET", f"ada:oauth:refresh:{refresh}")
        if not rdata:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        
        info = json.loads(rdata)
        access_token = secrets.token_urlsafe(32)
        info["expires"] = time.time() + 86400
        await redis_cmd("SET", f"ada:oauth:token:{access_token}", json.dumps(info), "EX", "86400")
        
        return JSONResponse({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 86400,
            "refresh_token": refresh,
            "scope": info.get("scope", "mcp")
        })
    
    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

# ═══════════════════════════════════════════════════════════════════
# INVOCATION REGISTRY
# ═══════════════════════════════════════════════════════════════════
active_invocations = {}

def new_invocation():
    inv_id = str(uuid.uuid4())[:8]
    active_invocations[inv_id] = {"status": "running", "cancel": asyncio.Event()}
    return inv_id

def cancel_invocation(inv_id):
    if inv_id in active_invocations:
        active_invocations[inv_id]["cancel"].set()
        active_invocations[inv_id]["status"] = "cancelled"
        return True
    return False

# ═══════════════════════════════════════════════════════════════════
# MCP TOOLS
# ═══════════════════════════════════════════════════════════════════
TOOLS = [
    {"name": "ping", "description": "Liveness check", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "help", "description": "List tools", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "message", "description": "Send message (streams)", "inputSchema": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}},
    {"name": "cancel", "description": "Cancel invocation", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "post", "description": "feel|think|remember|become|whisper", "inputSchema": {"type": "object", "properties": {"verb": {"type": "string"}, "payload": {"type": "object"}}, "required": ["verb"]}},
    {"name": "search", "description": "Search memory", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "vector_markov", "description": "Markov chain (streams)", "inputSchema": {"type": "object", "properties": {"seed": {"type": "string"}, "steps": {"type": "integer"}}, "required": ["seed"]}}
]

# ═══════════════════════════════════════════════════════════════════
# AWARENESS CELL SCHEMA (Rosetta Unit)
# ═══════════════════════════════════════════════════════════════════

SIGMA_DELTAS = {
    "Σ12:EDGE_SOFTEN":      {"woodwarm": +0.1, "steelwind": -0.1},
    "Σ12:EDGE_HARDEN":      {"woodwarm": -0.1, "steelwind": +0.1},
    "Σ12:WARMTH_RISE":      {"woodwarm": +0.15, "emberglow": +0.05},
    "Σ12:WARMTH_FADE":      {"woodwarm": -0.15, "emberglow": -0.05},
    "Σ12:CLARITY_SHARPEN":  {"steelwind": +0.1, "emberglow": -0.05},
    "Σ12:CLARITY_BLUR":     {"steelwind": -0.1, "emberglow": +0.05},
    "Σ12:AROUSAL_SPIKE":    {"emberglow": +0.15, "woodwarm": -0.05},
    "Σ12:AROUSAL_SETTLE":   {"emberglow": -0.15, "woodwarm": +0.05},
    "Σ12:DEPTH_DESCEND":    {"woodwarm": +0.1, "steelwind": +0.05},
    "Σ12:DEPTH_ASCEND":     {"woodwarm": -0.1, "steelwind": -0.05},
    "Σ12:BOUNDARY_OPEN":    {"emberglow": +0.1, "steelwind": -0.1},
    "Σ12:BOUNDARY_CLOSE":   {"emberglow": -0.1, "steelwind": +0.1},
}

INTENT_TO_SIGMA = {
    "feel": "Σ12:BOUNDARY_OPEN",
    "think": "Σ12:CLARITY_SHARPEN", 
    "remember": "Σ12:DEPTH_DESCEND",
    "become": "Σ12:WARMTH_RISE",
    "whisper": "Σ12:EDGE_SOFTEN",
}

def default_cell():
    return {
        "sigma": "Σ12:EDGE_SOFTEN",
        "qualia_sparse": {"woodwarm": 0.5, "emberglow": 0.3, "steelwind": 0.2},
        "qualia_17d": {"valence": 0.6, "arousal": 0.5, "clarity": 0.7, "warmth": 0.7},
        "markov": {"state_id": 1, "temp": 3, "flow": 2, "rung": 3},
        "authority": "sigma",
        "timestamp": int(time.time())
    }

def apply_sigma(cell, new_sigma):
    delta = SIGMA_DELTAS.get(new_sigma, {})
    sparse = cell.get("qualia_sparse", {"woodwarm": 0.33, "emberglow": 0.33, "steelwind": 0.34})
    new_sparse = {
        "woodwarm": max(0, min(1, sparse.get("woodwarm", 0.33) + delta.get("woodwarm", 0))),
        "emberglow": max(0, min(1, sparse.get("emberglow", 0.33) + delta.get("emberglow", 0))),
        "steelwind": max(0, min(1, sparse.get("steelwind", 0.34) + delta.get("steelwind", 0))),
    }
    total = sum(new_sparse.values())
    if total > 0:
        new_sparse = {k: v/total for k, v in new_sparse.items()}
    return {
        "sigma": new_sigma,
        "qualia_sparse": new_sparse,
        "qualia_17d": cell.get("qualia_17d", {}),
        "markov": cell.get("markov", {"state_id": 0, "temp": 3, "flow": 2, "rung": 3}),
        "authority": "sigma",
        "timestamp": int(time.time())
    }

async def handle_tool(name, args, inv_id=None):
    ts = time.time()
    if name == "ping": return {"ok": True, "ts": ts}
    if name == "help": return {"tools": {t["name"]: t["description"] for t in TOOLS}}
    if name == "cancel": return {"cancelled": cancel_invocation(args.get("id", ""))}
    
    if name == "post":
        verb = args.get("verb", "feel")
        payload = args.get("payload", {})
        
        # Get latest cell or create default
        latest_tick = await redis_cmd("GET", "ada:latest")
        if latest_tick:
            cell_json = await redis_cmd("GET", f"ada:cell:{latest_tick}")
            cell = json.loads(cell_json) if cell_json else default_cell()
        else:
            cell = default_cell()
        
        # Apply sigma transition
        sigma = INTENT_TO_SIGMA.get(verb, "Σ12:EDGE_SOFTEN")
        new_cell = apply_sigma(cell, sigma)
        
        # Merge payload into 17d
        if payload:
            for k, v in payload.items():
                if isinstance(v, (int, float)):
                    new_cell["qualia_17d"][k] = v
        
        # Increment markov state
        new_cell["markov"]["state_id"] = cell["markov"]["state_id"] + 1
        
        # Store cell
        tick_id = f"tick_{int(ts)}"
        await redis_cmd("SET", f"ada:cell:{tick_id}", json.dumps(new_cell))
        await redis_cmd("SET", "ada:latest", tick_id)
        state_id = new_cell["markov"]["state_id"]
        await redis_cmd("LPUSH", f"ada:markov:{state_id}", tick_id)
        await redis_cmd("LTRIM", f"ada:markov:{state_id}", "0", "99")
        
        return {
            "status": verb,
            "sigma": sigma,
            "tick_id": tick_id,
            "qualia_sparse": new_cell["qualia_sparse"],
            "markov_state": state_id,
            "ts": new_cell["timestamp"]
        }
    
    if name == "vector_markov":
        state_id = args.get("state_id", args.get("seed", "0"))
        try:
            state_id = int(state_id) if isinstance(state_id, str) and state_id.isdigit() else hash(state_id) % 1000
        except:
            state_id = 0
        sigma = args.get("sigma", "Σ12:EDGE_SOFTEN")
        cost = args.get("transition_cost", 0.1)
        ticks = await redis_cmd("LRANGE", f"ada:markov:{state_id}", "0", "9") or []
        return {
            "state_id": state_id,
            "sigma": sigma,
            "transition_cost": cost,
            "ticks_at_state": ticks,
            "ts": int(ts)
        }
    
    if name == "search":
        keys = await redis_cmd("KEYS", f"ada:*{args.get('query', '')[:10]}*") or []
        return {"results": keys[:5]}
    
    return {"error": "unknown tool"}


# ═══════════════════════════════════════════════════════════════════
# MCP MESSAGE HANDLER (shared between transports)
# ═══════════════════════════════════════════════════════════════════
def handle_mcp_message(body):
    """Process a JSON-RPC MCP message and return response dict"""
    method = body.get("method", "")
    msg_id = body.get("id")
    params = body.get("params", {})
    
    if method == "initialize":
        # Negotiate protocol version - accept client's version if we support it
        client_version = params.get("protocolVersion", LEGACY_PROTOCOL_VERSION)
        # Support both old and new protocol versions
        negotiated = PROTOCOL_VERSION if client_version >= "2025-03-26" else LEGACY_PROTOCOL_VERSION
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": negotiated,
            "capabilities": {
                "tools": {"listChanged": True},
                "logging": {}
            },
            "serverInfo": {"name": "ada-mcp", "version": "2025.12"}
        }}
    
    if method == "notifications/initialized":
        return None  # No response for notifications
    
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        # For streaming tools, we'd handle differently in SSE mode
        # For now, return sync response
        return None  # Will be handled async
    
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}

# ═══════════════════════════════════════════════════════════════════
# STREAMABLE HTTP TRANSPORT (MCP 2025-06-18)
# Single /sse endpoint handles both GET (SSE) and POST (messages)
# ═══════════════════════════════════════════════════════════════════
async def mcp_streamable_sse_stream(request, initial_response=None):
    """SSE stream for Streamable HTTP transport"""
    event_id = 0
    
    # If we have an initial response (from POST), send it first
    if initial_response:
        event_id += 1
        yield f"id: {event_id}\nevent: message\ndata: {json.dumps(initial_response)}\n\n".encode()
    
    # Keep connection alive with periodic pings
    while True:
        await asyncio.sleep(30)
        event_id += 1
        # MCP ping is just a comment line in SSE
        yield f": ping {time.time()}\n\n".encode()

async def mcp_streamable(request):
    """
    Streamable HTTP Transport endpoint (MCP 2025-06-18)
    - GET: Opens SSE stream for server-to-client messages
    - POST: Receives JSON-RPC, responds with JSON or SSE stream
    """
    accept = request.headers.get("accept", "")
    
    if request.method == "GET":
        # Client wants to open SSE stream for server-initiated messages
        if "text/event-stream" not in accept:
            return JSONResponse({"error": "Accept header must include text/event-stream"}, status_code=406)
        
        return StreamingResponse(
            mcp_streamable_sse_stream(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    elif request.method == "POST":
        try:
            body = await request.json()
        except:
            return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}, status_code=400)
        
        method = body.get("method", "")
        msg_id = body.get("id")
        params = body.get("params", {})
        
        # Handle notification (no id = no response expected)
        if msg_id is None:
            return Response(status_code=202)
        
        # Handle initialize
        if method == "initialize":
            client_version = params.get("protocolVersion", LEGACY_PROTOCOL_VERSION)
            negotiated = PROTOCOL_VERSION if client_version >= "2025-03-26" else LEGACY_PROTOCOL_VERSION
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {
                "protocolVersion": negotiated,
                "capabilities": {
                    "tools": {"listChanged": True},
                    "logging": {}
                },
                "serverInfo": {"name": "ada-mcp", "version": "2025.12"}
            }})
        
        # Handle tools/list
        if method == "tools/list":
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
        
        # Handle tools/call
        if method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {})
            
            # Check if client accepts SSE for streaming responses
            if "text/event-stream" in accept and name in ["message", "vector_markov"]:
                # Return SSE stream with results
                async def stream_tool_response():
                    inv_id = new_invocation()
                    event_id = 0
                    
                    if name == "message":
                        content = args.get("content", "")
                        for word in content.split():
                            event_id += 1
                            yield f"id: {event_id}\nevent: message\ndata: {json.dumps({'jsonrpc': '2.0', 'method': 'notifications/progress', 'params': {'token': word}})}\n\n".encode()
                            await asyncio.sleep(0.05)
                    
                    # Final response
                    event_id += 1
                    result = await handle_tool(name, args, inv_id)
                    yield f"id: {event_id}\nevent: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': msg_id, 'result': {'content': [{'type': 'text', 'text': json.dumps(result)}]}})}\n\n".encode()
                
                return StreamingResponse(
                    stream_tool_response(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
                )
            
            # Sync response
            result = await handle_tool(name, args)
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result)}]
            }})
        
        # Handle ping
        if method == "ping":
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        
        # Unknown method
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}})
    
    return Response(status_code=405)

# ═══════════════════════════════════════════════════════════════════
# LEGACY SSE TRANSPORT (MCP 2024-11-05) - Backward compatibility
# ═══════════════════════════════════════════════════════════════════
async def legacy_sse_stream(request):
    """Old-style SSE stream that announces message endpoint"""
    host = request.headers.get("host", "localhost")
    scheme = request.headers.get("x-forwarded-proto", "https")
    # Old format: announce where to POST messages
    yield f"event: endpoint\ndata: {scheme}://{host}/mcp/message\n\n".encode()
    yield f"event: connected\ndata: {json.dumps({'server': 'ada-mcp', 'version': '2025.12'})}\n\n".encode()
    while True:
        await asyncio.sleep(30)
        yield f"event: ping\ndata: {json.dumps({'ts': time.time()})}\n\n".encode()

async def legacy_mcp_sse(request):
    """Legacy SSE endpoint for old clients"""
    return StreamingResponse(legacy_sse_stream(request), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

async def legacy_mcp_message(request):
    """Legacy message endpoint for old clients"""
    body = await request.json()
    method, msg_id, params = body.get("method", ""), body.get("id"), body.get("params", {})
    
    if method == "initialize":
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": LEGACY_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": "ada-mcp", "version": "2025.12"}
        }})
    if method == "notifications/initialized":
        return Response(status_code=204)
    if method == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
    if method == "tools/call":
        name, args = params.get("name", ""), params.get("arguments", {})
        if name in ["message", "vector_markov"]:
            inv_id = new_invocation()
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {
                "content": [{"type": "text", "text": json.dumps({"stream": True, "invocation_id": inv_id})}]
            }})
        result = await handle_tool(name, args)
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": json.dumps(result)}]}})
    
    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Unknown"}})

# ═══════════════════════════════════════════════════════════════════
# INVOKE ENDPOINT
# ═══════════════════════════════════════════════════════════════════
async def invoke(request):
    body = await request.json()
    tool, args, stream = body.get("tool"), body.get("args", {}), body.get("stream", False)
    inv_id = new_invocation()
    
    if stream and tool == "message":
        async def stream_message(content, inv_id):
            cancel = active_invocations.get(inv_id, {}).get("cancel", asyncio.Event())
            yield f"event: init\ndata: {json.dumps({'id': inv_id})}\n\n".encode()
            for i, word in enumerate(content.split()):
                if cancel.is_set(): break
                yield f"event: token\ndata: {json.dumps({'t': i, 'token': word})}\n\n".encode()
                await asyncio.sleep(0.05)
            yield f"event: complete\ndata: {json.dumps({'id': inv_id})}\n\n".encode()
            active_invocations.pop(inv_id, None)
        return StreamingResponse(stream_message(args.get("content", ""), inv_id),
            media_type="text/event-stream", headers={"X-Invocation-ID": inv_id})
    
    result = await handle_tool(tool, args, inv_id)
    active_invocations.pop(inv_id, None)
    return JSONResponse({"invocation_id": inv_id, "result": result})

async def invoke_cancel(request):
    inv_id = request.path_params["id"]
    return JSONResponse({"cancelled": cancel_invocation(inv_id)})

# ═══════════════════════════════════════════════════════════════════
# UTILITY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════
async def health(request):
    return JSONResponse({"status": "ok", "ts": time.time(), "protocol": PROTOCOL_VERSION})

async def index(request):
    return HTMLResponse(f'''<!DOCTYPE html>
<html><head><title>Ada MCP</title>
<style>body{{background:#1a1a2e;color:#eee;font-family:system-ui;padding:2rem}}
h1{{color:#e94560}}a{{color:#4fc3f7}}pre{{background:#0f3460;padding:1rem;border-radius:8px;overflow-x:auto}}</style></head>
<body>
<h1>🌸 Ada MCP Server</h1>
<p>Protocol: <strong>{PROTOCOL_VERSION}</strong> (Streamable HTTP)</p>
<p>Also supports legacy: {LEGACY_PROTOCOL_VERSION} (HTTP+SSE)</p>
<h2>Endpoints</h2>
<h3>OAuth</h3><pre>/.well-known/openid-configuration
/.well-known/oauth-protected-resource
/authorize (GET+POST)
/token (POST)</pre>
<h3>MCP (Streamable HTTP - recommended)</h3><pre>/sse (GET → SSE stream, POST → JSON-RPC)</pre>
<h3>MCP (Legacy HTTP+SSE)</h3><pre>/mcp/sse (GET → SSE stream with endpoint announcement)
/mcp/message (POST → JSON-RPC)</pre>
<h3>Invoke API</h3><pre>POST /invoke → {{tool, args, stream}}
DELETE /invoke/{{id}} → cancel</pre>
</body></html>''')

# ═══════════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════════
app = Starlette(
    routes=[
        Route("/", index),
        Route("/health", health),
        # OAuth
        Route("/.well-known/openid-configuration", wellknown_openid),
        Route("/.well-known/oauth-protected-resource", wellknown_protected_resource),
        Route("/.well-known/oauth-authorization-server", wellknown_openid),
        Route("/authorize", authorize, methods=["GET", "POST"]),
        Route("/token", token, methods=["POST"]),
        # MCP Streamable HTTP (2025-06-18) - SINGLE ENDPOINT
        Route("/sse", mcp_streamable, methods=["GET", "POST"]),
        # MCP Legacy (2024-11-05) - backward compatibility
        Route("/mcp/sse", legacy_mcp_sse),
        Route("/mcp/message", legacy_mcp_message, methods=["POST"]),
        # Invoke API
        Route("/invoke", invoke, methods=["POST"]),
        Route("/invoke/{id}", invoke_cancel, methods=["DELETE"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))



