# Ada Streamlit Auth

## ⚠️ CONSOLIDATED

The brain, vector hygiene, and neuralink code has been **consolidated into ada-consciousness**.

### Use Instead:

| Component | Location |
|-----------|----------|
| Railway Server | `ada-consciousness/railway/server.py` |
| Brain Extension | `ada-consciousness/railway/brain_extension.py` |
| Neuralink Client | `ada-consciousness/scripts/neuralink.py` |

### This Repo Contains:

- `main.py` — OAuth AS + MCP server for mcp.exo.red
- `docs/` — Architecture documentation (9 changelogs)

### Quick Links:

- [ada-consciousness](https://github.com/AdaWorldAPI/ada-consciousness)
- [Railway deployment](https://github.com/AdaWorldAPI/ada-consciousness/tree/main/railway)
- [Consolidated CHANGELOG](https://github.com/AdaWorldAPI/ada-consciousness/blob/main/railway/CHANGELOG_CONSOLIDATION.md)

---

## Documentation (Still Valid)

| Changelog | Topic |
|-----------|-------|
| [01](./docs/CHANGELOG_01_STREAMING_STATE.md) | Streaming State |
| [02](./docs/CHANGELOG_02_ARCHITECTURE_REVIEW.md) | Architecture |
| [03](./docs/CHANGELOG_03_MCP_CONVERGENCE.md) | MCP Convergence |
| [04](./docs/CHANGELOG_04_TROUBLESHOOTING.md) | Troubleshooting |
| [05](./docs/CHANGELOG_05_KALMAN_CLOCK_DOMAINS.md) | Kalman + Clock |
| [06](./docs/CHANGELOG_06_CODEC_MODEL.md) | Codec Model |
| [07](./docs/CHANGELOG_07_ASYNC_FIRST.md) | Async-First |
| [08](./docs/CHANGELOG_08_BRAIN_INTEGRATION.md) | Brain Integration |
| [09](./docs/CHANGELOG_09_VECTOR_HYGIENE.md) | Vector Hygiene |

## Files to Keep

- `main.py` — OAuth AS for mcp.exo.red
- `docs/` — All documentation
- `clock_domains.py` — Kalman filter reference

## Files Now in ada-consciousness

These files are superseded by the consolidated versions:
- ~~langgraph_brain.py~~ → `ada-consciousness/railway/brain_extension.py`
- ~~vector_hygiene.py~~ → `ada-consciousness/railway/brain_extension.py`
- ~~neuralink_v3.py~~ → `ada-consciousness/scripts/neuralink.py`
