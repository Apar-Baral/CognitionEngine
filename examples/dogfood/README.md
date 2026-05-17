# Dogfooding Cognition Engine

Use Cognition Engine to build itself. Target: **10+ real sessions** before starting Product 1/2.

## Setup

From repository root:

```bash
cd packages/cognition-engine
pip install -e ".[dev]"
cd ../..
ce init --meta-tool --name "Cognition Engine"
```

## Session workflow

```bash
ce start --adapter cursor
# work in Cursor on current sub-task
ce end --summary "What you completed" --tokens 12000 --complete
ce status
```

## Session tracker

| # | Date | Phase / sub-task | Summary | Tokens |
|---|------|------------------|---------|--------|
| 1 | | PHASE_01 / T1 | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | | | |
| 9 | | | | |
| 10 | | | | |

Check progress:

```bash
ce status
ce budget
```

## Gates before Product 1/2

- [ ] 10 sessions logged in `dna.json` sessions_index
- [ ] Bootstrap stays under ~2000 tokens (`bootstrap_meta.json`)
- [ ] At least one `ce validate --import` catch during development
- [ ] Rare manual edits to `dna.json`

## Simulate session history (dev only)

```bash
python examples/dogfood/seed_sessions.py
```

This appends sample sessions for UI/testing — replace with real dogfood sessions for launch narrative.
