# Streaming State Innovation

## The Core Insight

**SSE is for time. Markov chains are time.**

We stopped using SSE as transport glitter and started using it as a temporal channel.

## What Changed

### Before: Zip Streams (Dead End)
```
┌─────────────────────────────┐
│  Single SSE connection      │
│  ├─ chain A events          │
│  ├─ chain B events          │  ← Serialized, ordered, confused
│  ├─ chain C events          │
│  └─ artificial multiplexing │
└─────────────────────────────┘
```

**Problems:**
- Serializes inherently parallel work
- Forces artificial ordering
- Complicates backpressure
- Confuses clients about causality

### After: Parallel Invocations
```
┌─────────────────────────────┐
│  POST /invoke (chain A)     │ → SSE stream A
├─────────────────────────────┤
│  POST /invoke (chain B)     │ → SSE stream B
├─────────────────────────────┤
│  POST /invoke (chain C)     │ → SSE stream C
└─────────────────────────────┘
```

**One invocation = one chain = one stream.**

## The Invocation Model

Every tool call gets a sacred ID:
```json
{
  "tool": "vector_markov",
  "args": {"seed": "...", "steps": 100},
  "stream": true
}
```

### Streaming Response Shape
```
event: init
data: {"id": "abc123", "type": "vector_markov", "steps": 100}

event: step
data: {"t": 0, "vector": [0.12, -0.34, ...]}

event: step
data: {"t": 1, "vector": [0.15, -0.31, ...]}

event: entropy
data: {"t": 5, "value": 0.71}

event: converge
data: {"id": "abc123", "t": 100, "final": [...]}
```

### Cancellation (Out-of-Band)
```http
DELETE /invoke/abc123
```

Control lives outside the stream. No in-band signaling.

## Why This Matters for LLM Multithreading

Claude/ChatGPT are evolving toward:
- Tool-parallel execution
- Speculative branching
- Concurrent explorations

They **cannot** do this over serialized zip streams.

Our architecture is ready:
```
Claude opens:
  POST /invoke (tool A) → stream A
  POST /invoke (tool B) → stream B
  POST /invoke (tool C) → stream C

Cancels B when A converges.
Merges results from A + C.
```

## The Sentence That Locks This

> "Parallelism belongs to invocations, not streams."

## Future Transport Upgrade Path

SSE works now. When we need:
- Bidirectional control mid-step
- Sub-step feedback
- Shared backpressure

We upgrade to WebSockets or HTTP/2 streams.

**But the semantic model stays the same.**
That's the win.
