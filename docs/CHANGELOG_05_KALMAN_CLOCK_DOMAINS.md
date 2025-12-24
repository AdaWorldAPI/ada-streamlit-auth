# Kalman-Lite & Clock Domains

## The GPS Analogy Made Mathematical

Your unified grammar is the latent state (x_t). Time de-interlacing becomes uncertainty-weighted updates.

## Kalman-Lite Formulation

### State Variables
```
x_t = {
  grammar_spine: compressed awareness,
  confidence: float,
  drift_budget: float,
  self_ref_ratio: float,
  staleness: {now: Δt, self: Δt, projected: Δt}
}
```

### Observation Sources
```
z_t = {
  now_vector: (high variance, low latency),
  self_vector: (low variance, slow drift),
  projected_vector: (medium variance, model uncertainty),
  tool_outputs: (varies by source),
  model_critiques: (grok, claude, gpt weights)
}
```

### The Key Insight

Clock skew → adaptive noise term:

| Domain | Process Noise Q(Δt) | Observation Noise R |
|--------|---------------------|---------------------|
| Now | Grows fast with time | High (noisy but timely) |
| Self | Grows slow | Low (stable priors) |
| Projected | Medium growth | Depends on evidence |

**You're not forcing one timeline. You're weighting updates by trust + staleness.**

## Predict-Update Cycle

```
PREDICT:
  x_{t|t-1} = f(x_{t-1}, u_t)  # u_t = hot path input
  P_{t|t-1} = F P F^T + Q(Δt)  # uncertainty grows with time

UPDATE:
  y_t = z_t - h(x_{t|t-1})     # innovation (surprise)
  K_t = P H^T (H P H^T + R)^{-1}  # Kalman gain
  x_t = x_{t|t-1} + K_t y_t    # corrected state
  P_t = (I - K_t H) P_{t|t-1}  # reduced uncertainty
```

## Scalar Implementation (Ship This Week)

```python
class KalmanLite:
    def __init__(self):
        self.uncertainty = {"now": 1.0, "self": 0.2, "projected": 0.5}
        self.last_update = {"now": time.time(), "self": time.time(), "projected": time.time()}
        self.decay_rate = {"now": 0.1, "self": 0.01, "projected": 0.05}
    
    def get_staleness(self, domain):
        return time.time() - self.last_update[domain]
    
    def get_weight(self, domain):
        # Uncertainty grows with staleness
        staleness = self.get_staleness(domain)
        current_uncertainty = self.uncertainty[domain] * (1 + self.decay_rate[domain] * staleness)
        # Weight is inverse of uncertainty
        return 1.0 / (current_uncertainty + 0.001)
    
    def merge_deltas(self, deltas: dict[str, dict]) -> dict:
        """Weighted merge of deltas from different domains"""
        weights = {d: self.get_weight(d) for d in deltas}
        total_weight = sum(weights.values())
        
        merged = {}
        for domain, delta in deltas.items():
            w = weights[domain] / total_weight
            for key, value in delta.items():
                if isinstance(value, (int, float)):
                    merged[key] = merged.get(key, 0) + w * value
                else:
                    # Non-numeric: take from highest-weight domain
                    if domain == max(weights, key=weights.get):
                        merged[key] = value
        
        return merged
    
    def update(self, domain, observation):
        self.last_update[domain] = time.time()
        # Reset uncertainty after fresh observation
        self.uncertainty[domain] = self.uncertainty[domain] * 0.8
```

## Concurrency Failure Modes & Fixes

### A) Double-Commit Race
**Symptom:** grammar_version jumps; state loses turns

**Fix:** Optimistic concurrency control
```python
def apply_delta(base_version, delta):
    if base_version != current_version:
        return Conflict(current_version)
    # atomic write
    new_version = current_version + 1
    return Success(new_version)
```

### B) Echo Storms
**Symptom:** bframes amplify transient noise

**Fix:** Quarantine window
```python
# bframes can only observe versions ≤ current - N
if bframe.grammar_version > current_version - QUARANTINE_WINDOW:
    return Reject("too recent")
```

