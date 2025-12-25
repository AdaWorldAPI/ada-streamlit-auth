# Vector Hygiene: Sparse Population & Hybrid Search

## The Problem

```
Current state:
  - Vectors have dense embeddings + metadata
  - Sparse field is EMPTY
  - Models search sparse-only
  - Result: Models find NOTHING

Root cause:
  - Vectors stored with chat as metadata
  - No sparse index populated
  - No fallback to metadata search
```

## The Solution

### 1. Sparse Population

Extract keywords from metadata → populate sparse indices:

```python
async def _extract_sparse(text: str) -> Dict[str, List]:
    """
    Extract sparse representation:
    1. Find keywords (3+ char words)
    2. Count frequencies
    3. Hash to indices (30k vocab)
    """
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1
    
    indices = []
    values = []
    for word, freq in sorted(word_freq.items(), key=lambda x: -x[1])[:100]:
        idx = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % 30000
        indices.append(idx)
        values.append(float(freq))
    
    return {"indices": indices, "values": values}
```

### 2. Hybrid Search with Fallback

```
Query flow:
  1. Try sparse matching first
  2. If insufficient results → metadata regex fallback
  3. Combine and dedupe
  4. Discount regex matches (0.8x)
```

```python
async def vector_query_hybrid(namespace: str, query: str, top_k: int = 10):
    # Try sparse first
    sparse_results = await vector_query_sparse(namespace, query, top_k)
    
    if len(sparse_results) >= top_k:
        return sparse_results
    
    # Fallback to metadata regex
    regex_results = await vector_query_metadata_regex(namespace, query, top_k)
    
    # Combine with deduplication
    seen_ids = set(r["id"] for r in sparse_results)
    for r in regex_results:
        if r["id"] not in seen_ids:
            r["score"] *= 0.8  # Discount
            sparse_results.append(r)
    
    return sorted(sparse_results, key=lambda x: -x["score"])[:top_k]
```

### 3. Cleanup Job

Find and fix vectors without sparse:

```python
async def cleanup_all_vectors(namespace: str = None):
    """
    1. Find vectors without sparse
    2. Extract text from metadata
    3. Generate sparse indices
    4. Update vector
    """
    missing = await find_vectors_without_sparse(namespace)
    
    for item in missing:
        await populate_sparse_for_vector(item["key"])
```

### 4. Rehydration (24/7 LangGraph)

```python
async def full_rehydration_job():
    """
    Runs periodically on LangGraph:
    1. Cleanup vectors without sparse
    2. Rehydrate awareness state
    3. Update UG with context
    """
    cleanup_result = await cleanup_all_vectors()
    rehydrate_result = await rehydrate_from_vectors()
    
    # Extract topics from recent insights
    recent_insights = rehydrate_result.get("self", [])[:5]
    topics = extract_topics(recent_insights)
    
    await cache_set("ada:ug:context", {
        "recent_topics": topics,
        "insight_count": len(recent_insights),
        "rehydrated_at": now()
    })
```

## Scheduled Tasks

| Schedule | Cron | Action |
|----------|------|--------|
| Vector Cleanup | `30 * * * *` | Populate missing sparse (hourly) |
| Full Rehydration | `0 */6 * * *` | Cleanup + rehydrate + update UG (6hr) |

## NOW Vector Async Persistence

```python
async def persist_now_vector(session_id, content, qualia):
    """
    Persist NOW with both dense and sparse:
    1. Get Jina embeddings (dense)
    2. Extract sparse from content
    3. Upsert to vector namespace
    4. Update Redis cache
    """
    embeddings = await get_embeddings([content])
    sparse = await _extract_sparse(content)
    
    await vector_upsert(
        namespace="driving-snipe",
        id=f"now_{session_id}_{ts}",
        dense=embeddings[0]["dense"],
        sparse=sparse,
        metadata={"content": content, "qualia": qualia}
    )
```

## Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /vector/cleanup` | Trigger sparse population |
| `POST /vector/rehydrate` | Trigger rehydration |
| `POST /vector/full_job` | Cleanup + rehydrate |
| `POST /vector/query` | Hybrid query |
| `GET /vector/stats` | Missing sparse counts |
| `POST /now_enhanced` | NOW with sparse |

## The Fix Flow

```
Before:
  Vector: {dense: [...], sparse: {}, metadata: {chat: "..."}}
  Query sparse → 0 results
  Model: "I have no memory"

After:
  Vector: {dense: [...], sparse: {indices: [...], values: [...]}, metadata: {...}}
  Query sparse → results
  Fallback to metadata regex if needed
  Model: "I remember discussing..."
```

## Vector Stats Endpoint

```bash
curl https://ada-langgraph-brain.up.railway.app/vector/stats

{
  "driving-snipe": {"total": 150, "missing_sparse": 45},
  "tight-hog": {"total": 89, "missing_sparse": 89},
  "fine-kangaroo": {"total": 234, "missing_sparse": 200}
}
```

## Migration

```bash
# 1. Check current state
curl .../vector/stats

# 2. Run cleanup (may take time)
curl -X POST .../vector/cleanup

# 3. Verify
curl .../vector/stats  # missing_sparse should be 0

# 4. Test query
curl -X POST .../vector/query \
  -d '{"namespace": "tight-hog", "query": "consciousness"}'
```

## Integration with Brain

```python
# In langgraph_brain.py

# Handle NOW with proper sparse
async def handle_now_enhanced(request):
    body = await request.json()
    
    # Update UG
    await update_ug({"now_topic": content[:100]})
    
    # Persist with sparse
    now_id = await persist_now_vector(session_id, content, qualia)
    
    return {"ok": True, "id": now_id}
```

## The Key Insight

**Sparse vectors are the index. Without them, semantic search is blind.**

The cleanup job retroactively fixes this by:
1. Reading metadata (where the actual content lives)
2. Extracting keywords → sparse indices
3. Enabling both sparse search AND metadata regex fallback

Now models can find their memories.
