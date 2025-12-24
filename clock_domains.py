"""
Clock Domains & Kalman-Lite Implementation
Temporal de-interlacing for awareness architecture
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any
import time
import hashlib
import json
import uuid

# ═══════════════════════════════════════════════════════════════════
# CLOCK DOMAINS (First-Class Types)
# ═══════════════════════════════════════════════════════════════════

class ClockDomain(Enum):
    HOT = "hot"        # Now/Self/Projected → grammar delta (inline)
    COLD = "cold"      # bframes → reflection → arbiter (QStash)
    STREAM = "stream"  # SSE Markov chains (parallel)

class EventType(Enum):
    USER_TURN = "user_turn"
    TOOL_RESULT = "tool_result"
    RETRIEVAL = "retrieval"
    REFLECTION = "reflection"
    MARKOV_STEP = "markov_step"
    ARBITER_DECISION = "arbiter_decision"
    GRAMMAR_UPDATE = "grammar_update"

class TrustTier(Enum):
    UNTRUSTED = "untrusted"
    CANDIDATE = "candidate"
    TRUSTED = "trusted"
    DISFAVORED = "disfavored"

class ModelSource(Enum):
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    GROK = "grok"
    SYSTEM = "system"

# ═══════════════════════════════════════════════════════════════════
# EVENT HEADER CONTRACT (Non-Negotiable)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class EventHeader:
    """Every event must carry this header - the GPS timestamp + satellite ID"""
    event_id: str
    domain: ClockDomain
    event_type: EventType
    ts: float
    grammar_base_version: int
    session_id: str
    source: ModelSource
    confidence: float
    idempotency_key: str
    
    @classmethod
    def create(cls, domain: ClockDomain, event_type: EventType, 
               grammar_version: int, session_id: str, 
               source: ModelSource, confidence: float,
               payload: Any = None):
        event_id = str(uuid.uuid4())
        ts = time.time()
        
        # Idempotency key from content hash
        content = json.dumps({
            "domain": domain.value,
            "event_type": event_type.value,
            "grammar_version": grammar_version,
            "session_id": session_id,
            "payload": str(payload)
        }, sort_keys=True)
        idempotency_key = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        return cls(
            event_id=event_id,
            domain=domain,
            event_type=event_type,
            ts=ts,
            grammar_base_version=grammar_version,
            session_id=session_id,
            source=source,
            confidence=confidence,
            idempotency_key=idempotency_key
        )
    
    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "domain": self.domain.value,
            "event_type": self.event_type.value,
            "ts": self.ts,
            "grammar_base_version": self.grammar_base_version,
            "session_id": self.session_id,
            "source": self.source.value,
            "confidence": self.confidence,
            "idempotency_key": self.idempotency_key
        }

# ═══════════════════════════════════════════════════════════════════
# KALMAN-LITE (80% of value, 20% of complexity)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class DomainState:
    """Uncertainty state for a single clock domain"""
    uncertainty: float
    last_update: float
    decay_rate: float
    
    def get_staleness(self) -> float:
        return time.time() - self.last_update
    
    def get_current_uncertainty(self) -> float:
        """Uncertainty grows with staleness"""
        staleness = self.get_staleness()
        return self.uncertainty * (1 + self.decay_rate * staleness)
    
    def get_weight(self) -> float:
        """Weight is inverse of uncertainty"""
        return 1.0 / (self.get_current_uncertainty() + 0.001)
    
    def update(self, new_uncertainty: Optional[float] = None):
        """Record fresh observation"""
        self.last_update = time.time()
        if new_uncertainty is not None:
            self.uncertainty = new_uncertainty
        else:
            # Reduce uncertainty after observation
            self.uncertainty *= 0.8

class KalmanLite:
    """
    Scalar Kalman filter for time de-interlacing.
    
    Key insight: You're not forcing one timeline.
    You're weighting updates by trust + staleness.
    """
    
    def __init__(self):
        self.domains = {
            "now": DomainState(uncertainty=1.0, last_update=time.time(), decay_rate=0.1),
            "self": DomainState(uncertainty=0.2, last_update=time.time(), decay_rate=0.01),
            "projected": DomainState(uncertainty=0.5, last_update=time.time(), decay_rate=0.05),
        }
        self.grammar_version = 0
    
    def get_staleness_metrics(self) -> dict:
        return {name: d.get_staleness() for name, d in self.domains.items()}
    
    def get_weights(self) -> dict:
        return {name: d.get_weight() for name, d in self.domains.items()}
    
    def merge_deltas(self, deltas: dict[str, dict]) -> dict:
        """
        Weighted merge of deltas from different domains.
        
        Numeric values: weighted average
        Non-numeric: take from highest-weight domain
        """
        weights = {d: self.domains[d].get_weight() for d in deltas if d in self.domains}
        total_weight = sum(weights.values()) or 1.0
        
        merged = {}
        highest_weight_domain = max(weights, key=weights.get) if weights else None
        
        for domain, delta in deltas.items():
            if domain not in weights:
                continue
            w = weights[domain] / total_weight
            
            for key, value in delta.items():
                if isinstance(value, (int, float)):
                    merged[key] = merged.get(key, 0) + w * value
                elif domain == highest_weight_domain:
                    merged[key] = value
        
        return merged
    
    def update(self, domain: str, observation: dict):
        """Record observation from a domain"""
        if domain in self.domains:
            self.domains[domain].update()
    
    def apply_delta(self, base_version: int, delta: dict) -> tuple[bool, int]:
        """
        Optimistic concurrency control for grammar updates.
        
        Returns: (success, new_version or current_version)
        """
        if base_version != self.grammar_version:
            return False, self.grammar_version
        
        self.grammar_version += 1
        return True, self.grammar_version

# ═══════════════════════════════════════════════════════════════════
# ARBITER GATES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ArbiterDecision:
    action: str  # "accept", "reject", "defer"
    reason: str
    evidence: dict = field(default_factory=dict)

class Arbiter:
    """
    The single gate for grammar mutations.
    No cold-path output may mutate hot-path state without passing here.
    """
    
    MAX_STALENESS = 30.0  # seconds
    MAX_SELF_REF_RATIO = 0.7
    QUARANTINE_WINDOW = 5  # grammar versions
    
    def __init__(self, kalman: KalmanLite):
        self.kalman = kalman
    
    def self_reference_ratio(self, delta: dict) -> float:
        """Fraction of content referencing internal state"""
        internal_keywords = ["self", "grammar", "state", "awareness", "thinking", "reflecting"]
        
        text = json.dumps(delta).lower()
        total_words = len(text.split())
        internal_count = sum(text.count(kw) for kw in internal_keywords)
        
        return internal_count / (total_words + 1)
    
    def check_staleness(self) -> Optional[ArbiterDecision]:
        """Gate: reject if now vector is too stale"""
        staleness = self.kalman.get_staleness_metrics()
        if staleness.get("now", 0) > self.MAX_STALENESS:
            return ArbiterDecision(
                action="defer",
                reason="now vector too stale",
                evidence={"staleness": staleness}
            )
        return None
    
    def check_self_reference(self, delta: dict) -> Optional[ArbiterDecision]:
        """Gate: reject if self-reference ratio too high"""
        ratio = self.self_reference_ratio(delta)
        if ratio > self.MAX_SELF_REF_RATIO:
            return ArbiterDecision(
                action="reject",
                reason="self-reference ratio too high",
                evidence={"ratio": ratio, "max": self.MAX_SELF_REF_RATIO}
            )
        return None
    
    def check_quarantine(self, bframe_version: int) -> Optional[ArbiterDecision]:
        """Gate: bframes can only observe versions ≤ current - N"""
        current = self.kalman.grammar_version
        if bframe_version > current - self.QUARANTINE_WINDOW:
            return ArbiterDecision(
                action="reject",
                reason="bframe too recent (quarantine)",
                evidence={"bframe_version": bframe_version, "current": current}
            )
        return None
    
    def evaluate(self, proposal: dict, source_version: int, is_bframe: bool = False) -> ArbiterDecision:
        """Run all gates, return decision"""
        
        # Staleness gate
        staleness_check = self.check_staleness()
        if staleness_check:
            return staleness_check
        
        # Self-reference gate
        self_ref_check = self.check_self_reference(proposal)
        if self_ref_check:
            return self_ref_check
        
        # Quarantine gate (bframes only)
        if is_bframe:
            quarantine_check = self.check_quarantine(source_version)
            if quarantine_check:
                return quarantine_check
        
        return ArbiterDecision(
            action="accept",
            reason="all gates passed",
            evidence={
                "staleness": self.kalman.get_staleness_metrics(),
                "self_ref_ratio": self.self_reference_ratio(proposal)
            }
        )

# ═══════════════════════════════════════════════════════════════════
# QSTASH DOMAIN GATE
# ═══════════════════════════════════════════════════════════════════

def validate_qstash_event(header: EventHeader) -> bool:
    """
    HOT events cannot go through QStash.
    This one rule prevents feedback loops from becoming a blender.
    """
    if header.domain == ClockDomain.HOT:
        raise ValueError(f"HOT events cannot go through QStash: {header.event_id}")
    return True

# ═══════════════════════════════════════════════════════════════════
# ADMISSION CONTROL (Parallel Streams)
# ═══════════════════════════════════════════════════════════════════

class AdmissionControl:
    """Prevent SSE overload"""
    
    MAX_PER_CLIENT = 5
    MAX_TOTAL = 100
    
    def __init__(self):
        self.streams: dict[str, set] = {}  # client_id -> set of stream_ids
    
    def count_client(self, client_id: str) -> int:
        return len(self.streams.get(client_id, set()))
    
    def count_total(self) -> int:
        return sum(len(s) for s in self.streams.values())
    
    def can_start(self, client_id: str) -> bool:
        return (self.count_client(client_id) < self.MAX_PER_CLIENT and
                self.count_total() < self.MAX_TOTAL)
    
    def register(self, client_id: str, stream_id: str) -> bool:
        if not self.can_start(client_id):
            return False
        if client_id not in self.streams:
            self.streams[client_id] = set()
        self.streams[client_id].add(stream_id)
        return True
    
    def release(self, client_id: str, stream_id: str):
        if client_id in self.streams:
            self.streams[client_id].discard(stream_id)

# ═══════════════════════════════════════════════════════════════════
# PROJECTION WITH TTL
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Projection:
    """Model-of-model with confidence and TTL"""
    belief: dict
    confidence: float
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 60.0
    
    def is_valid(self) -> bool:
        return time.time() - self.created_at < self.ttl_seconds
    
    def get_routing(self, conservative_default: dict = None) -> dict:
        if not self.is_valid():
            return conservative_default or {"strategy": "conservative"}
        return self.belief

# ═══════════════════════════════════════════════════════════════════
# USAGE EXAMPLE
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Initialize
    kalman = KalmanLite()
    arbiter = Arbiter(kalman)
    admission = AdmissionControl()
    
    # Simulate updates from different domains
    kalman.update("now", {"turn": 1, "content": "hello"})
    kalman.update("self", {"identity": "ada"})
    
    # Merge deltas with uncertainty weighting
    deltas = {
        "now": {"confidence": 0.8, "topic": "greeting"},
        "self": {"confidence": 0.95, "mode": "friendly"},
        "projected": {"confidence": 0.6, "expectation": "question"}
    }
    merged = kalman.merge_deltas(deltas)
    print(f"Merged delta: {merged}")
    print(f"Weights: {kalman.get_weights()}")
    
    # Arbiter evaluation
    proposal = {"update": "new_topic", "self_grammar": "modified"}
    decision = arbiter.evaluate(proposal, source_version=0)
    print(f"Arbiter decision: {decision}")
    
    # Stream admission
    print(f"Can start stream: {admission.can_start('client_1')}")
    admission.register("client_1", "stream_1")
    print(f"Streams for client_1: {admission.count_client('client_1')}")
