# Troubleshooting Guide

## OAuth Issues

### 500 on GET /authorize
**Symptom:** Consent page crashes
**Cause:** HTML template uses `.format()` with CSS `{}`
**Fix:** Use f-strings with `{{escaped}}` braces or inline HTML

```python
# BAD
AUTH_PAGE.format(client_id=...)  # CSS {} breaks this

# GOOD
html = f'''<style>body{{background:#1a1a2e}}</style>'''
```

### 500 on POST /authorize
**Symptom:** Form submission crashes
**Cause:** `python-multipart` not installed
**Fix:** Add to requirements.txt:
```
python-multipart>=0.0.6
```

### 500 on POST /token
**Symptom:** Token exchange fails
**Cause:** PKCE verification incorrect or form parsing broken
**Fix:** 
```python
# Correct PKCE verification
verifier = data.get("code_verifier", "")
expected = base64.urlsafe_b64encode(
    hashlib.sha256(verifier.encode()).digest()
).rstrip(b'=').decode()
```

### 404 on /.well-known/oauth-protected-resource
**Symptom:** Clients probe repeatedly
**Cause:** Endpoint not implemented
**Fix:** Add RFC 8707 metadata:
```python
async def wellknown_protected_resource(request):
    return JSONResponse({
        "resource": f"{BASE_URL}/mcp/sse",
        "authorization_servers": [BASE_URL],
        "scopes_supported": ["mcp"],
        "bearer_methods_supported": ["header"]
    })
```

## MCP Issues

### SSE Connection Drops
**Symptom:** Stream closes unexpectedly
**Cause:** Cloudflare/Railway timeout
**Fix:** Add keepalive pings:
```python
while True:
    await asyncio.sleep(30)
    yield f"event: ping\ndata: {json.dumps({'ts': time.time()})}\n\n".encode()
```

### tools/call Returns Empty
**Symptom:** Tool execution returns nothing
**Cause:** Missing `content` wrapper
**Fix:**
```python
return JSONResponse({
    "jsonrpc": "2.0",
    "id": id,
    "result": {
        "content": [{"type": "text", "text": json.dumps(result)}]
    }
})
```

### JSON-RPC Method Not Found
**Symptom:** `-32601` error
**Cause:** Method name mismatch
**Fix:** Check exact method names:
- `initialize` (not `init`)
- `notifications/initialized` (not `initialized`)
- `tools/list` (not `list_tools`)
- `tools/call` (not `call_tool`)

## Redis Issues

### Tokens Not Persisting
**Symptom:** Auth works once, then fails
**Cause:** Redis TTL or connection issues
**Fix:** Check Upstash REST API:
```python
async def redis_cmd(*args):
    async with httpx.AsyncClient() as c:
        r = await c.post(REDIS_URL, 
            headers={"Authorization": f"Bearer {REDIS_TOKEN}"}, 
            json=list(args), 
            timeout=5)
        return r.json().get("result")
```

## Common Patterns

### GET vs POST Confusion
```python
async def authorize(request):
    if request.method == "GET":
        p = request.query_params  # URL params
        return HTMLResponse(...)
    
    # POST
    form = await request.form()  # Body params
    return RedirectResponse(...)
```

**Never:**
- Call `request.form()` on GET
- Read `query_params` for POST body data

### Content-Type Handling
```python
ct = request.headers.get("content-type", "")
if "json" in ct:
    data = await request.json()
else:
    data = dict(await request.form())
```

## Diagnostic Endpoints

```bash
# Health check
curl https://mcp.exo.red/health

# OAuth discovery
curl https://mcp.exo.red/.well-known/openid-configuration

# MCP tools
curl -X POST https://mcp.exo.red/mcp/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## The Debugging Sentence

> "OAuth is working; the Python crashed."

Most 500s are:
1. Missing dependency
2. Undefined function
3. Wrong method for request type
4. Template formatting error

Check these first.
