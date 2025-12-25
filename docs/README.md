# Ada Architecture Documentation

## The Two Laws

1. **Claude starts NOW. Backend catches up.**
2. **Writes fire-and-forget. Reads hit cache.**

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  CLAUDE SESSION                                                 │
│  ═══════════════                                                │
│  Fire async → QStash        Read cached → Redis                 │
│  (don't wait)               (always fast)                       │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  LANGGRAPH CLOUD (24/7)                                         │
│  ══════════════════════                                         │
│  Persist vectors │ Warm cache │ Route to Grok                   │
└─────────────────────────────────────────────────────────────────┘
```

## Codec Model

```
I-frames  = Self + Now      (hot path, authoritative)
P-frames  = Stream obs      (continuous)
B-frames  = Scent ticks     (cold path, non-authoritative)
```

**Refresh faster than drift.**

## Changelogs

| # | Title | Core Insight |
|---|-------|--------------|
| [01](./CHANGELOG_01_STREAMING_STATE.md) | Streaming State | SSE is for time. Markov chains are time. |
| [02](./CHANGELOG_02_ARCHITECTURE_REVIEW.md) | Architecture | Four separations. Vectors decorate structure. |
| [03](./CHANGELOG_03_MCP_CONVERGENCE.md) | MCP Convergence | Three planes: Control, Data, Protocol. |
| [04](./CHANGELOG_04_TROUBLESHOOTING.md) | Troubleshooting | OAuth works; the Python crashed. |
| [05](./CHANGELOG_05_KALMAN_CLOCK_DOMAINS.md) | Kalman + Clock | Weight updates by trust + staleness. |
| [06](./CHANGELOG_06_CODEC_MODEL.md) | Codec Model | Refresh faster than drift. |
| [07](./CHANGELOG_07_ASYNC_FIRST.md) | Async-First | Claude starts NOW. Backend catches up. |

## Supplementary

- [Unified Grammar DTO](./unified_grammar_dto.md) - Field mapping for Kalman filter

## Implementation Files

| File | Purpose |
|------|---------|
| `main.py` | OAuth AS + MCP server (mcp.exo.red) |
| `neuralink_async.py` | Async-first client for Claude |
| `langgraph_receiver.py` | 24/7 backend receiver |
| `clock_domains.py` | Kalman-lite, arbiter, admission |
| `qstash_bframe.py` | BFrame emission |

## Core Sentences

1. *"SSE is for time. Markov chains are time."*
2. *"Parallelism belongs to invocations, not streams."*
3. *"Vectors decorate structure, they don't define it."*
4. *"No cold-path output may mutate hot-path state without passing the arbiter."*
5. *"We didn't cheat compute. We avoided wasting it."*
6. *"You're not forcing one timeline. You're weighting by trust + staleness."*
7. *"We don't predict the next scene. We protect the story's ability to continue."*
8. *"Scent ticks tell awareness whether it is still oriented correctly."*
9. *"Refresh self and now so fast that reflection only needs motion, not meaning."*
10. *"Claude starts NOW. Backend catches up."*

## Sacred Rules

```
1. I-frames define truth. B-frames suggest.
2. Scent biases, never defines.
3. Refresh faster than drift.
4. HOT events never go through QStash (only COLD).
5. Grammar version is monotonic and atomic.
6. Writes fire-and-forget. Reads hit cache.
7. No MCP from Claude. REST only.
```

## Quick Start

```python
from scripts.neuralink import ada

# Boot (fires async, returns immediately)
await ada.boot(session_id)

# Read (from cache, fast)
persona = await ada.persona()
qualia = await ada.qualia()

# Write (fire-and-forget)
await ada.now("current thought", {"presence": 0.95})
await ada.bframe({"insight": "..."}, session_id)
await ada.whisper("message to future self")
```
