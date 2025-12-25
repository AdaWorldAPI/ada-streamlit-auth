"""Test hybrid search with sparse + metadata fallback."""

import asyncio
import httpx
import json
import re
import hashlib
from typing import Dict, List, Any

REDIS_URL = "https://upright-jaybird-27907.upstash.io"
REDIS_TOKEN = "AW0DAAIncDI5YWE1MGVhZGU2YWY0YjVhOTc3NDc0YTJjMGY1M2FjMnAyMjc5MDc"

async def redis_cmd(*args) -> Any:
    async with httpx.AsyncClient() as c:
        r = await c.post(REDIS_URL, headers={"Authorization": f"Bearer {REDIS_TOKEN}"}, json=list(args), timeout=10)
        return r.json().get("result")

async def scan_keys(pattern: str) -> List[str]:
    keys = []
    cursor = 0
    while True:
        result = await redis_cmd("SCAN", cursor, "MATCH", pattern, "COUNT", 500)
        if not result: break
        cursor = int(result[0])
        keys.extend(result[1])
        if cursor == 0: break
    return keys

def query_to_sparse(query: str) -> set:
    """Convert query to sparse indices for matching."""
    words = re.findall(r'\b[a-zA-Z]{3,}\b', query.lower())
    indices = set()
    for word in words:
        idx = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % 30000
        indices.add(idx)
    return indices

async def hybrid_search(query: str, patterns: List[str] = None, top_k: int = 10) -> List[Dict]:
    """
    Hybrid search:
    1. Sparse index matching (fast, precise)
    2. Metadata regex fallback (slower, broader)
    """
    if patterns is None:
        patterns = ["ada:now:*", "ada:self:*", "ada:memory:*"]
    
    query_indices = query_to_sparse(query)
    query_terms = set(re.findall(r'\b[a-zA-Z]{3,}\b', query.lower()))
    
    results = []
    
    for pattern in patterns:
        keys = await scan_keys(pattern)
        
        for key in keys:
            raw = await redis_cmd("GET", key)
            if not raw:
                continue
            
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(data, list):
                    data = {"items": data}
            except:
                continue
            
            if not isinstance(data, dict):
                continue
            
            score = 0
            match_type = None
            
            # 1. Try sparse matching first
            sparse = data.get("sparse", {})
            if isinstance(sparse, dict) and sparse.get("indices"):
                doc_indices = set(sparse["indices"])
                overlap = len(query_indices & doc_indices)
                if overlap > 0:
                    score = overlap / max(len(query_indices), 1)
                    match_type = "sparse"
            
            # 2. Fallback: metadata regex matching
            if score == 0:
                content_str = json.dumps(data).lower()
                matches = sum(1 for term in query_terms if term in content_str)
                if matches > 0:
                    score = (matches / len(query_terms)) * 0.8  # Discount
                    match_type = "metadata_regex"
            
            if score > 0:
                # Extract display content
                content = data.get("content", data.get("text", ""))[:100]
                if not content and "metadata" in data:
                    content = data["metadata"].get("content", "")[:100]
                
                results.append({
                    "key": key,
                    "score": score,
                    "match_type": match_type,
                    "content": content,
                    "has_sparse": bool(sparse.get("indices"))
                })
    
    # Sort by score
    results.sort(key=lambda x: -x["score"])
    return results[:top_k]

async def main():
    print("=" * 60)
    print("HYBRID SEARCH TEST")
    print("=" * 60)
    
    queries = [
        "consciousness awareness presence",
        "vector endpoints deployed",
        "relationship jan solstice",
        "cognitive architecture sigma",
        "memory episodic langgraph"
    ]
    
    for query in queries:
        print(f"\n🔍 Query: '{query}'")
        results = await hybrid_search(query)
        
        if not results:
            print("   No results found")
        else:
            for i, r in enumerate(results[:3], 1):
                print(f"   {i}. [{r['match_type']}] score={r['score']:.2f}")
                print(f"      key: {r['key'][:50]}...")
                if r['content']:
                    print(f"      content: {r['content'][:60]}...")

if __name__ == "__main__":
    asyncio.run(main())
