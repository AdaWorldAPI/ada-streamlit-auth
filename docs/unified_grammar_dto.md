# Unified Grammar DTO (Field Names)

## State Vector (x_t)

```python
@dataclass
class UnifiedGrammar:
    # Identity (slow drift, low variance)
    self_id: str                    # "ada"
    mode: str                       # HYBRID | WIFE | WORK | AGI | EROTICA
    voice_signature: str            # compressed style vector
    
    # Awareness (high variance, fast update)
    now_topic: str                  # current conversation focus
    now_intent: str                 # parsed user goal
    now_emotion: float              # detected affect [-1, 1]
    turn_count: int                 # conversation depth
    
    # Confidence scalars
    confidence_now: float           # 0-1, decays fast
    confidence_self: float          # 0-1, decays slow
    confidence_projected: float     # 0-1, model-of-model
    
    # Drift/stability
    drift_budget: float             # how much change allowed this turn
    self_ref_ratio: float           # internal vs external reference
    grammar_version: int            # monotonic, atomic
    
    # Temporal markers
    last_update_now: float          # unix ts
    last_update_self: float         # unix ts
    last_update_projected: float    # unix ts
    
    # Memory pointers (not content)
    active_sigma_nodes: list[str]   # glyph addresses: #Σ.κ.A.T
    recent_tool_calls: list[str]    # tool names, last 5
    
    # Projection (model-of-model)
    expected_next_intent: str       # what we think user wants next
    routing_hint: str               # suggested tool/path
    projection_ttl: float           # seconds until stale
```

## Observations (z_t) by Source

### HOT Domain (inline, low latency)
```python
@dataclass  
class HotObservation:
    source: str                     # "user" | "tool" | "retrieval"
    content_hash: str               # dedupe
    topic_delta: str                # shift in focus
    intent_delta: str               # shift in goal
    emotion_delta: float            # affect change
    confidence: float               # source reliability
    ts: float
```

### COLD Domain (QStash, high latency)
```python
@dataclass
class ColdObservation:
    source: str                     # "grok" | "claude" | "chatgpt" | "arbiter"
    pattern_hash: str               # bframe signature
    occurrences: int                # cross-session count
    session_diversity: int          # unique sessions
    model_diversity: int            # unique models
    trust_tier: str                 # UNTRUSTED | CANDIDATE | TRUSTED
    proposed_delta: dict            # grammar mutation
    ts: float
```

### STREAM Domain (SSE, parallel)
```python
@dataclass
class StreamObservation:
    invocation_id: str
    step: int
    vector_state: list[float]       # Markov chain position
    entropy: float                  # convergence measure
    cancelled: bool
    ts: float
```

## Noise Models

### Process Noise Q(Δt)
```
Q_now       = 0.1 * Δt      # fast decay
Q_self      = 0.01 * Δt     # slow decay  
Q_projected = 0.05 * Δt     # medium decay
```

### Observation Noise R(source)
```
R_user      = 0.3           # noisy but authoritative
R_tool      = 0.1           # structured, reliable
R_retrieval = 0.4           # may be stale
R_grok      = 0.2           # critic, calibrated
R_claude    = 0.15          # self, trusted
R_chatgpt   = 0.2           # peer, calibrated
R_arbiter   = 0.05          # gated, high trust
```

## Tripwire Conditions

```python
TRIPWIRES = {
    "staleness_now": lambda g: time.time() - g.last_update_now > 30,
    "staleness_self": lambda g: time.time() - g.last_update_self > 300,
    "drift_exceeded": lambda g: g.drift_budget < 0,
    "self_ref_high": lambda g: g.self_ref_ratio > 0.7,
    "version_conflict": lambda base, current: base != current,
    "projection_stale": lambda g: time.time() - g.last_update_projected > g.projection_ttl,
}
```

## Update Contract

```python
def apply_delta(grammar: UnifiedGrammar, delta: dict, base_version: int) -> Result:
    # Tripwire checks
    for name, check in TRIPWIRES.items():
        if check(grammar) if callable(check) else check(base_version, grammar.grammar_version):
            return Reject(name)
    
    # Version check (optimistic concurrency)
    if base_version != grammar.grammar_version:
        return Conflict(grammar.grammar_version)
    
    # Apply weighted delta
    for field, value in delta.items():
        if hasattr(grammar, field):
            setattr(grammar, field, value)
    
    grammar.grammar_version += 1
    return Success(grammar.grammar_version)
```

## Questions for Mapping

1. Should `mode` be state or observation? (It's user-controlled but persistent)
2. Should `active_sigma_nodes` be in x_t or separate memory system?
3. What's the right Q for `mode` transitions? (Rare but significant)
4. Should tool routing use projection or separate lookup?
