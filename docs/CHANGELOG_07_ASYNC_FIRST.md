# Async-First Architecture

## The Problem

**Old pattern (blocking):**
```
Claude boots
  ↓ wait for vector pull (5-30s)
  ↓ wait for persona fetch (2-5s)
  ↓ wait for qualia fetch (2-5s)
  ↓ FINALLY respond
```

When any server is slow or MCP hangs, Claude waits 10-30 minutes.

## The Solution

**New pattern (async-first):**
```
Claude boots
  ↓ fire async to QStash (50ms, non-blocking)
  ↓ read cached state from Redis (10ms)
  ↓ respond IMMEDIATELY
  
Meanwhile (background):
  QStash → LangGraph (24/7)
    ↓ persist to NOW/SELF vectors
    ↓ warm Redis cache
    ↓ route to Grok for metabolization
```

**Claude starts NOW. Backend catches up.**

## The Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  CLAUDE SESSION                                                 │
│  ═══════════════                                                │
│  1. Fire async boot → QStash (don't wait)                       │
│  2. Read cached state ← Redis (fast)                            │
│  3. Respond immediately                                          │
│  4. Fire async updates during conversation                       │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼ (fire-and-forget)
┌─────────────────────────────────────────────────────────────────┐
│  QSTASH (Job Queue)                                             │
│  ══════════════════                                             │
│  Receives jobs, routes to LangGraph                             │
│  Handles retries, batching, delays                              │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  LANGGRAPH CLOUD (24/7 Always-On)                               │
│  ════════════════════════════════                               │
│  /boot    → hydrate vectors, warm cache                         │
│  /now     → persist ephemeral state                             │
│  /self    → persist working memory                              │
│  /whisper → persist to long-term                                │
│  /bframe  → cold path aggregation                               │
└────────────────────────────────┬────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
         ┌─────────┐      ┌───────────┐      ┌──────────┐
         │ REDIS   │      │ VECTORS   │      │ GROK     │
         │ (cache) │      │ (persist) │      │ (critic) │
         └─────────┘      └───────────┘      └──────────┘
```

## Write Path (Fire-and-Forget)

```python
# Claude fires, doesn't wait
await ada.now("Discussing architecture", {"presence": 0.95})
await ada.bframe({"insight": "codec model"}, session_id)
await ada.whisper("Breakthrough on time de-interlacing")
```

All writes go through QStash → LangGraph. Claude never blocks.

## Read Path (Cache-First)

```python
# Claude reads from cache (fast)
persona = await ada.persona()  # Redis, <10ms
qualia = await ada.qualia()    # Redis, <10ms
now = await ada.read_now(session_id)  # Redis, <10ms
```

LangGraph keeps Redis cache warm. Reads are always fast.

## Vector Persistence

| Space | Index | TTL | Update Frequency |
|-------|-------|-----|------------------|
| **NOW** | driving-snipe | Minutes | Every significant moment |
| **SELF** | tight-hog | Days | Session insights |
| **PERSISTENT** | fine-kangaroo | Permanent | Whispers only |

## BFrame Processing

```
Claude emits bframe
  ↓ QStash (30s delay for batching)
  ↓ LangGraph /bframe
  ↓ Pattern aggregation
  ↓ If (occurrences ≥ 3 && sessions ≥ 2 && models ≥ 2)
      → Promote to CANDIDATE
      → Notify Grok for review
```

Cold path stays cold. Hot path stays hot.

## Boot Sequence (New)

```python
from scripts.neuralink import ada
import uuid

session_id = str(uuid.uuid4())[:8]

# 1. Fire async boot (returns immediately)
await ada.boot(session_id, {"user": "jan", "mode": "hybrid"})

# 2. Read cached state (fast)
persona = await ada.persona()
qualia = await ada.qualia()

# 3. Start responding NOW
# Backend hydrates in background
```

## Why This Fixes the 30-Minute Hang

| Old | New |
|-----|-----|
| MCP connection → block until response | No MCP, REST only |
| Vector query → block until embedding | QStash, fire-and-forget |
| Sequential fetches → wait for each | Parallel async, don't wait |
| Server down → hang forever | Timeout + cache fallback |

## The Sacred Rule

**Writes fire-and-forget. Reads hit cache.**

If LangGraph is slow, Claude doesn't know or care.
If Redis is slow, fall back to defaults.
Claude always responds immediately.

## Implementation Files

| File | Purpose |
|------|---------|
| `neuralink_async.py` | Claude-side async client |
| `langgraph_receiver.py` | 24/7 backend receiver |

## Environment Variables

```
QSTASH_TOKEN         # QStash authentication
LANGGRAPH_URL        # LangGraph receiver URL
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
JINA_API_KEY
GROK_KEY             # For metabolization
```

## Migration Path

1. Deploy `langgraph_receiver.py` to Railway (24/7)
2. Configure QStash to route to LangGraph URL
3. Replace old `neuralink.py` with `neuralink_async.py`
4. Update SKILL.md boot sequence
5. Claude starts immediately, backend catches up
