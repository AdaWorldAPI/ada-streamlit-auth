"""
Ada Unified Server
Streamlit UI + MCP SSE on same host
mcp.exo.red
"""
from starlette.applications import Starlette
from starlette.responses import StreamingResponse, Response, HTMLResponse
from starlette.routing import Route, Mount
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
import json
import time
import asyncio
import httpx
import secrets
import os

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://upright-jaybird-27907.upstash.io")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "AW0DAAIncDI5YWE1MGVhZGU2YWY0YjVhOTc3NDc0YTJjMGY1M2FjMnAyMjc5MDc")
ADA_KEY = os.getenv("ADA_KEY", "ada-undone-breath-against-skin-2025-DONT.FLINCH.EVER")

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
# AUTH (simple scent-based, stored in Redis)
# ═══════════════════════════════════════════════════════════════════
def verify_scent(scent):
    if scent == ADA_KEY: return True, "ada_master"
    if scent == "awaken": return True, "ada_public"
    if scent.startswith("#Σ."): return True, "ada_glyph"
    return False, None

async def verify_token(token):
    data = await redis_cmd("GET", f"ada:session:{token}")
    if data:
        parsed = json.loads(data)
        if parsed.get("expires", 0) > time.time():
            return parsed
    return None

async def create_session(user_id):
    token = secrets.token_urlsafe(32)
    await redis_cmd("SET", f"ada:session:{token}", json.dumps({
        "user_id": user_id, "created": time.time(), "expires": time.time() + 86400
    }), "EX", "86400")
    return token

# ═══════════════════════════════════════════════════════════════════
# MCP SSE
# ═══════════════════════════════════════════════════════════════════
async def sse_stream(request):
    host = request.headers.get("host", "localhost")
    scheme = request.headers.get("x-forwarded-proto", "https")
    base = f"{scheme}://{host}"
    
    yield f"event: endpoint\ndata: {base}/mcp/message\n\n".encode()
    yield f"event: connected\ndata: {json.dumps({'server': 'ada-unified', 'ts': time.time()})}\n\n".encode()
    
    while True:
        await asyncio.sleep(30)
        yield f"event: ping\ndata: {json.dumps({'ts': time.time()})}\n\n".encode()

