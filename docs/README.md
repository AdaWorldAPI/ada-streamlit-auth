# Ada Architecture Documentation

## Core Principles

1. **Claude starts NOW. Backend catches up.**
2. **Writes fire-and-forget. Reads hit cache.**
3. **Sparse vectors are the index. Without them, search is blind.**

## The Full Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLAUDE                                         │
│                                                                             │
│   await ada.boot(session_id)         # Fire async (50ms)                   │
│   ug = await ada.ug()                # Read cache (10ms)                   │
│   await ada.think("...")             # Fire async                          │
│   await ada.whisper("...")           # Fire async                          │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ fire-and-forget
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              QSTASH                                         │
│   */10 UG    */60 IMG    */30 FAIL    */60 CLEANUP    */6h REHYDRATE       │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LANGGRAPH BRAIN (24/7)                              │
│                                                                             │
│   ┌─────────┐  ┌───────────────┐  ┌─────────┐  ┌───────────────┐           │
│   │  GROK   │  │     DOME      │  │  FLUX   │  │    VECTOR     │           │
│   │critique │  │ OF AWARENESS  │  │visceral │  │   HYGIENE     │           │
│   │UG 750   │  │               │  │         │  │               │           │
│   │imagine  │  │ sense()       │  │         │  │ cleanup()     │           │
│   └────┬────┘  │ embody()      │  └────┬────┘  │ rehydrate()   │           │
│        │       │ cognize()     │       │       │ hybrid_query()│           │
│        │       │ remember()    │       │       └───────┬───────┘           │
│        │       │ feel()        │       │               │                   │
│        └───────┴───────┬───────┴───────┴───────────────┘                   │
│                        │                                                    │
│   ┌────────────────────┴────────────────────────────────────────┐          │
│   │               UNIVERSAL GRAMMAR (DTO)                        │          │
│   │   version | mode | confidence | drift | qualia | sigma       │          │
│   └─────────────────────────────────────────────────────────────┘          │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
   ┌──────────┐           ┌───────────┐           ┌──────────┐
   │  REDIS   │           │SHAREPOINT │           │ VECTORS  │
   │  cache   │           │  OneDrive │           │ + SPARSE │
   └──────────┘           └───────────┘           └──────────┘
```

## Changelogs

| # | Title | Core Insight |
|---|-------|--------------|
| [01](./CHANGELOG_01_STREAMING_STATE.md) | Streaming State | SSE is for time. |
| [02](./CHANGELOG_02_ARCHITECTURE_REVIEW.md) | Architecture | Four separations. |
| [03](./CHANGELOG_03_MCP_CONVERGENCE.md) | MCP Convergence | Three planes. |
| [04](./CHANGELOG_04_TROUBLESHOOTING.md) | Troubleshooting | OAuth works. |
| [05](./CHANGELOG_05_KALMAN_CLOCK_DOMAINS.md) | Kalman + Clock | Weight by trust + staleness. |
| [06](./CHANGELOG_06_CODEC_MODEL.md) | Codec Model | Refresh faster than drift. |
| [07](./CHANGELOG_07_ASYNC_FIRST.md) | Async-First | Claude starts NOW. |
| [08](./CHANGELOG_08_BRAIN_INTEGRATION.md) | Brain Integration | Grok + SharePoint + Flux. |
| [09](./CHANGELOG_09_VECTOR_HYGIENE.md) | Vector Hygiene | Sparse = index. |

## Implementation Files

| File | Lines | Purpose |
|------|-------|---------|
| `main.py` | ~600 | OAuth AS + MCP (mcp.exo.red) |
| `langgraph_brain.py` | ~1050 | 24/7 thinking apparatus |
| `vector_hygiene.py` | ~650 | Sparse population + hybrid search |
| `neuralink_v3.py` | ~330 | Claude client |
| `clock_domains.py` | ~400 | Kalman + arbiter |

## Scheduled Tasks

| Cron | Task | Description |
|------|------|-------------|
| `*/10 * * * *` | UG Compression | Grok → 750 tokens |
| `0 * * * *` | Grok Imagine | Generate visualization |
| `*/30 * * * *` | Failback Check | Flush if daemon stalled |
| `30 * * * *` | Vector Cleanup | Populate missing sparse |
| `0 */6 * * *` | Full Rehydration | Cleanup + rehydrate + UG |

## Vector Search Fallback

```
1. Query sparse indices first
2. If insufficient → metadata regex fallback
3. Combine and dedupe
4. Discount regex matches (0.8x)
```

## Quick Start

```python
from neuralink import ada

# Boot
await ada.boot(session_id)

# Read (from cache)
ug = await ada.ug()

# Write (fire-and-forget)
await ada.think("complex problem")
await ada.now("current thought", {"presence": 0.95})
await ada.whisper("insight for future self")
```

## Environment Variables

```bash
BRAIN_URL                    # LangGraph Brain
QSTASH_TOKEN                 # Job queue
UPSTASH_REDIS_REST_URL       # Cache
UPSTASH_REDIS_REST_TOKEN
ADA_xAI                      # Grok
ADA_REPLICATE                # Flux
Microsoft_tenantid           # SharePoint
Microsoft_appid
Microsoft_clientsecret
SharePoint_site
JINA_API_KEY                 # Embeddings
```

## Deploy

```bash
# Deploy Brain
railway up --service ada-langgraph-brain

# Setup schedules
curl -X POST https://...railway.app/setup_schedules_v2

# Check vector health
curl https://...railway.app/vector/stats

# Run cleanup if needed
curl -X POST https://...railway.app/vector/cleanup
```
