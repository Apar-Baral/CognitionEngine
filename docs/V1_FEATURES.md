# V1 feature list (Phase 0 validation)

Derived from documented developer pain points and Phase 1–3 build plan. **Build only what is listed here** until validated with real users.

## Ranked pain points → features

| Rank | Pain point | V1 feature | Phase |
|------|------------|------------|-------|
| 1 | Session amnesia — "what was I doing?" | DNA + session store + bootstrap on `ce start` | 1 |
| 2 | No progress visibility | ASCII progress map, `ce status` | 1 |
| 3 | Cost blindness | Manual token entry, budget zones, `ce budget` | 2 |
| 4 | Hallucinated imports/APIs | Stage-1 shield (AST import/symbol check), avoid register | 3 |
| 5 | Context bloat | Bootstrap hard cap ~2000 tokens | 1 |
| 6 | Host lock-in | Tool-agnostic core + Cursor/Claude adapters | 1b |

## In scope for v1

- `ce init`, `ce start`, `ce end`, `ce status`
- `dna.json` schema v1 (phases, sub-tasks, sessions_index, avoid_registry)
- Strategic / tactical / operational memory
- Session JSONL logs under `.cognition/sessions/`
- Bootstrap packet → `.cognition/bootstrap.md`
- Adapters: `ce adapter install cursor|claude_code`
- `ce budget`, `ce end --tokens N`
- Shield: validate Python imports against truth index

## Explicitly out of scope (v2+)

- API proxy (automatic interception)
- Multi-agent orchestration
- RL token allocator, mirror world simulator
- Cross-project transfer
- Vector DB truth store (v1 uses JSON symbol index)
- Stage 2/3 hallucination shield (semantic / runtime)

## Validation gate

Ship Phase 1 demo when **3+ developers** confirm they would use session continuity weekly.