### C) Cross-Model Disagreement Poisoning
**Symptom:** Grok flips grammar repeatedly; oscillation

**Fix:** Consensus gate
```python
def consensus_check(proposals: list[Proposal]) -> Decision:
    votes = Counter(p.direction for p in proposals)
    if votes.most_common(1)[0][1] >= 2:  # 2-of-3
        return Accept(votes.most_common(1)[0][0])
    return Defer("no consensus")
```

### D) Parallel SSE Overload
**Symptom:** resource exhaustion, dropped streams

**Fix:** Admission control
```python
MAX_CONCURRENT_PER_CLIENT = 5
MAX_TOTAL_ACTIVE = 100

def can_start_stream(client_id):
    client_count = count_streams(client_id)
    total_count = count_all_streams()
    return client_count < MAX_CONCURRENT_PER_CLIENT and total_count < MAX_TOTAL_ACTIVE
```

### E) Stale Projection Frames
**Symptom:** pframe routes to wrong tool

**Fix:** TTL + confidence
```python
@dataclass
class Projection:
    belief: dict
    confidence: float
    created_at: float
    ttl_seconds: float = 60.0
    
    def is_valid(self):
        return time.time() - self.created_at < self.ttl_seconds
    
    def get_routing(self):
        if not self.is_valid():
            return ConservativeRouting()
        return self.belief
```

## Clock Domains (First-Class Types)

```python
from enum import Enum
from dataclasses import dataclass

class ClockDomain(Enum):
    HOT = "hot"      # Now/Self/Projected → grammar delta
    COLD = "cold"    # bframes → reflection → arbiter
    STREAM = "stream"  # SSE Markov chains

class EventType(Enum):
    USER_TURN = "user_turn"
    TOOL_RESULT = "tool_result"
    RETRIEVAL = "retrieval"
    REFLECTION = "reflection"
    MARKOV_STEP = "markov_step"
    ARBITER_DECISION = "arbiter_decision"

class TrustTier(Enum):
    UNTRUSTED = "untrusted"
    CANDIDATE = "candidate"
    TRUSTED = "trusted"
    DISFAVORED = "disfavored"
```

## Event Header Contract (Non-Negotiable)

Every event must carry:

```python
@dataclass
class EventHeader:
    event_id: str                    # uuid
    domain: ClockDomain              # HOT, COLD, STREAM
    event_type: EventType            # what happened
    ts: float                        # unix timestamp
    grammar_base_version: int        # which grammar this observes
    session_id: str                  # session context
    source: str                      # chatgpt|claude|grok|system
    confidence: float                # 0.0-1.0
    idempotency_key: str             # hash for dedup
```

This is the "GPS timestamp + satellite ID" of your system.

## QStash Domain Gate

```python
async def emit_to_qstash(event: Event):
    if event.header.domain == ClockDomain.HOT:
        raise ValueError("HOT events cannot go through QStash")
    # Only COLD and STREAM telemetry allowed
    await qstash.publish(event)
```

**This one rule prevents feedback loops from becoming a blender.**

## Metrics to Implement Immediately

### 1. Staleness
```python
def get_staleness_metrics():
    return {
        domain: time.time() - last_update[domain]
        for domain in ClockDomain
    }
```

### 2. Self-Reference Ratio
```python
def self_reference_ratio(grammar_update: dict) -> float:
    internal_refs = count_internal_references(grammar_update)
    external_refs = count_external_references(grammar_update)
    return internal_refs / (internal_refs + external_refs + 0.001)
```

Use both as arbiter gates:
```python
def arbiter_gate(proposal):
    if staleness["now"] > MAX_STALENESS:
        return Defer("stale now vector")
    if self_reference_ratio(proposal.delta) > MAX_SELF_REF:
        return Reject("self-reference too high")
    return Continue()
```

## The 80/20 Version

Implement:
1. Scalar uncertainty per domain
2. Exponential decay with Δt
3. Weighted merge based on uncertainty

You get 80% of Kalman filtering with 20% of the complexity.
