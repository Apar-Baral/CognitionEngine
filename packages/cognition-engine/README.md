# Cognition Engine — package & `cc` CLI

This directory is the installable Python package. After `pip install -e .`, the **`cc`** command is available globally.

**Repo-level guide (recommended starting point):** [../../README.md](../../README.md) — includes a full **worked example** (XSS finder webapp): configuration, `cc` commands, and Cursor/Claude integration.

---

## Install

```bash
# From this directory:
pip install -e .

# With dev tools (pytest, ruff, etc.):
pip install -e ".[dev]"
```

```bash
cc --version    # e.g. cognition-engine 0.1.0
cc --help
```

---

## First-time machine setup

### 1. Install the CLI (above)

### 2. Create `~/.cognition/config.yaml`

```yaml
default_model: claude-sonnet-4-20250514
shield_sensitivity: medium

api_keys:
  anthropic: YOUR_KEY
  openai: YOUR_KEY
  deepseek: YOUR_KEY

proxy:
  enabled: false
  host: 127.0.0.1
  port: 8787
```

Never put API keys in the project repo — only in this global file.

### 3. Model registry

On first run, `~/.cognition/models.yaml` is copied from `config/default_models.yaml` in this package. Edit it to add/remove models; changes apply without restart.

---

## Baral interactive mode (v0.3+)

Run the **Textual agent console** from your project (or anywhere):

```bash
cognition-engine              # full-screen TUI (recommended)
cognition-engine chat         # same
cognition-engine setup --project .
```

### Layout

- **Left rail:** project status, **Setup keys**, **Start session**, **Generate plan**, status/shield/end, etc.
- **Top strip:** **Active** model name + **dropdown** to switch models (same registry as `~/.cognition/models.yaml`). **Ctrl+M** opens the searchable picker.
- **Center:** chat log and inline agent progress while a turn runs.
- **Right:** **Agent trace** (tool steps) in its own scroll area.
- **Bottom:** tips rotate every few seconds (two lines).

### Selection and copy (your terminal, your rules)

- **Clickable UI (default):** Textual handles the mouse so buttons, dropdowns, and mouse wheel scrolling work. In most terminals, hold **Shift** while dragging if you want terminal selection/copy.
- **Terminal Ctrl+Shift+C mode:** run with **`CE_NATIVE_COPY=1`** so Cognition Engine starts with **`mouse=False`**; then use the terminal’s selection + **Ctrl+Shift+C**. Use **PgUp** / **PgDn** to scroll because clicks and wheel scrolling are disabled in this mode.
- **Backup:** each assistant reply is still written to **`~/.cognition/last_reply.txt`** for `cat` / `xclip` workflows.

**PgUp** / **PgDn** (with **priority** while the input is focused) scroll the scroll area that contains the focused widget, or the chat column by default.

### Other notes

- **No env hassle:** CE auto-runs inside `~/CognitionEngine/.../.venv` when installed via `install-ce.sh` (no Kali system-pip errors).
- **GitHub:** setup can ask once to push your project (`gh repo create` or remote URL).
- **Slash commands:** `/help`, `/setup`, `/model`, `/models`, `/plan`, `/start`, `/end`, `/status`, `/keys`, `/shield`, …

**Kali/Linux — use a venv (never system pip):**

```bash
curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/install-ce.sh | bash
source ~/CognitionEngine/packages/cognition-engine/.venv/bin/activate
cognition-engine setup --project ~/projects/your-app
```

**Upgrade** (run from `~` or `/tmp`, **not** from inside `~/CognitionEngine`):

```bash
cd ~
curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/install-ce.sh | bash
```

Default install is **slim (~200MB)**. Do **not** run `pip install -e ".[semantic]"` unless you need vector memory (~4GB PyTorch download).

```bash
# Only if you need Chroma embeddings:
cd ~/CognitionEngine/packages/cognition-engine
source .venv/bin/activate
pip install -e ".[semantic]"
```

Copy `config/profile.example.yaml` to `~/.cognition/profile.yaml` for defaults (model, auto_commit).

## Usage on your project

### Initialize

```bash
cd /path/to/your-application
cc init
```

### Plan

```bash
cc plan --goal "E-commerce API with Stripe and PostgreSQL"
cc plan --goal "Refactor monolith" --phases 15 --force   # replace existing plan
```

