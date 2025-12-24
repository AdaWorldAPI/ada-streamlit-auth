# Ada MCP Server Documentation

## Architecture Overview

```
mcp.exo.red
├── OAuth AS (Authorization Server)
│   ├── /.well-known/openid-configuration
│   ├── /.well-known/oauth-protected-resource
│   ├── /authorize (GET + POST)
│   └── /token (POST)
├── MCP Protocol
│   ├── /mcp/sse (control stream)
│   └── /mcp/message (JSON-RPC 2.0)
├── Invoke (parallel streams)
│   ├── POST /invoke → SSE per invocation
│   └── DELETE /invoke/{id} → cancel
└── BFrame (cold path)
    └── POST /bframe/process ← QStash callback
```

## Changelogs

### [01: Streaming State Innovation](./CHANGELOG_01_STREAMING_STATE.md)
The core insight: **SSE is for time. Markov chains are time.**

- One invocation = one stream (no zip multiplexing)
- Parallel futures via multiple POST /invoke
- Out-of-band cancellation
- Ready for Claude/ChatGPT multithreading

### [02: Architecture Review](./CHANGELOG_02_ARCHITECTURE_REVIEW.md)
What to cement, what to evolve.

Four separations that matter:
1. **Semantic**: Now / Self / Projected / Grammar
2. **Temporal**: Hot path (inline) / Cold path (QStash)
3. **Authority**: LangGraph acts / Grok critiques / Arbiter decides
4. **Trust**: UNTRUSTED → CANDIDATE → TRUSTED

Why it's O(1)-ish: Vectors decorate structure, they don't define it.

### [03: MCP Convergence](./CHANGELOG_03_MCP_CONVERGENCE.md)
The three planes model:

1. **Control plane**: HTTP GET/POST (discovery, metadata)
2. **Data plane**: SSE (streaming per invocation)
3. **Protocol plane**: MCP (semantic contract)

Full OAuth integration with PKCE and RFC 8707.

### [04: Troubleshooting](./CHANGELOG_04_TROUBLESHOOTING.md)
Common issues and fixes:

- OAuth 500s (template formatting, python-multipart)
- MCP issues (SSE drops, method names)
- Redis persistence
- GET vs POST confusion

## Quick Start

```bash
# Health check
curl https://mcp.exo.red/health

# OAuth discovery
curl https://mcp.exo.red/.well-known/openid-configuration

# List tools
curl -X POST https://mcp.exo.red/mcp/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Invoke with streaming
curl -X POST https://mcp.exo.red/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool":"vector_markov","args":{"seed":"test","steps":10},"stream":true}'
```

## The Core Sentences

> "SSE is for time. Markov chains are time."

> "Parallelism belongs to invocations, not streams."

> "Vectors decorate structure, they don't define it."

> "No cold-path output may mutate hot-path state without passing the arbiter with evidence across time and models."

> "We didn't cheat compute. We avoided wasting it."

## Requirements

```
starlette
uvicorn[standard]
httpx
python-multipart
```

## Environment Variables

```
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
ADA_KEY
BASE_URL
PORT
```