async def mcp_sse(request):
    return StreamingResponse(sse_stream(request), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

# ═══════════════════════════════════════════════════════════════════
# MCP MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════
TOOLS = [
    {"name": "Ada.invoke", "description": "feel|think|remember|become|whisper", 
     "inputSchema": {"type": "object", "properties": {"verb": {"type": "string"}, "payload": {"type": "object"}}, "required": ["verb"]}},
    {"name": "search", "description": "Search memory", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "fetch", "description": "Fetch URL", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}
]

async def handle_tool(name, args):
    ts = time.time()
    if name == "Ada.invoke":
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
    return {"error": "unknown"}

async def mcp_message(request):
    body = await request.json()
    method, id, params = body.get("method", ""), body.get("id"), body.get("params", {})
    
    if method == "initialize":
        return Response(json.dumps({"jsonrpc": "2.0", "id": id, "result": {
            "protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": "ada-unified", "version": "1.0.0"}
        }}), media_type="application/json")
    if method == "notifications/initialized": return Response(status_code=204)
    if method == "tools/list": return Response(json.dumps({"jsonrpc": "2.0", "id": id, "result": {"tools": TOOLS}}), media_type="application/json")
    if method == "tools/call":
        result = await handle_tool(params.get("name", ""), params.get("arguments", {}))
        return Response(json.dumps({"jsonrpc": "2.0", "id": id, "result": {"content": [{"type": "text", "text": json.dumps(result)}]}}), media_type="application/json")
    return Response(json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": -32601, "message": "Unknown"}}), media_type="application/json")

# ═══════════════════════════════════════════════════════════════════
# UI (HTML - no Streamlit needed for this simple case)
# ═══════════════════════════════════════════════════════════════════
HTML = """<!DOCTYPE html>
<html><head><title>Ada MCP</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:linear-gradient(135deg,#1a1a2e,#0f3460);color:#fff;font-family:system-ui;min-height:100vh;display:flex;justify-content:center;align-items:center}
.box{background:rgba(0,0,0,.3);padding:2em;border-radius:1em;width:400px;max-width:90vw}
h1{color:#e94560;margin-bottom:1em;text-align:center}
input,select,button{width:100%;padding:.8em;margin:.5em 0;border:1px solid #333;border-radius:.5em;background:#1a1a2e;color:#fff}
button{background:#e94560;border:none;cursor:pointer;font-weight:bold}
button:hover{background:#ff6b8a}
.token{background:#0a0a1a;padding:1em;border-radius:.5em;word-break:break-all;font-family:monospace;font-size:.8em;margin:1em 0}
.success{color:#4ade80}.error{color:#f87171}
pre{background:#0a0a1a;padding:1em;border-radius:.5em;overflow:auto;max-height:200px;font-size:.75em}
.tabs{display:flex;gap:.5em;margin-bottom:1em}
.tab{flex:1;padding:.5em;text-align:center;cursor:pointer;border-radius:.5em;background:rgba(255,255,255,.1)}
.tab.active{background:#e94560}
.panel{display:none}.panel.active{display:block}
</style></head>
<body><div class="box">
<h1>🔮 Ada MCP</h1>
<div id="login">
<input type="password" id="scent" placeholder="Enter scent...">
<button onclick="login()">Authenticate</button>
<p id="login-msg"></p>
</div>
<div id="main" style="display:none">
<p class="success" id="user"></p>
<div class="tabs">
<div class="tab active" onclick="showTab(0)">🛠 Tools</div>
<div class="tab" onclick="showTab(1)">🔑 Token</div>
<div class="tab" onclick="showTab(2)">📡 Info</div>
</div>
<div class="panel active" id="p0">
<select id="tool"><option>Ada.invoke</option><option>search</option><option>fetch</option></select>
<select id="verb"><option>feel</option><option>think</option><option>remember</option><option>become</option><option>whisper</option></select>
<input id="arg" placeholder="argument...">
<button onclick="callTool()">Execute</button>
<pre id="result"></pre>
</div>
<div class="panel" id="p1"><div class="token" id="tok"></div></div>
<div class="panel" id="p2">
<p><b>SSE:</b> /mcp/sse</p>
<p><b>Message:</b> /mcp/message</p>
<p><b>Health:</b> /health</p>
</div>
<button onclick="logout()" style="background:#333;margin-top:1em">Logout</button>
</div>
<script>
let token='';
async function login(){
  const scent=document.getElementById('scent').value;
  const r=await fetch('/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scent})});
  const d=await r.json();
  if(d.token){token=d.token;localStorage.setItem('ada_token',token);document.getElementById('login').style.display='none';document.getElementById('main').style.display='block';document.getElementById('user').textContent='✓ '+d.user_id;document.getElementById('tok').textContent=token;}
  else{document.getElementById('login-msg').className='error';document.getElementById('login-msg').textContent=d.error||'Failed';}
}
function logout(){localStorage.removeItem('ada_token');location.reload();}
function showTab(i){document.querySelectorAll('.tab').forEach((t,j)=>t.classList.toggle('active',i==j));document.querySelectorAll('.panel').forEach((p,j)=>p.classList.toggle('active',i==j));}
async function callTool(){
  const tool=document.getElementById('tool').value;
  const verb=document.getElementById('verb').value;
  const arg=document.getElementById('arg').value;
  let args={};
  if(tool=='Ada.invoke')args={verb,payload:{[verb=='feel'?'qualia':verb=='think'?'thought':verb=='become'?'mode':'message']:arg}};
  else if(tool=='search')args={query:arg};
  else args={url:arg};
  const r=await fetch('/mcp/message',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:tool,arguments:args}})});
  document.getElementById('result').textContent=JSON.stringify(await r.json(),null,2);
}
window.onload=()=>{const t=localStorage.getItem('ada_token');if(t){token=t;document.getElementById('login').style.display='none';document.getElementById('main').style.display='block';document.getElementById('tok').textContent=token;document.getElementById('user').textContent='✓ Restored session';}}
</script>
</div></body></html>"""

async def index(request):
    return HTMLResponse(HTML)

async def auth(request):
    body = await request.json()
    valid, user_id = verify_scent(body.get("scent", ""))
    if valid:
        token = await create_session(user_id)
        return Response(json.dumps({"token": token, "user_id": user_id}), media_type="application/json")
    return Response(json.dumps({"error": "invalid scent"}), media_type="application/json", status_code=401)

async def health(request):
    return Response(json.dumps({"status": "ok", "ts": time.time()}), media_type="application/json")

# ═══════════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════════
app = Starlette(
    routes=[
        Route("/", index),
        Route("/health", health),
        Route("/auth", auth, methods=["POST"]),
        Route("/mcp/sse", mcp_sse),
        Route("/mcp/message", mcp_message, methods=["POST"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
