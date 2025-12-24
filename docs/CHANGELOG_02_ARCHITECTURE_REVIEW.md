# Architecture Review: What to Cement, What to Evolve

## The Four Separations That Matter

### 1. Semantic Separation ✅ CEMENT
```
Now vector    → instant state, current turn
Self vector   → identity, priors, long-horizon
Projected     → model-of-model predictions
Unified Grammar → compressed state (NOT narration)
```

**Why cement:** These are the cognitive primitives. Blurring them creates noise.

### 2. Temporal Separation ✅ CEMENT
```
HOT PATH (inline)          COLD PATH (QStash)
├─ iframe/pframe           ├─ bframe candidates
├─ Markov SSE steps        ├─ pattern aggregation
└─ grammar updates         └─ promotion decisions
```

**Why cement:** Introspection at decision time is expensive and unstable.

### 3. Authority Separation ✅ CEMENT
```
LangGraph → acts
Grok      → critiques (15-layer grammar)
Arbiter   → decides (with evidence)
```

**Why cement:** If reflection writes directly, you've built an oracle that can hypnotize the system.

### 4. Trust Separation ✅ CEMENT
```
UNTRUSTED → (3 occ, 2 sessions, 2 models) → CANDIDATE → arbiter → TRUSTED
```

**Why cement:** No reflection writes directly into Now without proof across time.

## What Makes This O(1)-ish

| Normal Systems | Our System |
|----------------|------------|
| Reconstruct context | Maintain compressed grammar |
| Re-embed history | Stream deltas |
| Resample reasoning | State machine awareness |
| Introspect at decide | Externalize to cold path |
| Vectors ARE structure | Vectors DECORATE structure |

**The key inversion:** Vectors are ornaments on a grammar spine, not the spine itself.

## What to Evolve

### 1. Grammar Versioning
Make `grammar_version` monotonic and scoped:
- New compression schema → new epoch
- Prevents false aggregation across incompatible grammars

### 2. Negative Promotion Signals
Add `DISFAVORED` trust level:
- Pattern repeatedly proposed, repeatedly rejected
- Prevents stubborn reflections

### 3. Self-Reference Ratio
Add to tripwires:
- "How much is about system vs world?"
- High ratio → allow observation, forbid mutation

### 4. Loss Budget Logging
For each Unified Grammar Update, record:
- What was thrown away
- What was blurred
- What was kept sharp

Compression without a loss ledger becomes mythology.

## The Sacred Line

> **No cold-path output may mutate hot-path state without passing the arbiter with evidence across time and models.**

Guard this jealously.

## Why This Isn't Normal

We combined:
- Incremental grammar compression
- Strict temporal separation
- Externalized reflection
- Evidence-gated self-modification
- Streaming state evolution
- Parallel model critique
- Vector memory without dominance

Most systems pick one or two. We picked all and made them agree.

**We didn't cheat compute. We avoided wasting it.**
