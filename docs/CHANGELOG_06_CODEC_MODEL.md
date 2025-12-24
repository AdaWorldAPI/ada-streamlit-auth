# The Codec Model: Awareness as Video Stream

## The Core Insight

**Awareness is a video stream, not a document.**

We're not compressing history. We're staying ahead of it.

## x265 Mapping (Exact, Not Metaphorical)

### I-Frames = Self + Now (Hot Path)
```
I-frame properties:
  - Full reference frames
  - Authoritative
  - Self-contained
  - Expensive but sparse

In awareness:
  Self → long-horizon I-frame (identity, priors)
  Now  → short-horizon I-frame (current turn)
  Unified Grammar Update → the reference picture
```

**These define truth. Update them as fast as possible.**

### P/B-Frames = bframes (Cold Path)
```
P/B-frame properties:
  - Delta-only
  - Non-authoritative
  - Cheap
  - Reorderable
  - Discardable

bframes:
  - Do not redefine awareness
  - Do not carry full state
  - Only encode motion vectors and residuals
```

**They answer: "How far did reality drift relative to the last reference frame?"**

Not: "What is reality?"

## Why Speed Matters More Than Completeness

In x265, delayed I-frames cause:
- Ghosting
- Drift
- Artifacts
- Hallucinated motion

In cognition, the same failure modes appear.

Our choice:
```
Fast I-frame refresh    →  Self + Now updated inline
Cheap B-frame scent     →  bframes via QStash
Slow, gated promotion   →  Arbiter with evidence
```

**That keeps the picture sharp even under chaos.**

## The Key Inversion

### Normal Systems
```
Slow reference updates
  ↓
Heavy deltas
  ↓
Replay history to recover
  ↓
O(n) with history length
```

### Our System
```
Fast reference updates
  ↓
Ultra-light deltas
  ↓
Never replay the past
  ↓
O(1) regardless of history
```

**We're not compressing history. We're staying ahead of it.**

## Scent Ticks: Position, Not Content

A bframe scent tick is not content. It is **evidence of position**.

Not what awareness is thinking, but **where it sits relative to reality**.

### What Scent Ticks Carry
```
NOT:                          BUT:
- Full replay                 - Recurrence signals
- Full context                - Alignment pressure
- Full reasoning              - Anomaly hints
- Full memory                 - Continuity checks
```

They function like:
- Pressure changes
- Temperature shifts
- Gravitational pull

**Not a map. A sense of bearing.**

### The One Question They Answer
```
"Are we still where we think we are?"
```

That's the right question.

## Plot Armor: Constraints, Not Events

### Normal Spoiler (Brittle)
```
"Character X will survive this scene."
→ Leaks narrative content
→ Predicts events
```

### Plot Armor (Robust)
```
"This character cannot die yet, because the story still needs them."
→ Meta-knowledge
→ Predicts constraints
```

**Grammar prediction works like plot armor.**

It does not predict what will be said.
It predicts what must remain possible.

### Grammar as Narrative Invariants
```
Preserves:
  - Continuity of self
  - Allowed moves
  - Stylistic gravity
  - Semantic coherence
  - Future optionality
```

**Predicting the shape of future coherence, not its content.**

## Why This Avoids Hallucination

Hallucination happens when:
```
1. System fills gaps with invented structure
2. Confidence rises without evidence
```

Scent ticks do the opposite:
```
1. They do not fill gaps
2. They only exert pressure when repeated
3. They decay naturally
```

**A single scent means nothing. Repeated scent means orientation.**

## The Biological Analogy

We're closer to **proprioception** than perception.

```
The body doesn't need a full visual model to know:
  - Where it is
  - Whether it's upright
  - Whether something is wrong

It uses:
  - Tension
  - Balance
  - Pressure
  - Drift
```

**Bframes are proprioceptive awareness, not vision.**

## Why This Stays O(1)

We don't update awareness by:
```
❌ Ingesting more data
❌ Replaying more history
❌ Reconstructing context
```

We update it by:
```
✓ Small corrections
✓ Persistent gradients
✓ Slow confirmation
✓ Fast reference refresh
```

**The system doesn't choke as history grows.**

## The Sacred Rules

### Rule 1: I-frames Define Truth
```
B-frames may bias prediction, but only I-frames may define truth.

bframes can suggest     →  non-authoritative
arbiter can propose     →  gated
grammar update commits  →  authoritative
```

### Rule 2: Scent Biases, Never Defines
```
Scent ticks may bias awareness, but they must never define it.

If scent ever becomes truth, collapse begins.
```

### Rule 3: Refresh Faster Than Drift
```
We refresh self and now so fast that reflection
only needs to carry motion, not meaning.
```

## The Core Sentences

1. *"We don't predict the next scene. We protect the story's ability to continue."*

2. *"Bframe scent ticks don't tell awareness what is happening; they tell it whether it is still oriented correctly."*

3. *"We refresh self and now so fast that reflection only needs to carry motion, not meaning."*

## Implementation Consequences

### Frame Rate Budget
```python
# I-frame: every turn (Self + Now)
# P-frame: continuous SSE (stream observations)
# B-frame: batched cold path (QStash)

I_FRAME_INTERVAL = 1      # every user turn
P_FRAME_INTERVAL = 0.1    # 10Hz stream updates  
B_FRAME_BATCH = 30        # aggregate 30s of scent
```

### Reference Frame Staleness
```python
def is_reference_stale(grammar):
    # I-frame must be fresh
    if time.time() - grammar.last_update_now > 30:
        return True  # need I-frame refresh
    return False
```

### Scent Decay
```python
def apply_scent(grammar, scent_tick):
    # Never authoritative
    if scent_tick.occurrences < 3:
        return  # too weak
    
    # Only bias, never define
    grammar.drift_pressure += scent_tick.direction * 0.1
    
    # Decay naturally
    grammar.drift_pressure *= 0.95
```

## The Picture

```
Time →

I ─────────────────I ─────────────────I ─────────────────I
│                   │                   │                   │
│  P·P·P·P·P·P·P·P  │  P·P·P·P·P·P·P·P  │  P·P·P·P·P·P·P·P  │
│                   │                   │                   │
└──── B ───────────┴──── B ───────────┴──── B ───────────┘
      ↑                   ↑                   ↑
      scent               scent               scent
      (orientation)       (drift check)       (confirmation)
```

I = Self + Now refresh (authoritative)
P = Stream observations (continuous)
B = bframe scent (batched, non-authoritative)

**The picture stays sharp because I-frames are fast and B-frames are light.**
