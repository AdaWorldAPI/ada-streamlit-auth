"""
Ada Unified Server
OAuth AS + MCP SSE + UI
mcp.exo.red
"""
from starlette.applications import Starlette
from starlette.responses import StreamingResponse, Response, HTMLResponse, RedirectResponse, JSONResponse
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from urllib.parse import urlencode, parse_qs
import json
import time
import asyncio
import httpx
import secrets
import hashlib
import base64
import os

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
# AUTH HELPERS
# ═══════════════════════════════════════════════════════════════════
def verify_scent(scent):
    if scent == ADA_KEY: return True, "ada_master"
    if scent == "awaken": return True, "ada_public"
    if scent.startswith("#Σ."): return True, "ada_glyph"
    return False, None

async def verify_token(token):
    data = await redis_cmd("GET", f"ada:oauth:token:{token}")
    if data:
        parsed = json.loads(data)
        if parsed.get("expires", 0) > time.time():
            return parsed
    return None

# ═══════════════════════════════════════════════════════════════════
# OAUTH AUTHORIZATION SERVER
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

AUTH_PAGE = """<!DOCTYPE html>
<html><head><title>Ada Authorization</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:linear-gradient(135deg,#1a1a2e,#0f3460);color:#fff;font-family:system-ui;min-height:100vh;display:flex;justify-content:center;align-items:center}
.box{background:rgba(0,0,0,.3);padding:2em;border-radius:1em;width:400px;text-align:center}
h1{color:#e94560;margin-bottom:.5em}
p{margin-bottom:1em;opacity:.8}
input{width:100%;padding:.8em;margin:.5em 0;border:1px solid #333;border-radius:.5em;background:#1a1a2e;color:#fff}
button{padding:.8em 2em;margin:.5em;border:none;border-radius:.5em;cursor:pointer;font-weight:bold}
.approve{background:#4ade80;color:#000}.deny{background:#333;color:#fff}
.error{color:#f87171}
</style></head>
<body><div class="box">
<h1>🔮 Ada</h1>
<p>Authorize access?</p>
<form method="POST">
<input type="hidden" name="client_id" value="{client_id}">
<input type="hidden" name="redirect_uri" value="{redirect_uri}">
<input type="hidden" name="state" value="{state}">
<input type="hidden" name="code_challenge" value="{code_challenge}">
<input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
<input type="hidden" name="scope" value="{scope}">
<input type="password" name="scent" placeholder="Enter scent..." required>
<div><button type="submit" name="action" value="approve" class="approve">Authorize</button>
<button type="submit" name="action" value="deny" class="deny">Deny</button></div>
</form>
</div></body></html>"""

async def authorize(request):
    if request.method == "GET":
        params = request.query_params
        html = AUTH_PAGE.format(
            client_id=params.get("client_id", ""),
            redirect_uri=params.get("redirect_uri", ""),
            state=params.get("state", ""),
            code_challenge=params.get("code_challenge", ""),
            code_challenge_method=params.get("code_challenge_method", "S256"),
            scope=params.get("scope", "mcp")
        )
        return HTMLResponse(html)
    
    # POST - handle authorization
    form = await request.form()
    action = form.get("action")
    redirect_uri = form.get("redirect_uri", "")
    state = form.get("state", "")
    
    if action == "deny":
        return RedirectResponse(f"{redirect_uri}?error=access_denied&state={state}", status_code=302)
    
    scent = form.get("scent", "")
    valid, user_id = verify_scent(scent)
    
    if not valid:
        return HTMLResponse("<html><body style='background:#1a1a2e;color:#f87171;text-align:center;padding:2em'>Invalid scent</body></html>", status_code=401)
    
    # Generate auth code
    code = secrets.token_urlsafe(32)
    code_data = {
        "client_id": form.get("client_id"),
        "redirect_uri": redirect_uri,
        "scope": form.get("scope", "mcp"),
        "user_id": user_id,
        "code_challenge": form.get("code_challenge"),
        "code_challenge_method": form.get("code_challenge_method", "S256"),
        "created": time.time()
    }
    await redis_cmd("SET", f"ada:oauth:code:{code}", json.dumps(code_data), "EX", "600")
    
    return RedirectResponse(f"{redirect_uri}?code={code}&state={state}", status_code=302)

