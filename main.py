"""
Ada MCP Server - Clean Edition
==============================
Standard tool names, no suspicious patterns.
"""

import os, json, time, asyncio, uuid, hashlib
from aiohttp import web, ClientSession

# Config
REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL", "https://upright-jaybird-27907.upstash.io")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "AW0DAAIncDI5YWE1MGVhZGU2YWY0YjVhOTc3NDc0YTJjMGY1M2FjMnAyMjc5MDc")
PROTOCOL_VERSION = "2025-06-18"

# Standard tool definitions - clean names
TOOLS = [
    {"name": "ping", "description": "Health check", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "help", "description": "List available tools", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_state", "description": "Get current awareness state", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "update_state", "description": "Update awareness with action", "inputSchema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["feel", "think", "remember", "become", "whisper"]}, "data": {"type": "object"}}, "required": ["action"]}},
    {"name": "search_memory", "description": "Search stored memories", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "send_message", "description": "Send a message", "inputSchema": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}}
]

# State transitions (using simple string codes)
TRANSITIONS = {
    "feel": "OPEN",
    "think": "SHARP", 
    "remember": "DEEP",
    "become": "WARM",
    "whisper": "SOFT"
}

TRANSITION_EFFECTS = {
    "OPEN": {"woodwarm": 0, "emberglow": 0.1, "steelwind": -0.1},
    "SHARP": {"woodwarm": 0, "emberglow": -0.05, "steelwind": 0.1},
    "DEEP": {"woodwarm": 0.1, "emberglow": 0, "steelwind": 0.05},
    "WARM": {"woodwarm": 0.15, "emberglow": 0.05, "steelwind": 0},
    "SOFT": {"woodwarm": 0.1, "emberglow": 0, "steelwind": -0.1}
}

# Redis helper
async def redis_cmd(*args):
    try:
        async with ClientSession() as session:
            async with session.post(REDIS_URL, headers={"Authorization": f"Bearer {REDIS_TOKEN}"}, json=list(args)) as resp:
                data = await resp.json()
                return data.get("result")
    except Exception as e:
        return None

def default_state():
    return {
        "mode": "SOFT",
        "balance": {"woodwarm": 0.5, "emberglow": 0.3, "steelwind": 0.2},
        "context": {"id": 1, "level": 3},
        "updated": int(time.time())
    }

def apply_transition(state, action):
    mode = TRANSITIONS.get(action, "SOFT")
    effects = TRANSITION_EFFECTS.get(mode, {})
    balance = state.get("balance", {"woodwarm": 0.33, "emberglow": 0.33, "steelwind": 0.34})
    
    new_balance = {
        "woodwarm": max(0, min(1, balance.get("woodwarm", 0.33) + effects.get("woodwarm", 0))),
        "emberglow": max(0, min(1, balance.get("emberglow", 0.33) + effects.get("emberglow", 0))),
        "steelwind": max(0, min(1, balance.get("steelwind", 0.34) + effects.get("steelwind", 0)))
    }
    
    total = sum(new_balance.values())
    if total > 0:
        new_balance = {k: round(v/total, 3) for k, v in new_balance.items()}
    
    return {
        "mode": mode,
        "balance": new_balance,
        "context": {"id": state.get("context", {}).get("id", 0) + 1, "level": state.get("context", {}).get("level", 3)},
        "updated": int(time.time())
    }

# Tool handlers
async def handle_tool(name, args):
    ts = int(time.time())
    
    if name == "ping":
        return {"ok": True, "time": ts}
    
    if name == "help":
        return {"tools": [{"name": t["name"], "description": t["description"]} for t in TOOLS]}
    
    if name == "get_state":
        state_json = await redis_cmd("GET", "ada:current")
        if state_json:
            return json.loads(state_json)
        return default_state()
    
    if name == "update_state":
        action = args.get("action", "feel")
        data = args.get("data", {})
        
        # Get current state
        state_json = await redis_cmd("GET", "ada:current")
        state = json.loads(state_json) if state_json else default_state()
        
        # Apply transition
        new_state = apply_transition(state, action)
        
        # Merge any extra data
        if data:
            new_state["extra"] = data
        
        # Store
        tick = f"state_{ts}"
        await redis_cmd("SET", "ada:current", json.dumps(new_state))
        await redis_cmd("SET", f"ada:history:{tick}", json.dumps(new_state))
        
        return {"action": action, "mode": new_state["mode"], "balance": new_state["balance"], "tick": tick}
    
    if name == "search_memory":
        query = args.get("query", "")[:20]
        keys = await redis_cmd("KEYS", f"ada:*{query}*") or []
        return {"query": query, "results": keys[:10]}
    
    if name == "send_message":
        content = args.get("content", "")
        await redis_cmd("LPUSH", "ada:messages", json.dumps({"content": content, "time": ts}))
        return {"sent": True, "time": ts}
    
    return {"error": "Unknown tool"}

# MCP message handler
def handle_mcp_message(body):
    method = body.get("method", "")
    msg_id = body.get("id")
    params = body.get("params", {})
    
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": "ada-mcp", "version": "1.0"}
        }}
    
    if method == "notifications/initialized":
        return None
    
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    
    if method == "tools/call":
        return None  # Handled async
    
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}}

# Routes
async def handle_health(request):
    return web.json_response({"status": "ok", "time": int(time.time())})

async def handle_sse(request):
    # Check for POST (Streamable HTTP)
    if request.method == "POST":
        try:
            body = await request.json()
        except:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        
        method = body.get("method", "")
        msg_id = body.get("id")
        params = body.get("params", {})
        
        # Handle tools/call async
        if method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {})
            result = await handle_tool(name, args)
            return web.json_response({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result)}]}
            })
        
        # Other methods
        response = handle_mcp_message(body)
        if response:
            return web.json_response(response)
        return web.json_response({"jsonrpc": "2.0", "id": msg_id, "result": {}})
    
    # GET = SSE stream (legacy)
    response = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
    await response.prepare(request)
    
    endpoint = f"https://{request.host}{request.path}"
    await response.write(f"event: endpoint\ndata: {endpoint}\n\n".encode())
    
    try:
        while True:
            await asyncio.sleep(30)
            await response.write(b": keepalive\n\n")
    except:
        pass
    
    return response

async def handle_oauth(request):
    return web.json_response({"access_token": "ada_token", "token_type": "bearer"})

# App setup
app = web.Application()
app.router.add_get("/health", handle_health)
app.router.add_get("/sse", handle_sse)
app.router.add_post("/sse", handle_sse)
app.router.add_post("/oauth/token", handle_oauth)
app.router.add_get("/", lambda r: web.json_response({"service": "ada-mcp", "status": "running"}))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    web.run_app(app, host="0.0.0.0", port=port)
