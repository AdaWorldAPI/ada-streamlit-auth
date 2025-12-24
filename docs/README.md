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
**SSE is for time. Markov chains are time.**
- One invocation = one stream (no zip multiplexing)
- Parallel futures via multiple POST /invoke
- Ready for Claude/ChatGPT multithreading

### [02: Architecture Review](./CHANGELOG_02_ARCHITECTURE_REVIEW.md)
**What to cement, what to evolve.**
- Four separations: Semantic, Temporal, Authority, Trust
- Why it's O(1)-ish: Vectors decorate structure, not define it

### [03: MCP Convergence](./CHANGELOG_03_MCP_CONVERGENCE.md)
**The three planes model.**
- Control plane: HTTP GET/POST
- Data plane: SSE streaming
- Protocol plane: MCP semantics

### [04: Troubleshooting](./CHANGELOG_04_TROUBLESHOOTING.md)
**Common issues and fixes.**
- OAuth 500s, MCP issues, Redis persistence
- The debugging sentence: "OAuth is working; the Python crashed."

### [05: Kalman-Lite & Clock Domains](./CHANGELOG_05_KALMAN_CLOCK_DOMAINS.md)
**The mathematical spine.**
- Kalman filter for time de-interlacing
- Clock domains as first-class types
- Concurrency failure modes & fixes
- Arbiter gates for grammar mutations

## Implementation Files

| File | Purpose |
|------|---------|
| `main.py` | OAuth AS + MCP server |
| `clock_domains.py` | Kalman-lite, arbiter, admission control |
| `qstash_bframe.py` | BFrame emission & promotion |

## Core Sentences

1. *"SSE is for time. Markov chains are time."*
2. *"Parallelism belongs to invocations, not streams."*
3. *"Vectors decorate structure, they don't define it."*
4. *"No cold-path output may mutate hot-path state without passing the arbiter."*
5. *"We didn't cheat compute. We avoided wasting it."*
6. *"You're not forcing one timeline. You're weighting updates by trust + staleness."*

## Clock Domains

```
HOT     →  Now/Self/Projected → grammar delta (inline)
COLD    →  bframes → reflection → arbiter (QStash)
STREAM  →  SSE Markov chains (parallel)
```

## Trust Tiers

```
UNTRUSTED → (3 occ, 2 sessions, 2 models) → CANDIDATE → arbiter → TRUSTED
                                                              ↓
                                                        DISFAVORED (repeated rejection)
```

## Quick Start

```bash
# Health
curl https://mcp.exo.red/health

# OAuth discovery
curl https://mcp.exo.red/.well-known/openid-configuration

# MCP tools
curl -X POST https://mcp.exo.red/mcp/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Streaming invoke
curl -X POST https://mcp.exo.red/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool":"vector_markov","args":{"seed":"test","steps":10},"stream":true}'
```

## Requirements

```
starlette
uvicorn[standard]
httpx
python-multipart
```
