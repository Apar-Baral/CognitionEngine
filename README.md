# Cognition Engine

**Persistent memory, token control, and hallucination prevention for AI-assisted development.**

Cognition Engine is an orchestration layer — not a code-writing agent. It manages the process of building software with Claude Code, Cursor, and other AI coding tools: session continuity, phased plans, budgets, and validation.

## The problem

- **Session amnesia** — every session starts blind
- **Hallucination whack-a-mole** — invented imports and APIs
- **Cost blindness** — surprise API bills
- **No project memory** — lessons don't transfer between sessions or projects

## What v1 does today

| Feature | Command |
|---------|---------|
| Initialize project DNA & phase plan | `ce init` |
| Start session with bootstrap context | `ce start` |
| End session and persist progress | `ce end` |
| View progress map & status | `ce status` |
| Session budget & token tracking | `ce budget` |
| Install host adapter (Cursor / Claude Code) | `ce adapter install cursor` |

Bootstrap context is written to `.cognition/bootstrap.md` (host-agnostic). Adapters optionally sync to Cursor rules or `CLAUDE.md`.

## Quick start

```bash
cd packages/cognition-engine
pip install -e ".[dev]"

# In any project root:
ce init --name "my-app"
ce start
# ... work in Cursor or Claude Code ...
ce end --summary "Implemented auth schema"
ce status
```

## Repository layout

```
packages/cognition-engine/   # Core library + CLI (pip installable)
adapters/                    # Thin Cursor & Claude Code adapters
apps/                        # Future products (pentest, optimizer)
examples/dogfood/            # CE managing itself
docs/                        # Landing, v1 features, interview guide
```

## Documentation

- [Landing / product overview](docs/LANDING.md)
- [V1 feature list (validated pain points)](docs/V1_FEATURES.md)
- [Developer interview guide](docs/INTERVIEW_GUIDE.md)
- [Dogfooding guide](examples/dogfood/README.md)

## License

MIT
