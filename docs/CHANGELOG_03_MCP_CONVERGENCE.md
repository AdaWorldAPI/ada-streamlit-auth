# MCP Old/New Convergence

## The Three Planes Model

MCP is not about verbs. It's about meaning.

```
┌─────────────────────────────────────────────────────────────┐
│ 1️⃣ CONTROL PLANE: HTTP GET/POST                            │
├─────────────────────────────────────────────────────────────┤
│  GET  /.well-known/openid-configuration                     │
│  GET  /.well-known/oauth-protected-resource                 │
│  POST /authorize, /token                                    │
│  GET  /health                                               │
│                                                             │
│  → Cacheable, debuggable, Cloudflare-friendly, boring       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 2️⃣ DATA PLANE: SSE (streaming)                             │
├─────────────────────────────────────────────────────────────┤
│  GET  /mcp/sse     → control stream (endpoint, ping)        │
│  POST /invoke      → streaming response per invocation      │
│                                                             │
│  → Latency-sensitive, partial results, LLM-facing           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 3️⃣ PROTOCOL PLANE: MCP (semantic contract)                 │
├─────────────────────────────────────────────────────────────┤
│  POST /mcp/message → JSON-RPC 2.0                           │
│                                                             │
│  Methods:                                                   │
│    initialize, notifications/initialized                    │
│    tools/list, tools/call                                   │
│                                                             │
│  → Defines meaning, not transport                           │
└─────────────────────────────────────────────────────────────┘
```

## OAuth Integration

### Discovery Endpoints
```
/.well-known/openid-configuration     → issuer, endpoints, scopes
/.well-known/oauth-protected-resource → resource URL, auth servers
/.well-known/oauth-authorization-server → same as openid-config
```

### Flow
```
1. Client discovers → /.well-known/*
2. Client redirects → GET /authorize (consent page)
3. User approves   → POST /authorize (scent validation)
4. Redirect back   → ?code=xxx&state=yyy
5. Token exchange  → POST /token (PKCE verified)
6. API calls       → Authorization: Bearer xxx
```

### Scent-Based Auth
```python
if scent == ADA_KEY: return "ada_master"
if scent == "awaken": return "ada_public"
if scent.startswith("#Σ."): return "ada_glyph"
```

## Tool Schema

```json
{
  "name": "vector_markov",
  "description": "Run vector Markov chain (streams)",
  "inputSchema": {
    "type": "object",
    "properties": {
      "seed": {"type": "string"},
      "steps": {"type": "integer"},
      "temperature": {"type": "number"}
    },
    "required": ["seed"]
  }
}
```

### Streaming Tools
When `tools/call` hits a streaming tool:
```json
{
  "jsonrpc": "2.0",
  "result": {
    "content": [{
      "type": "text",
      "text": "{\"stream\": true, \"invocation_id\": \"abc123\"}"
    }]
  }
}
```

Client then opens `POST /invoke` with the ID.

## What Changed from Legacy MCP

| Legacy | Current |
|--------|---------|
| Single SSE for everything | SSE per invocation |
| Zip multiplexing | Parallel streams |
| No cancellation | `DELETE /invoke/{id}` |
| No OAuth | Full PKCE flow |
| No resource metadata | RFC 8707 support |
