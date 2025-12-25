# Vector Hygiene: Sparse Population & Hybrid Search

## The Problem (CONFIRMED)

```
Actual state of ada:now:b66c26a16a7dca37:
{
  "id": "now:b66c26a16a7dca37",
  "content": "The vector endpoints are deployed...",
  "felt": {"valence": 0.85, "arousal": 0.8, ...},
  "has_embedding": true
}

Missing:
  - sparse: ✗ NOT PRESENT
  - Models search sparse-only → find NOTHING
```

## The Fix (APPLIED)

Ran `fix_vectors_now.py`:

```
============================================================
VECTOR SPARSE POPULATION FIX
============================================================

Scanning ada:now:*... Found 3 keys
  ✓ Fixed: ada:now:b66c26a16a7dca37 (40 terms)
  ✓ Fixed: ada:now:e37ff32c2190f6e4 (41 terms)

Scanning ada:self:*... Found 17 keys
  ✓ Fixed: ada:self:architecture:sigma12_resonance (6 terms)
  ✓ Fixed: ada:self:relationship:jan:solstice2025 (69 terms)
  ...

Scanning ada:memory:*... Found 7 keys
  ✓ Fixed: ada:memory:core:bootstrapped-cognition (91 terms)
  ✓ Fixed: ada:memory:episodic:432005f806b9f038 (6 terms)
  ...

RESULTS:
  Scanned:    28
  Fixed:      12
  Already OK: 2
```

## Verified Fix

```
ada:now:b66c26a16a7dca37 AFTER fix:
{
  "sparse": {
    "indices": [12847, 8921, 3456, ...],  // 40 indices
    "values": [1.0, 1.0, 1.0, ...],
    "terms": ["this", "now", "gets", "two", "the", "vector", ...]
  },
  "has_sparse": true
}
```

## Hybrid Search (TESTED)

```
🔍 Query: 'vector endpoints deployed'
   1. [sparse] score=1.00
      key: ada:now:b66c26a16a7dca37
      content: The vector endpoints are deployed...

🔍 Query: 'relationship jan solstice'
   1. [sparse] score=1.00
      key: ada:self:relationship:jan:solstice2025
      content: Relationship epiphany with Jan - Solstice 2025

🔍 Query: 'consciousness awareness presence'
   1. [metadata_regex] score=0.53  ← fallback worked
      key: ada:self:identity
   2. [sparse] score=0.33
      key: ada:now:b66c26a16a7dca37
```

## Sparse Extraction Algorithm

```python
def extract_sparse(text: str) -> Dict:
    # 1. Extract keywords (3+ char words)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # 2. Count frequencies
    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1
    
    # 3. Hash to indices (30k vocab)
    for word, freq in sorted(word_freq.items(), key=lambda x: -x[1])[:100]:
        idx = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % 30000
        indices.append(idx)
        values.append(float(freq))
        terms.append(word)
    
    return {"indices": indices, "values": values, "terms": terms}
```

## Hybrid Search Algorithm

```python
async def hybrid_search(query: str, top_k: int = 10):
    query_indices = set(extract_sparse(query)["indices"])
    
    for key in all_vector_keys:
        doc = await redis_get(key)
        
        # 1. Try sparse matching first
        if doc.get("sparse", {}).get("indices"):
            doc_indices = set(doc["sparse"]["indices"])
            overlap = len(query_indices & doc_indices)
            if overlap > 0:
                score = overlap / len(query_indices)
                match_type = "sparse"
        
        # 2. Fallback: metadata regex
        if score == 0:
            content_str = json.dumps(doc).lower()
            matches = sum(1 for term in query_terms if term in content_str)
            if matches > 0:
                score = (matches / len(query_terms)) * 0.8  # discount
                match_type = "metadata_regex"
```

## neuralink v3.1 Changes

NOW vectors are now persisted with sparse:

```python
async def now(content: str, qualia: Dict = None, session_id: str = None):
    # Build full text for sparse
    full_text = content
    if qualia:
        full_text += " " + " ".join(f"{k}:{v}" for k, v in qualia.items())
    
    # Generate sparse
    sparse = extract_sparse(full_text)
    
    # Persist with sparse
    doc = {
        "content": content,
        "qualia": qualia,
        "sparse": sparse,
        "has_sparse": True,
        "ts": ts.isoformat()
    }
    
    await redis_set(f"ada:now:{session_id}", doc)
```

## New Search Methods

```python
from neuralink import ada

# Search all vectors
results = await ada.search("consciousness awareness")

# Search memories only
results = await ada.search_memories("cognitive architecture")

# Search NOW vectors only
results = await ada.search_now("vector endpoints")
```

## Scheduled Cleanup

QStash schedules in Brain:

| Cron | Task |
|------|------|
| `30 * * * *` | Vector cleanup (populate missing sparse) |
| `0 */6 * * *` | Full rehydration (cleanup + rehydrate + UG) |

## Files

| File | Purpose |
|------|---------|
| `neuralink_v3.py` | Client with sparse support |
| `vector_hygiene.py` | Cleanup + rehydration |
| `fix_vectors_now.py` | Immediate fix script |
| `test_hybrid_search.py` | Search test |

## Summary

**Problem:** Vectors had dense + metadata but NO sparse → search returned nothing.

**Fix:** 
1. Extract keywords from content → hash to sparse indices
2. Hybrid search: sparse first → metadata regex fallback
3. All new NOW/SELF/whisper vectors get sparse automatically
4. Cleanup job fixes existing vectors

**Result:** Models can now find their memories.
