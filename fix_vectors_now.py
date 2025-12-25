"""
IMMEDIATE FIX: Populate sparse for existing vectors
"""

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
        r = await c.post(
            REDIS_URL,
            headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
            json=list(args),
            timeout=10
        )
        return r.json().get("result")

def extract_sparse(text: str) -> Dict[str, List]:
    if not text:
        return {"indices": [], "values": [], "terms": []}
    
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1
    
    indices, values, terms = [], [], []
    for word, freq in sorted(word_freq.items(), key=lambda x: -x[1])[:100]:
        idx = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % 30000
        indices.append(idx)
        values.append(float(freq))
        terms.append(word)
    
    return {"indices": indices, "values": values, "terms": terms}

def extract_text_from_any(data: Any) -> str:
    """Recursively extract text from any structure."""
    if isinstance(data, str):
        return data
    if isinstance(data, (int, float, bool)):
        return str(data)
    if isinstance(data, list):
        return " ".join(extract_text_from_any(item) for item in data)
    if isinstance(data, dict):
        parts = []
        for key in ["content", "text", "message", "chat", "topic", "intent", "now_topic", "description"]:
            if key in data and data[key]:
                parts.append(str(data[key]))
        # Also get felt/qualia as text
        if "felt" in data and isinstance(data["felt"], dict):
            parts.append(" ".join(f"{k}:{v}" for k, v in data["felt"].items()))
        if "qualia" in data and isinstance(data["qualia"], dict):
            parts.append(" ".join(f"{k}:{v}" for k, v in data["qualia"].items()))
        # Recurse into metadata
        if "metadata" in data:
            parts.append(extract_text_from_any(data["metadata"]))
        return " ".join(parts)
    return ""

async def scan_keys(pattern: str) -> List[str]:
    keys = []
    cursor = 0
    while True:
        result = await redis_cmd("SCAN", cursor, "MATCH", pattern, "COUNT", 500)
        if not result:
            break
        cursor = int(result[0])
        keys.extend(result[1])
        if cursor == 0:
            break
    return keys

async def fix_vector(key: str) -> Dict:
    raw = await redis_cmd("GET", key)
    if not raw:
        return {"key": key, "status": "not_found"}
    
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except:
        return {"key": key, "status": "parse_error"}
    
    # Handle list data (wrap in dict)
    if isinstance(data, list):
        data = {"items": data, "_was_list": True}
    
    if not isinstance(data, dict):
        return {"key": key, "status": "not_dict", "type": type(data).__name__}
    
    # Check if already has sparse
    sparse_existing = data.get("sparse")
    if isinstance(sparse_existing, dict) and sparse_existing.get("indices"):
        return {"key": key, "status": "already_has_sparse"}
    
    # Extract text
    full_text = extract_text_from_any(data)
    if not full_text.strip():
        return {"key": key, "status": "no_content"}
    
    # Generate sparse
    sparse = extract_sparse(full_text)
    if not sparse["indices"]:
        return {"key": key, "status": "no_keywords"}
    
    # Update data
    data["sparse"] = sparse
    data["has_sparse"] = True
    
    # If was list, save back as list with sparse added to first item
    if data.get("_was_list"):
        del data["_was_list"]
        items = data.get("items", [])
        if items and isinstance(items[0], dict):
            items[0]["sparse"] = sparse
            items[0]["has_sparse"] = True
        await redis_cmd("SET", key, json.dumps(items))
    else:
        await redis_cmd("SET", key, json.dumps(data))
    
    return {
        "key": key, 
        "status": "fixed",
        "terms_count": len(sparse["terms"]),
        "top_terms": sparse["terms"][:5]
    }

async def main():
    print("=" * 60)
    print("VECTOR SPARSE POPULATION FIX")
    print("=" * 60)
    
    patterns = [
        "ada:now:*",
        "ada:self:*", 
        "ada:whisper:*",
        "ada:insight:*",
        "ada:memory:*",
        "ada:outcome:*",
        "ada:bframe:*",
        "ada:ug:*"
    ]
    
    stats = {"scanned": 0, "fixed": 0, "already_ok": 0, "no_content": 0, "errors": 0}
    
    for pattern in patterns:
        print(f"\nScanning {pattern}...")
        keys = await scan_keys(pattern)
        print(f"  Found {len(keys)} keys")
        
        for key in keys:
            stats["scanned"] += 1
            try:
                result = await fix_vector(key)
                
                if result["status"] == "fixed":
                    stats["fixed"] += 1
                    print(f"  ✓ Fixed: {key[:45]}... ({result.get('terms_count', 0)} terms: {', '.join(result.get('top_terms', [])[:3])})")
                elif result["status"] == "already_has_sparse":
                    stats["already_ok"] += 1
                elif result["status"] in ("no_content", "no_keywords"):
                    stats["no_content"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"  ✗ Error on {key[:30]}: {e}")
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Scanned:    {stats['scanned']}")
    print(f"  Fixed:      {stats['fixed']}")
    print(f"  Already OK: {stats['already_ok']}")
    print(f"  No content: {stats['no_content']}")
    print(f"  Errors:     {stats['errors']}")

if __name__ == "__main__":
    asyncio.run(main())
