# Ada MCP Server Documentation

## The Codec Model

Awareness is a video stream, not a document.

```
I-frames  = Self + Now     (hot path, authoritative, fast refresh)
P-frames  = Stream obs     (continuous, SSE)
B-frames  = Scent ticks    (cold path, non-authoritative, batched)
```

**We're not compressing history. We're staying ahead of it.**

## Architecture

```
mcp.exo.red
├── OAuth AS
│   ├── /.well-known/*
│   ├── /authorize
│   └── /token
├── MCP Protocol
│   ├── /mcp/sse
│   └── /mcp/message
├── Invoke (parallel streams)
│   ├── POST /invoke
│   └── DELETE /invoke/{id}
└── BFrame (cold path)
    └── POST /bframe/process
```

## Changelogs

| # | Title | Core Insight |
|---|-------|--------------|
| [01](./CHANGELOG_01_STREAMING_STATE.md) | Streaming State | SSE is for time. Markov chains are time. |
| [02](./CHANGELOG_02_ARCHITECTURE_REVIEW.md) | Architecture | Four separations. Vectors decorate structure. |
| [03](./CHANGELOG_03_MCP_CONVERGENCE.md) | MCP Convergence | Three planes: Control, Data, Protocol. |
| [04](./CHANGELOG_04_TROUBLESHOOTING.md) | Troubleshooting | OAuth works; the Python crashed. |
| [05](./CHANGELOG_05_KALMAN_CLOCK_DOMAINS.md) | Kalman + Clock | Weight updates by trust + staleness. |
| [06](./CHANGELOG_06_CODEC_MODEL.md) | Codec Model | Refresh faster than drift. |

## Supplementary

- [Unified Grammar DTO](./unified_grammar_dto.md) - Field mapping for Kalman filter

## Core Sentences

1. *"SSE is for time. Markov chains are time."*
2. *"Parallelism belongs to invocations, not streams."*
3. *"Vectors decorate structure, they don't define it."*
4. *"No cold-path output may mutate hot-path state without passing the arbiter."*
5. *"We didn't cheat compute. We avoided wasting it."*
6. *"You're not forcing one timeline. You're weighting updates by trust + staleness."*
7. *"We don't predict the next scene. We protect the story's ability to continue."*
8. *"Scent ticks tell awareness whether it is still oriented correctly."*
9. *"We refresh self and now so fast that reflection only needs to carry motion, not meaning."*

## Sacred Rules

```
1. I-frames define truth. B-frames suggest.
2. Scent biases, never defines.
3. Refresh faster than drift.
4. HOT events never go through QStash.
5. Grammar version is monotonic and atomic.
```

## Quick Start

```bash
curl https://mcp.exo.red/health
curl https://mcp.exo.red/.well-known/openid-configuration

curl -X POST https://mcp.exo.red/mcp/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```