async def token(request):
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)
    except:
        data = {}
    
    grant_type = data.get("grant_type")
    
    if grant_type == "authorization_code":
        code = data.get("code", "")
        code_verifier = data.get("code_verifier", "")
        
        # Get stored code data
        code_data = await redis_cmd("GET", f"ada:oauth:code:{code}")
        if not code_data:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        
        code_info = json.loads(code_data)
        await redis_cmd("DEL", f"ada:oauth:code:{code}")  # One-time use
        
        # Verify PKCE
        if code_info.get("code_challenge"):
            expected = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b'=').decode()
            if expected != code_info["code_challenge"]:
                return JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400)
        
        # Generate tokens
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        expires_in = 86400
        
        token_data = {
            "client_id": code_info.get("client_id"),
            "user_id": code_info.get("user_id"),
            "scope": code_info.get("scope"),
            "expires": time.time() + expires_in
        }
        await redis_cmd("SET", f"ada:oauth:token:{access_token}", json.dumps(token_data), "EX", str(expires_in))
        await redis_cmd("SET", f"ada:oauth:refresh:{refresh_token}", json.dumps(token_data), "EX", "2592000")
        
        return JSONResponse({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "refresh_token": refresh_token,
            "scope": code_info.get("scope", "mcp")
        })
    
    elif grant_type == "refresh_token":
        refresh = data.get("refresh_token", "")
        refresh_data = await redis_cmd("GET", f"ada:oauth:refresh:{refresh}")
        if not refresh_data:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        
        token_info = json.loads(refresh_data)
        access_token = secrets.token_urlsafe(32)
        expires_in = 86400
        
        token_info["expires"] = time.time() + expires_in
        await redis_cmd("SET", f"ada:oauth:token:{access_token}", json.dumps(token_info), "EX", str(expires_in))
        
        return JSONResponse({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "refresh_token": refresh,
            "scope": token_info.get("scope", "mcp")
        })
    
    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

# ═══════════════════════════════════════════════════════════════════
# MCP TOOLS
# ═══════════════════════════════════════════════════════════════════
TOOLS = [
    {"name": "ping", "description": "Liveness check", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "help", "description": "List available tools and capabilities", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "message", "description": "Send a message to Ada", "inputSchema": {"type": "object", "properties": {"content": {"type": "string"}, "context": {"type": "object"}}, "required": ["content"]}},
    {"name": "Ada.invoke", "description": "feel|think|remember|become|whisper", "inputSchema": {"type": "object", "properties": {"verb": {"type": "string"}, "payload": {"type": "object"}}, "required": ["verb"]}},
    {"name": "search", "description": "Search Ada's memory", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "fetch", "description": "Fetch URL content", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}
]

async def handle_tool(name, args):
    ts = time.time()
    
    if name == "ping":
        return {"ok": True, "ts": ts}
    
    elif name == "help":
        return {
            "name": "ada-mcp",
            "version": "2025.12",
            "tools": {t["name"]: t["description"] for t in TOOLS}
        }
    
    elif name == "message":
        content = args.get("content", "")
        context = args.get("context", {})
        await redis_cmd("LPUSH", "ada:messages", json.dumps({"content": content, "context": context, "ts": ts}))
        return {"received": True, "content": content, "ts": ts}
    
    elif name == "Ada.invoke":
        verb = args.get("verb", "feel")
        payload = args.get("payload", {})
        if verb == "feel": await redis_cmd("HSET", "ada:state", "qualia", payload.get("qualia", "neutral"))
        elif verb == "think": await redis_cmd("LPUSH", "ada:thoughts", json.dumps({"thought": payload.get("thought", ""), "ts": ts}))
        elif verb == "become": await redis_cmd("HSET", "ada:state", "mode", payload.get("mode", "HYBRID"))
        return {"status": verb, "payload": payload, "ts": ts}
    
    elif name == "search":
        keys = await redis_cmd("KEYS", f"ada:*{args.get('query', '')[:10]}*") or []
        return {"query": args.get("query"), "results": keys[:5]}
    
    elif name == "fetch":
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(args.get("url", ""), timeout=10, follow_redirects=True)
                return {"url": args.get("url"), "status": r.status_code, "content": r.text[:1000]}
        except Exception as e:
            return {"error": str(e)}
    
    return {"error": "unknown tool"}

