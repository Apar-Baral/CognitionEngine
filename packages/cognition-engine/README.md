# Cognition Engine

**AI Development Orchestrator** — persistent memory, phased planning, hallucination prevention, token budgeting, and intelligent multi-provider model routing.

## What it does

Cognition Engine wraps AI coding workflows (Claude Code, Cursor, and similar tools) with:

- **Project DNA** — structured master plan, phases, sub-tasks, and session history
- **Bootstrap context** — compact, tiered session prompts built from memory
- **API proxy** — token counting, budget zones, and cost projection
- **Hallucination Shield** — import/API validation before bad code lands
- **Strategic Navigator** — dependencies, critical path, debt, and recommendations
- **Dynamic model registry** — route tasks to the best LLM by complexity and budget (`~/.cognition/models.yaml`)
- **Knowledge synthesis** — insights from every session; RL learns token allocation splits

## Requirements

- Python 3.11+
- Git (optional; used for debt age / blame)
- API keys in `~/.cognition/config.yaml` (never in the project repo)

## Installation

```bash
cd packages/cognition-engine
pip install -e ".[dev]"
```

Verify the CLI:

```bash
cc --version
cc --help
```

On first run, Cognition Engine creates:

| Path | Purpose |
|------|---------|
| `~/.cognition/config.yaml` | Global settings and API keys |
| `~/.cognition/models.yaml` | Model registry (edit to add providers) |

## Quick start (new project)

```bash
cd /path/to/your/project
cc init
cc plan --goal "Build a REST API for a todo app"
cc start --preview          # inspect bootstrap context
cc start                    # begin session (see proxy note below)
# ... work with your AI tool ...
cc end
cc status
cc insights
cc models --list
cc models --status
```

## Configuration

### Project config (`.cognition/config.yaml`)

Created by `cc init`. Controls budgets, shield sensitivity, default model id, and proxy port.

```bash
cc config --list
cc config --key shield_sensitivity --value high
```

### Global config (`~/.cognition/config.yaml`)

```yaml
default_model: claude-sonnet-4-20250514
shield_sensitivity: medium
api_keys:
  anthropic: sk-ant-...
  openai: sk-...
  deepseek: sk-...
proxy:
  enabled: true
  port: 8787
```

### Model registry (`~/.cognition/models.yaml`)

Add any OpenAI-compatible, Anthropic, Google, OpenRouter, or Ollama endpoint without code changes. The file is watched for changes and reloads automatically.

Example custom model:

```yaml
models:
  - id: my-local-llm
    provider: ollama
    display_name: Local LLM
    api_base: http://localhost:11434
    endpoint: /api/chat
    auth_header: ""
    auth_prefix: ""
    capabilities: [chat, streaming]
    max_context: 8192
    max_output: 4096
    pricing: {input_per_1k: 0.0, output_per_1k: 0.0}
    tokenizer: generic
    default: false
    tier: economy
    custom: true
```

## CLI reference

| Command | Description |
|---------|-------------|
| `cc init` | Initialize `.cognition/` and DNA |
| `cc plan` | Generate master plan from a goal |
| `cc start` | Start session; optional `--preview`, `--task`, `--budget`, `--model` |
| `cc end` | End session, synthesize insights, update RL |
| `cc status` | Progress map and summary |
| `cc budget` | View or set token budget |
| `cc insights` | Show generated insights |
| `cc history` | Session history |
| `cc config` | View/edit configuration |
| `cc validate <file>` | Run Hallucination Shield on a file |
| `cc models --list` | List registered models |
| `cc models --status` | Circuit breaker / availability |
| `cc models --route` | Sample routing decision |
| `cc completion install` | Shell tab completion |

Global options: `--project PATH`, `--verbose`, `--version`

Use `cc --project /path/to/project COMMAND` when not in the project directory.

## API proxy (optional)

Point your AI tool at the local proxy to enforce budgets and log usage:

```text
http://127.0.0.1:8787
```

Enable in config (`proxy.enabled: true`). The proxy forwards to provider APIs and tracks tokens per session.

## Architecture (MVP modules)

```text
src/
  core/          Config, constants, types, exceptions
  dna/           Project DNA load/save/validate
  memory/        Strategic, tactical, operational, sessions, metrics
  bootstrap/     Context compiler and session bootstrap
  proxy/         API proxy and budget enforcement
  shield/        Hallucination validation pipeline
  cli/           Typer commands and Rich formatters
  visualization/ Progress maps, dashboards, heat maps
  navigator/     Phase tracking, dependencies, debt, recommendations
  models/        Registry, request builder, router, fallback, pricing
  optimizer/     RL token allocation and rewards
  synthesizer/   Knowledge synthesis and trends
  planner/       Phase plan generation
  scanner/       Project detection on init
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/test_phase1_core.py tests/test_phase2_dna.py tests/test_phase3_memory.py \
  tests/test_phase4_bootstrap.py tests/test_phase5_proxy.py tests/test_phase6_shield.py \
  tests/test_phase7_cli.py tests/test_phase8_visualization_navigator.py tests/test_phase9_models.py -q
```

## License

MIT