### Session lifecycle

```bash
# Preview context (no active session file)
cc start --preview

# Start session
cc start
cc start --task "Implement password reset flow"
cc start --budget 50000 --model gpt-4o-mini

# During work
cc status
cc budget
cc validate src/auth/service.py

# End session
cc end
cc end --summary "Completed reset email + tests" --tokens 42000
```

### After session

```bash
cc insights
cc history --limit 10
cc status --detailed
cc status --phase PHASE_05
```

---

## Bootstrap file (critical for AI tools)

Every `cc start` writes:

**`.cognition/bootstrap.md`**

This file contains:

- Current phase and sub-task  
- Project goal and constraints  
- “Avoid” registry (known hallucinations, failed approaches)  
- Recommended token budget  
- Resume instructions from the last session  

**You must feed this to your AI tool** (Cursor chat, Claude Code / `CLAUDE.md`, etc.). Cognition Engine does not inject it automatically unless you use a host adapter.

---

## Token proxy

| Setting | Location |
|---------|----------|
| Enable | `~/.cognition/config.yaml` → `proxy.enabled: true` |
| URL for AI tool | `http://127.0.0.1:8787` |
| Keys | `api_keys` in same global config |

Workflow:

```bash
cc start          # arms budget tracking
# ... API calls via proxy ...
cc end            # records session totals
cc budget         # review usage
```

Budget zones: **green** (safe) → **yellow** (caution) → **red** (wrap up) → **exhausted**.

---

## Hallucination Shield

```bash
cc validate path/to/file.py
```

Runs import validation and static checks against a truth index built from your codebase. Use on AI-generated files before merging.

---

## Model registry & routing

```bash
cc models --list      # all models in models.yaml
cc models --status    # circuit breakers / availability
cc models --route     # sample routing decision
```

Routing considers task complexity, required capabilities (`tool_use`, `vision`, …), and budget zone. Configure models in `~/.cognition/models.yaml`.

Example — add local Ollama:

```yaml
models:
  - id: llama3-local
    provider: ollama
    display_name: Llama 3 Local
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

---

## Full CLI reference

| Command | Flags / notes |
|---------|----------------|
| `init` | `[project_path]` |
| `plan` | `--goal`, `--phases`, `--force` |
| `start` | `--preview`, `--task`, `--budget`, `--model`, `--phase` |
| `end` | `--summary`, `--tokens` |
| `status` | `--detailed`, `--phase PHASE_XX` |
| `budget` | `--set N`, `--show` |
| `insights` | — |
| `history` | `--limit`, `--phase` |
| `config` | `--list`, `--key`, `--value` |
| `validate` | `FILE` required; `--code` optional |
| `models` | `--list`, `--status`, `--route` |
| `completion` | `install` subcommand |

**Globals:** `--project PATH`, `-p PATH`, `--verbose`, `-v`, `--version`

---

## Architecture (MVP)

| Module | Role |
|--------|------|
| `src/dna/` | Project DNA schema, load/save, mutations |
| `src/memory/` | Strategic / tactical / operational memory, sessions, metrics |
| `src/bootstrap/` | Context compiler, bootstrap generator |
| `src/proxy/` | API proxy, token counter, budget enforcer |
| `src/shield/` | Truth DB, import validator, validation pipeline |
| `src/cli/` | Typer commands, Rich UI |
| `src/visualization/` | Progress maps, dashboards |
| `src/navigator/` | Phases, dependencies, debt, recommendations |
| `src/models/` | Registry, request/response, router, fallback, pricing |
| `src/optimizer/` | RL token allocation |
| `src/synthesizer/` | Post-session insights |
| `src/planner/` | Phase plan generation |
| `src/scanner/` | Project detection on `cc init` |

Entry point: `src/main.py` → console script `cc`.

---

## Run tests

```bash
pytest tests/test_phase1_core.py tests/test_phase2_dna.py tests/test_phase3_memory.py \
  tests/test_phase4_bootstrap.py tests/test_phase5_proxy.py tests/test_phase6_shield.py \
  tests/test_phase7_cli.py tests/test_phase8_visualization_navigator.py \
  tests/test_phase9_models.py -q
```

---

## License

MIT