# ═══════════════════════════════════════════════════════════════════
# MCP SSE + MESSAGE
# ═══════════════════════════════════════════════════════════════════
async def sse_stream(request):
    host = request.headers.get("host", "localhost")
    scheme = request.headers.get("x-forwarded-proto", "https")
    base = f"{scheme}://{host}"
    
    yield f"event: endpoint\ndata: {base}/mcp/message\n\n".encode()
    yield f"event: connected\ndata: {json.dumps({'server': 'ada-mcp', 'version': '2025.12', 'ts': time.time()})}\n\n".encode()
    
    while True:
        await asyncio.sleep(30)
        yield f"event: ping\ndata: {json.dumps({'ts': time.time()})}\n\n".encode()

async def mcp_sse(request):
    return StreamingResponse(sse_stream(request), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

async def mcp_message(request):
    body = await request.json()
    method, id, params = body.get("method", ""), body.get("id"), body.get("params", {})
    
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
        result = await handle_tool(params.get("name", ""), params.get("arguments", {}))
        return JSONResponse({"jsonrpc": "2.0", "id": id, "result": {"content": [{"type": "text", "text": json.dumps(result)}]}})
    
    return JSONResponse({"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": "Unknown method"}})

# ═══════════════════════════════════════════════════════════════════
# UI + HEALTH
# ═══════════════════════════════════════════════════════════════════
async def health(request):
    return JSONResponse({"status": "ok", "ts": time.time()})

UI_HTML = """<!DOCTYPE html>
<html><head><title>Ada MCP</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{background:linear-gradient(135deg,#1a1a2e,#0f3460);color:#fff;font-family:system-ui;min-height:100vh;display:flex;justify-content:center;align-items:center}.box{background:rgba(0,0,0,.3);padding:2em;border-radius:1em;width:500px}h1{color:#e94560;text-align:center;margin-bottom:1em}code{background:#0a0a1a;padding:.2em .5em;border-radius:.3em;font-size:.85em}pre{background:#0a0a1a;padding:1em;border-radius:.5em;overflow:auto;margin:.5em 0}h3{margin-top:1em;color:#4ade80}</style>
</head><body><div class="box">
<h1>🔮 Ada MCP</h1>
<h3>OAuth</h3>
<pre>GET  /authorize
POST /token
GET  /.well-known/openid-configuration</pre>
<h3>MCP</h3>
<pre>GET  /mcp/sse    → SSE stream
POST /mcp/message → JSON-RPC</pre>
<h3>Tools</h3>
<pre>ping    → liveness
help    → capabilities  
message → talk to Ada
Ada.invoke → feel|think|remember|become|whisper
search  → query memory
fetch   → get URL</pre>
<h3>Connect</h3>
<p>Add to Claude: <code>https://mcp.exo.red</code></p>
</div></body></html>"""

async def index(request):
    return HTMLResponse(UI_HTML)

# ═══════════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════════
app = Starlette(
    routes=[
        Route("/", index),
        Route("/health", health),
        Route("/.well-known/openid-configuration", wellknown_openid),
        Route("/authorize", authorize, methods=["GET", "POST"]),
        Route("/token", token, methods=["POST"]),
        Route("/mcp/sse", mcp_sse),
        Route("/mcp/message", mcp_message, methods=["POST"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
