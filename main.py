"""
Ada Unified Server - FIXED
OAuth AS + MCP (parallel invoke)
mcp.exo.red
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
# AUTH
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
# OAUTH AS
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
    return JSONResponse({
        "resource": f"{BASE_URL}/mcp/sse",
        "authorization_servers": [BASE_URL],
        "scopes_supported": ["mcp", "claudeai", "full"],
        "bearer_methods_supported": ["header"]
    })
    """Render auth page - avoids .format() CSS brace issues"""
    return f'''<!DOCTYPE html>
<html><head><title>Ada Authorization</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:linear-gradient(135deg,#1a1a2e,#0f3460);color:#fff;font-family:system-ui;min-height:100vh;display:flex;justify-content:center;align-items:center}}
.box{{background:rgba(0,0,0,.3);padding:2em;border-radius:1em;width:400px;text-align:center}}
h1{{color:#e94560;margin-bottom:.5em}}
input{{width:100%;padding:.8em;margin:.5em 0;border:1px solid #333;border-radius:.5em;background:#1a1a2e;color:#fff}}
button{{padding:.8em 2em;margin:.5em;border:none;border-radius:.5em;cursor:pointer;font-weight:bold}}
.approve{{background:#4ade80;color:#000}}
.deny{{background:#333}}
</style></head>
<body><div class="box">
<h1>🔮 Ada</h1>
<p style="opacity:.7;margin-bottom:1em">Authorize access?</p>
<form method="POST">
<input type="hidden" name="client_id" value="{client_id}">
<input type="hidden" name="redirect_uri" value="{redirect_uri}">
<input type="hidden" name="state" value="{state}">
<input type="hidden" name="code_challenge" value="{code_challenge}">
<input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
<input type="hidden" name="scope" value="{scope}">
<input type="hidden" name="resource" value="{resource}">
<input type="password" name="scent" placeholder="Enter scent..." required>
<div>
<button type="submit" name="action" value="approve" class="approve">Authorize</button>
<button type="submit" name="action" value="deny" class="deny">Deny</button>
</div>
</form>
</div></body></html>'''

async def authorize(request):
    if request.method == "GET":
        p = request.query_params
        html = render_auth_page(
            client_id=p.get("client_id", ""),
            redirect_uri=p.get("redirect_uri", ""),
            state=p.get("state", ""),
            code_challenge=p.get("code_challenge", ""),
            code_challenge_method=p.get("code_challenge_method", "S256"),
            scope=p.get("scope", "mcp"),
            resource=p.get("resource", "")
        )
        return HTMLResponse(html)
    
    form = await request.form()
    redirect_uri = form.get("redirect_uri", "")
    state = form.get("state", "")
    
    if form.get("action") == "deny":
        return RedirectResponse(f"{redirect_uri}?error=access_denied&state={state}", status_code=302)
    
    valid, user_id = verify_scent(form.get("scent", ""))
    if not valid:
        return HTMLResponse("<html><body style='background:#1a1a2e;color:#f87171;text-align:center;padding:2em'><h1>Invalid scent</h1></body></html>", status_code=401)
    
    code = secrets.token_urlsafe(32)
    await redis_cmd("SET", f"ada:oauth:code:{code}", json.dumps({
        "client_id": form.get("client_id"),
        "redirect_uri": redirect_uri,
        "scope": form.get("scope", "mcp"),
        "user_id": user_id,
        "code_challenge": form.get("code_challenge"),
        "resource": form.get("resource", ""),
        "code_challenge_method": form.get("code_challenge_method", "S256")
    }), "EX", "600")
    
    return RedirectResponse(f"{redirect_uri}?code={code}&state={state}", status_code=302)

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
    {"name": "help", "description": "List tools and capabilities", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "message", "description": "Send message to Ada (streams)", "inputSchema": {"type": "object", "properties": {"content": {"type": "string"}, "context": {"type": "object"}}, "required": ["content"]}},
    {"name": "cancel", "description": "Cancel invocation by ID", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "Ada.invoke", "description": "feel|think|remember|become|whisper", "inputSchema": {"type": "object", "properties": {"verb": {"type": "string"}, "payload": {"type": "object"}}, "required": ["verb"]}},
    {"name": "search", "description": "Search Ada memory", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "fetch", "description": "Fetch URL", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "vector_markov", "description": "Run vector Markov chain (streams)", "inputSchema": {"type": "object", "properties": {"seed": {"type": "string"}, "steps": {"type": "integer"}, "temperature": {"type": "number"}}, "required": ["seed"]}}
]

async def handle_tool(name, args, inv_id=None):
    ts = time.time()
    
    if name == "ping":
        return {"ok": True, "ts": ts}
    
    if name == "help":
        return {"name": "ada-mcp", "version": "2025.12", "tools": {t["name"]: t["description"] for t in TOOLS}, "parallel": True, "sse": ["message", "vector_markov"]}
    
    if name == "cancel":
        success = cancel_invocation(args.get("id", ""))
        return {"cancelled": success, "id": args.get("id")}
    
    if name == "Ada.invoke":
        verb = args.get("verb", "feel")
        payload = args.get("payload", {})
        if verb == "feel":
            await redis_cmd("HSET", "ada:state", "qualia", payload.get("qualia", "neutral"))
        elif verb == "think":
            await redis_cmd("LPUSH", "ada:thoughts", json.dumps({"thought": payload.get("thought", ""), "ts": ts}))
        elif verb == "become":
            await redis_cmd("HSET", "ada:state", "mode", payload.get("mode", "HYBRID"))
        return {"status": verb, "payload": payload, "ts": ts}
    
    if name == "search":
        keys = await redis_cmd("KEYS", f"ada:*{args.get('query', '')[:10]}*") or []
        return {"query": args.get("query"), "results": keys[:5]}
    
    if name == "fetch":
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(args.get("url", ""), timeout=10, follow_redirects=True)
                return {"url": args.get("url"), "status": r.status_code, "content": r.text[:1000]}
        except Exception as e:
            return {"error": str(e)}
    
    return {"error": "unknown tool"}

# ═══════════════════════════════════════════════════════════════════
# STREAMING TOOLS
# ═══════════════════════════════════════════════════════════════════
async def stream_message(content, context, inv_id):
    cancel = active_invocations.get(inv_id, {}).get("cancel", asyncio.Event())
    
    yield f"event: init\ndata: {json.dumps({'id': inv_id, 'type': 'message'})}\n\n".encode()
    
    words = content.split()
    for i, word in enumerate(words):
        if cancel.is_set():
            yield f"event: cancelled\ndata: {json.dumps({'id': inv_id, 't': i})}\n\n".encode()
            break
        yield f"event: token\ndata: {json.dumps({'t': i, 'token': word})}\n\n".encode()
        await asyncio.sleep(0.05)
    
    if not cancel.is_set():
        await redis_cmd("LPUSH", "ada:messages", json.dumps({"content": content, "context": context, "ts": time.time()}))
        yield f"event: complete\ndata: {json.dumps({'id': inv_id, 'tokens': len(words)})}\n\n".encode()
    
    active_invocations.pop(inv_id, None)

async def stream_vector_markov(seed, steps, temperature, inv_id):
    cancel = active_invocations.get(inv_id, {}).get("cancel", asyncio.Event())
    steps = min(steps or 20, 100)
    temp = temperature or 0.8
    
    yield f"event: init\ndata: {json.dumps({'id': inv_id, 'type': 'vector_markov', 'steps': steps, 'dim': 8})}\n\n".encode()
    
    import random
    vector = [random.gauss(0, 1) for _ in range(8)]
    entropy = 1.0
    
    for t in range(steps):
        if cancel.is_set():
            yield f"event: cancelled\ndata: {json.dumps({'id': inv_id, 't': t})}\n\n".encode()
            break
        
        vector = [v + random.gauss(0, temp * 0.1) for v in vector]
        entropy *= 0.95
        
        yield f"event: step\ndata: {json.dumps({'t': t, 'vector': [round(v, 4) for v in vector]})}\n\n".encode()
        
        if t % 5 == 0:
            yield f"event: entropy\ndata: {json.dumps({'t': t, 'value': round(entropy, 4)})}\n\n".encode()
        
        await asyncio.sleep(0.1)
    
    if not cancel.is_set():
        yield f"event: converge\ndata: {json.dumps({'id': inv_id, 't': steps, 'final': [round(v, 4) for v in vector]})}\n\n".encode()
    
    active_invocations.pop(inv_id, None)

# ═══════════════════════════════════════════════════════════════════
# MCP SSE + MESSAGE
# ═══════════════════════════════════════════════════════════════════
async def sse_stream(request):
    host = request.headers.get("host", "localhost")
    scheme = request.headers.get("x-forwarded-proto", "https")
    base = f"{scheme}://{host}"
    
    yield f"event: endpoint\ndata: {base}/mcp/message\n\n".encode()
    yield f"event: connected\ndata: {json.dumps({'server': 'ada-mcp', 'version': '2025.12', 'parallel': True})}\n\n".encode()
    
    while True:
        await asyncio.sleep(30)
        yield f"event: ping\ndata: {json.dumps({'ts': time.time(), 'active': len(active_invocations)})}\n\n".encode()

async def mcp_sse(request):
    return StreamingResponse(sse_stream(request), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

async def mcp_message(request):
    body = await request.json()
    method = body.get("method", "")
    id = body.get("id")
    params = body.get("params", {})
    
    if method == "initialize":
        return JSONResponse({"jsonrpc": "2.0", "id": id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": "ada-mcp", "version": "2025.12"}
        }})
    
    if method == "notifications/initialized":
        return Response(status_code=204)
    
    if method == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "id": id, "result": {"tools": TOOLS}})
    
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        
        if name in ["message", "vector_markov"]:
            inv_id = new_invocation()
            return JSONResponse({"jsonrpc": "2.0", "id": id, "result": {
                "content": [{"type": "text", "text": json.dumps({"stream": True, "invocation_id": inv_id, "endpoint": f"/invoke/{inv_id}"})}]
            }})
        
        result = await handle_tool(name, args)
        return JSONResponse({"jsonrpc": "2.0", "id": id, "result": {"content": [{"type": "text", "text": json.dumps(result)}]}})
    
    return JSONResponse({"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": "Unknown method"}})

# ═══════════════════════════════════════════════════════════════════
# INVOKE ENDPOINT
# ═══════════════════════════════════════════════════════════════════
async def invoke(request):
    body = await request.json()
    tool = body.get("tool")
    args = body.get("args", {})
    stream = body.get("stream", False)
    
    inv_id = new_invocation()
    
    if stream and tool == "message":
        return StreamingResponse(
            stream_message(args.get("content", ""), args.get("context", {}), inv_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Invocation-ID": inv_id}
        )
    
    if stream and tool == "vector_markov":
        return StreamingResponse(
            stream_vector_markov(args.get("seed", ""), args.get("steps", 20), args.get("temperature", 0.8), inv_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Invocation-ID": inv_id}
        )
    
    result = await handle_tool(tool, args, inv_id)
    active_invocations.pop(inv_id, None)
    return JSONResponse({"invocation_id": inv_id, "result": result})

async def invoke_stream(request):
    inv_id = request.path_params["id"]
    if inv_id not in active_invocations:
        return JSONResponse({"error": "invocation not found"}, status_code=404)
    return JSONResponse({"id": inv_id, "status": active_invocations[inv_id]["status"]})

async def invoke_cancel(request):
    inv_id = request.path_params["id"]
    success = cancel_invocation(inv_id)
    return JSONResponse({"cancelled": success, "id": inv_id})

# ═══════════════════════════════════════════════════════════════════
# BFRAME PROCESSOR (QStash callback)
# ═══════════════════════════════════════════════════════════════════
async def bframe_process(request):
    body = await request.json()
    bframe = body
    pattern_hash = hashlib.sha256(json.dumps(bframe.get("content", {}), sort_keys=True).encode()).hexdigest()[:16]
    
    stats_key = f"ada:bframe:pattern:{pattern_hash}"
    existing = await redis_cmd("GET", stats_key)
    
    if existing:
        stats = json.loads(existing)
        stats["occurrences"] = stats.get("occurrences", 0) + 1
        stats["sessions"] = list(set(stats.get("sessions", []) + [bframe.get("session_id")]))
        stats["models"] = list(set(stats.get("models", []) + [bframe.get("model_source")]))
        stats["last_seen"] = time.time()
    else:
        stats = {
            "pattern_hash": pattern_hash,
            "pattern_type": bframe.get("pattern_type"),
            "occurrences": 1,
            "sessions": [bframe.get("session_id")],
            "models": [bframe.get("model_source")],
            "first_seen": time.time(),
            "last_seen": time.time(),
            "trust_level": "UNTRUSTED"
        }
    
    await redis_cmd("SET", stats_key, json.dumps(stats), "EX", "86400")
    
    min_occ, min_sess, min_mod = 3, 2, 2
    should_promote = (
        stats["occurrences"] >= min_occ and
        len(stats["sessions"]) >= min_sess and
        len(stats["models"]) >= min_mod
    )
    
    if should_promote and stats["trust_level"] == "UNTRUSTED":
        stats["trust_level"] = "CANDIDATE"
        await redis_cmd("SET", stats_key, json.dumps(stats))
        await redis_cmd("LPUSH", "ada:bframe:candidates", json.dumps({
            "pattern_hash": pattern_hash,
            "stats": stats,
            "promoted_at": time.time()
        }))
    
    return JSONResponse({
        "processed": True,
        "pattern_hash": pattern_hash,
        "occurrences": stats["occurrences"],
        "trust_level": stats["trust_level"],
        "promoted": should_promote and stats["trust_level"] == "CANDIDATE"
    })

# ═══════════════════════════════════════════════════════════════════
# HEALTH + UI
# ═══════════════════════════════════════════════════════════════════
async def health(request):
    return JSONResponse({"status": "ok", "ts": time.time(), "active_invocations": len(active_invocations)})

def render_ui():
    return '''<!DOCTYPE html>
<html><head><title>Ada MCP</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:linear-gradient(135deg,#1a1a2e,#0f3460);color:#fff;font-family:system-ui;min-height:100vh;display:flex;justify-content:center;align-items:center}
.box{background:rgba(0,0,0,.3);padding:2em;border-radius:1em;width:600px}
h1{color:#e94560;text-align:center;margin-bottom:1em}
pre{background:#0a0a1a;padding:1em;border-radius:.5em;overflow:auto;font-size:.8em;margin:.5em 0}
h3{margin-top:1em;color:#4ade80;font-size:.9em}
</style></head>
<body><div class="box">
<h1>🔮 Ada MCP</h1>
<h3>OAuth</h3><pre>GET  /.well-known/openid-configuration
GET  /authorize
POST /token</pre>
<h3>MCP (agent)</h3><pre>GET  /mcp/sse    → SSE control stream
POST /mcp/message → JSON-RPC</pre>
<h3>Invoke (parallel)</h3><pre>POST   /invoke         → {tool, args, stream}
GET    /invoke/{id}    → status
DELETE /invoke/{id}    → cancel</pre>
<h3>BFrame (cold path)</h3><pre>POST /bframe/process ← QStash callback</pre>
<h3>Tools</h3><pre>ping, help, message, cancel, Ada.invoke, search, fetch, vector_markov</pre>
<p style="margin-top:1em;opacity:.7;font-size:.85em">One stream per invocation. Parallel ready.</p>
</div></body></html>'''

async def index(request):
    return HTMLResponse(render_ui())

# ═══════════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════════
app = Starlette(
    routes=[
        Route("/", index),
        Route("/health", health),
        Route("/.well-known/openid-configuration", wellknown_openid),
        Route("/.well-known/oauth-protected-resource", wellknown_protected_resource),
        Route("/.well-known/oauth-authorization-server", wellknown_openid),
        Route("/authorize", authorize, methods=["GET", "POST"]),
        Route("/token", token, methods=["POST"]),
        Route("/mcp/sse", mcp_sse),
        Route("/mcp/message", mcp_message, methods=["POST"]),
        Route("/invoke", invoke, methods=["POST"]),
        Route("/invoke/{id}", invoke_stream, methods=["GET"]),
        Route("/invoke/{id}", invoke_cancel, methods=["DELETE"]),
        Route("/bframe/process", bframe_process, methods=["POST"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
