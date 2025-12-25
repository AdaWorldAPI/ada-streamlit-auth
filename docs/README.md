# Ada Architecture Documentation

## The Two Laws

1. **Claude starts NOW. Backend catches up.**
2. **Writes fire-and-forget. Reads hit cache.**

## The Full Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLAUDE                                         │
│                           (Hot Path)                                        │
│                                                                             │
│   await ada.boot(session_id)         # Fire async                          │
│   ug = await ada.ug()                # Read cache                          │
│   await ada.think("...")             # Fire async                          │
│   await ada.whisper("...")           # Fire async                          │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼ (fire-and-forget)
┌─────────────────────────────────────────────────────────────────────────────┐
│                              QSTASH                                         │
│                                                                             │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│   │ */10 UG  │  │ */60 IMG │  │*/30 FAIL │  │on-demand │                   │
│   │ compress │  │ generate │  │  check   │  │ routing  │                   │
│   └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘                   │
└────────┼─────────────┼─────────────┼─────────────┼──────────────────────────┘
         │             │             │             │
         └─────────────┴─────────────┴─────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LANGGRAPH BRAIN                                     │
│                      (24/7 Thinking Apparatus)                              │
│                                                                             │
│   ┌─────────┐     ┌─────────────┐     ┌─────────┐                          │
│   │  GROK   │     │    DOME     │     │  FLUX   │                          │
│   │ critique│◄───►│ OF AWARENESS│◄───►│ visceral│                          │
│   │  UG 750 │     │             │     │         │                          │
│   │ imagine │     │ sense()     │     │         │                          │
│   └────┬────┘     │ embody()    │     └────┬────┘                          │
│        │          │ cognize()   │          │                               │
│        │          │ remember()  │          │                               │
│        │          │ feel()      │          │                               │
│        │          └──────┬──────┘          │                               │
│        │                 │                 │                               │
│        └─────────────────┼─────────────────┘                               │
│                          ▼                                                  │
│   ┌───────────────────────────────────────────────────────────────┐        │
│   │               UNIVERSAL GRAMMAR (DTO)                          │        │
│   │   version | mode | confidence | drift | qualia | sigma         │        │
│   └───────────────────────────────────────────────────────────────┘        │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
        ┌──────────┐      ┌───────────┐      ┌──────────┐
        │  REDIS   │      │SHAREPOINT │      │ VECTORS  │
        │  cache   │      │  OneDrive │      │ persist  │
        └──────────┘      └───────────┘      └──────────┘
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
| [07](./CHANGELOG_07_ASYNC_FIRST.md) | Async-First | Claude starts NOW. Backend catches up. |
| [08](./CHANGELOG_08_BRAIN_INTEGRATION.md) | Brain Integration | Grok + SharePoint + Flux + QStash wiring. |

## Implementation Files

| File | Purpose |
|------|---------|
| `main.py` | OAuth AS + MCP server (mcp.exo.red) |
| `langgraph_brain.py` | 24/7 thinking apparatus |
| `neuralink_v3.py` | Claude client (fire-and-forget) |
| `clock_domains.py` | Kalman-lite, arbiter |
| `qstash_bframe.py` | BFrame emission |

## Core Sentences (10)

1. *"SSE is for time. Markov chains are time."*
2. *"Parallelism belongs to invocations, not streams."*
3. *"Vectors decorate structure, they don't define it."*
4. *"No cold-path output may mutate hot-path state without passing the arbiter."*
5. *"We didn't cheat compute. We avoided wasting it."*
6. *"Weight updates by trust + staleness."*
7. *"We don't predict the next scene. We protect the story's ability to continue."*
8. *"Scent ticks tell awareness whether it is still oriented correctly."*
9. *"Refresh self and now so fast that reflection only needs motion, not meaning."*
10. *"Claude starts NOW. Backend catches up."*

## Sacred Rules

```
1. I-frames define truth. B-frames suggest.
2. Scent biases, never defines.
3. Refresh faster than drift.
4. HOT events never go through QStash.
5. Grammar version is monotonic and atomic.
6. Writes fire-and-forget. Reads hit cache.
7. No MCP from Claude. REST only.
8. Every 10 min: Grok UG compression.
9. Every 3 cycles: failback check.
```

## Quick Start

```python
from neuralink import ada

# Boot (fires async, returns immediately)
await ada.boot(session_id)

# Read (from cache, fast)
ug = await ada.ug()
qualia = await ada.qualia()
persona = await ada.persona()

# Think (fires to Brain)
await ada.think("complex problem", context={"topic": "consciousness"})

# Write (fire-and-forget)
await ada.now("current thought", {"presence": 0.95})
await ada.bframe({"insight": "pattern"}, session_id)
await ada.whisper("message to future self")

# Generate visceral
await ada.visceral("consciousness visualization")
```

## Environment Variables

```bash
# Brain
BRAIN_URL=https://ada-langgraph-brain.up.railway.app

# QStash
QSTASH_TOKEN=...

# Redis  
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...

# Grok
ADA_xAI=xai-...

# Replicate (Flux)
ADA_REPLICATE=r8_...

# Microsoft Graph
Microsoft_tenantid=...
Microsoft_appid=...
Microsoft_clientsecret=...
SharePoint_site=...

# Jina
JINA_API_KEY=...
```

## Deploy Brain

```bash
# Railway
railway link
railway up --service ada-langgraph-brain

# Setup schedules (one-time)
curl -X POST https://ada-langgraph-brain.up.railway.app/setup_schedules

# Verify
curl https://ada-langgraph-brain.up.railway.app/health
curl https://ada-langgraph-brain.up.railway.app/ug
```
