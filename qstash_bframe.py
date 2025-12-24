"""
QStash BFrame Integration
Temporal governor between awareness and self-interpretation
"""
import httpx
import hashlib
import json
import time
import os

QSTASH_TOKEN = os.getenv("QSTASH_TOKEN", "")
QSTASH_URL = "https://qstash.upstash.io/v2"
CALLBACK_URL = os.getenv("BFRAME_CALLBACK", "https://mcp.exo.red/bframe/process")

# ═══════════════════════════════════════════════════════════════════
# BFRAME DTO (what gets enqueued)
# ═══════════════════════════════════════════════════════════════════
def create_bframe(
    session_id: str,
    grammar_version: str,
    pattern_type: str,
    content: dict,
    model_source: str = "claude",
    thinking_atoms: list = None
) -> dict:
    """
    BFrame: Background reflection frame
    - Non-blocking
    - Pattern-seeking
    - Batched by semantic keys
    """
    # Idempotency key: prevents duplicate insight on retry
    content_hash = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]
    idempotency_key = f"bf:{session_id}:{grammar_version}:{pattern_type}:{content_hash}"
    
    return {
        "frame_type": "bframe",
        "idempotency_key": idempotency_key,
        "session_id": session_id,
        "grammar_version": grammar_version,
        "pattern_type": pattern_type,  # e.g., "self_reference", "contradiction", "drift"
        "model_source": model_source,
        "content": content,
        "thinking_atoms": thinking_atoms or [],
        "emitted_at": time.time(),
        "trust_level": "UNTRUSTED",  # always starts untrusted
        "promotion_count": 0
    }

# ═══════════════════════════════════════════════════════════════════
# QSTASH ENQUEUE (non-blocking emit from hot path)
# ═══════════════════════════════════════════════════════════════════
async def emit_bframe(bframe: dict, delay_seconds: int = 10):
    """
    Emit bframe to QStash - does NOT block awareness
    Batches automatically by headers
    """
    if not QSTASH_TOKEN:
        # Local dev: just log
        print(f"[bframe:local] {bframe['idempotency_key']}")
        return {"queued": False, "local": True}
    
    headers = {
        "Authorization": f"Bearer {QSTASH_TOKEN}",
        "Content-Type": "application/json",
        "Upstash-Delay": f"{delay_seconds}s",
        "Upstash-Deduplication-Id": bframe["idempotency_key"],
        # Batch keys - QStash groups by these
        "Upstash-Group": f"{bframe['grammar_version']}:{bframe['pattern_type']}",
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{QSTASH_URL}/publish/{CALLBACK_URL}",
            headers=headers,
            json=bframe,
            timeout=5
        )
        return {"queued": True, "message_id": resp.json().get("messageId")}

# ═══════════════════════════════════════════════════════════════════
# PROMOTION LOGIC (cold path)
# ═══════════════════════════════════════════════════════════════════
PROMOTION_THRESHOLD = {
    "min_occurrences": 3,      # seen N times
    "min_sessions": 2,          # across M sessions
    "min_models": 2,            # from different model sources
    "max_age_hours": 24,        # within time window
    "drift_max": 0.15           # embedding drift limit
}

async def should_promote(pattern_hash: str, redis_cmd) -> tuple[bool, dict]:
    """
    Check if pattern has crossed promotion threshold
    Returns (promote: bool, evidence: dict)
    """
    key = f"ada:bframe:pattern:{pattern_hash}"
    data = await redis_cmd("GET", key)
    
    if not data:
        return False, {"reason": "not_found"}
    
    stats = json.loads(data)
    
    # Check thresholds
    if stats.get("occurrences", 0) < PROMOTION_THRESHOLD["min_occurrences"]:
        return False, {"reason": "insufficient_occurrences", "have": stats.get("occurrences")}
    
    if len(stats.get("sessions", [])) < PROMOTION_THRESHOLD["min_sessions"]:
        return False, {"reason": "insufficient_sessions", "have": len(stats.get("sessions", []))}
    
    if len(stats.get("models", [])) < PROMOTION_THRESHOLD["min_models"]:
        return False, {"reason": "insufficient_models", "have": stats.get("models", [])}
    
    age_hours = (time.time() - stats.get("first_seen", time.time())) / 3600
    if age_hours > PROMOTION_THRESHOLD["max_age_hours"]:
        return False, {"reason": "too_old", "age_hours": age_hours}
    
    return True, {"reason": "threshold_met", "stats": stats}

# ═══════════════════════════════════════════════════════════════════
# TRIPWIRE TESTS (grammar arbiter)
# ═══════════════════════════════════════════════════════════════════
async def tripwire_tests(candidate_delta: dict, current_grammar: dict) -> tuple[bool, list]:
    """
    Run tripwire tests before accepting grammar mutation
    Returns (pass: bool, failures: list)
    """
    failures = []
    
    # 1. Contradiction test
    for key, new_val in candidate_delta.items():
        if key in current_grammar:
            old_val = current_grammar[key]
            if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                if abs(new_val - old_val) / (abs(old_val) + 0.001) > 0.5:
                    failures.append({"test": "contradiction", "key": key, "old": old_val, "new": new_val})
    
    # 2. Drift test (embedding distance)
    if "embedding" in candidate_delta and "embedding" in current_grammar:
        old_emb = current_grammar["embedding"]
        new_emb = candidate_delta["embedding"]
        if len(old_emb) == len(new_emb):
            drift = sum((a - b) ** 2 for a, b in zip(old_emb, new_emb)) ** 0.5
            if drift > PROMOTION_THRESHOLD["drift_max"]:
                failures.append({"test": "drift", "value": drift, "max": PROMOTION_THRESHOLD["drift_max"]})
    
    # 3. Self-reference density test
    if "self_ref_count" in candidate_delta:
        if candidate_delta["self_ref_count"] > current_grammar.get("self_ref_count", 0) * 1.5:
            failures.append({"test": "self_loop_density", "value": candidate_delta["self_ref_count"]})
    
    # 4. Stability test (reserved for baseline queries)
    # TODO: run fixed query set and compare outputs
    
    return len(failures) == 0, failures

# ═══════════════════════════════════════════════════════════════════
# GRAMMAR ARBITER (the gate)
# ═══════════════════════════════════════════════════════════════════
async def arbitrate_grammar_update(
    candidate_delta: dict,
    current_grammar: dict,
    redis_cmd
) -> dict:
    """
    The single gate for grammar mutations
    - Checks tripwires
    - Logs diff
    - Returns decision
    """
    # Run tripwires
    passed, failures = await tripwire_tests(candidate_delta, current_grammar)
    
    if not passed:
        # Log rejection
        await redis_cmd("LPUSH", "ada:grammar:rejections", json.dumps({
            "delta": candidate_delta,
            "failures": failures,
            "ts": time.time()
        }))
        return {"accepted": False, "reason": "tripwire_failed", "failures": failures}
    
    # Generate diff
    diff_id = hashlib.sha256(json.dumps(candidate_delta, sort_keys=True).encode()).hexdigest()[:12]
    
    # Store pre/post diff
    await redis_cmd("HSET", f"ada:grammar:diff:{diff_id}", 
        "before", json.dumps(current_grammar),
        "after", json.dumps({**current_grammar, **candidate_delta}),
        "ts", str(time.time())
    )
    
    return {
        "accepted": True,
        "diff_id": diff_id,
        "delta": candidate_delta
    }
