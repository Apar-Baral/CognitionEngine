# Cognition Engine

**Persistent memory, phased planning, token control, and hallucination prevention for AI-assisted development.**

Cognition Engine is a **`cc` CLI** that orchestrates how you work with AI coding tools (Cursor, Claude Code, Windsurf, etc.). It does not replace your editor — it gives every session a **plan**, **memory**, **budget**, and **validation** so you stop re-explaining the project and catching fake imports after the fact.

| Problem | How `cc` helps |
|---------|----------------|
| AI forgets the project each session | DNA + `.cognition/bootstrap.md` restores context |
| Invented imports and APIs | Hallucination Shield (`cc validate`) |
| Surprise API bills | Token budgets, proxy, `cc budget` |
| No sense of progress | Phased master plan + `cc status` |
| Wrong model for the task | `~/.cognition/models.yaml` + intelligent routing |

---

## Requirements

- **Python 3.11+**
- **pip**
- **Git** (optional; used for technical-debt age detection)
- API keys for at least one provider (Anthropic, OpenAI, DeepSeek, etc.)

---

## Installation

This repository is a **monorepo**. The installable Python package is **not** the repo root — it is under `packages/cognition-engine/` (that folder contains `pyproject.toml`).

```bash
git clone https://github.com/Apar-Baral/CognitionEngine.git
cd CognitionEngine/packages/cognition-engine

python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

pip install -U pip
pip install -e .
```

If you already created a venv at the repo root, either activate it and `cd` into `packages/cognition-engine` before `pip install -e .`, or create a new venv inside `packages/cognition-engine` as above.

**Wrong (will fail):**

```bash
cd CognitionEngine          # repo root — no pyproject.toml here
pip install -e .
```

Verify:

```bash
ce --version
ce --help
```

### Linux / Kali: do not use bare `cc`

On Unix, **`cc` is the system C compiler** (gcc), not Cognition Engine. If you see errors like `liblto_plugin.so` or `unrecognized command-line option '--goal'`, you are calling the wrong program.

| Use this | Avoid on Linux |
|----------|----------------|
| `ce` | `cc` (conflicts with gcc) |
| `cognition-engine` | — |

```bash
which ce              # should point to your venv, e.g. .../venv/bin/ce
which cc              # often /usr/bin/cc — that's gcc
```

After install, prefer:

```bash
ce init
ce plan --goal "..."
ce start --preview
```

On first use, Cognition Engine creates (if missing):

| Path | Purpose |
|------|---------|
| `~/.cognition/config.yaml` | API keys, default model, proxy settings |
| `~/.cognition/models.yaml` | Full model registry (Claude, GPT, DeepSeek, Gemini, …) |

---

## Quick start (5 minutes)

```bash
# 1. Go to YOUR project (not the Cognition Engine repo)
cd /path/to/your/app

# 2. Initialize
cc init

# 3. Generate a phased plan
cc plan --goal "Build a REST API for a todo app with JWT auth and tests"

# 4. Preview what the AI will see this session
cc start --preview

# 5. Start a real session
cc start

# 6. Open .cognition/bootstrap.md in Cursor or Claude Code, then code

# 7. When done
cc end --summary "Added user model and POST /todos endpoint"

# 8. See progress
cc status
```

---

## Worked example: “I want to develop an XSS finder in a webapp”

This walks through a **real project** from zero: a web application that scans pages or forms for cross-site scripting (XSS) risks. Cognition Engine does not write the scanner for you — it **plans the work**, **remembers context** between sessions, and **validates** AI-generated code before you trust it.

### What you are building (the product)

| Piece | Description |
|-------|-------------|
| **Web UI** | Upload URL or paste HTML; show scan results |
| **Scanner core** | Parse inputs, detect reflected/stored XSS patterns, report severity |
| **API** | Optional REST API for CI integration |
| **Tests** | Fixtures with safe/unsafe samples so the AI does not hallucinate test helpers |

Cognition Engine sits **next to** this repo — in a terminal — while you code in **Cursor** or **Claude Code**.

### Step 0 — Install Cognition Engine (once per machine)

```bash
git clone https://github.com/Apar-Baral/CognitionEngine.git
cd CognitionEngine/packages/cognition-engine
pip install -e .
cc --version
```

### Step 1 — Create your application project

```bash
mkdir xss-finder-webapp
cd xss-finder-webapp
git init
# Scaffold your stack (example: Python/FastAPI + React — use whatever you prefer)
```

This folder is **your product**. All `cc` commands run **inside** `xss-finder-webapp/`, not inside the Cognition Engine repo.

### Step 2 — Global configuration (`~/.cognition/config.yaml`)

Create or edit this file on your machine. **Never commit it to git.**

For a security tool (where bad imports and fake APIs are costly), use a **stricter shield** and a **solid default model**:

```yaml
# ~/.cognition/config.yaml

default_model: claude-sonnet-4-20250514

shield_sensitivity: high   # stricter Hallucination Shield (cc validate)

api_keys:
  anthropic: sk-ant-...    # at least one provider
  openai: sk-...

proxy:
  enabled: false           # set true later if you want token budgets via proxy
  host: 127.0.0.1
  port: 8787

budgets:
  BUILD: 75000             # tokens per BUILD session
  DEBUG: 50000
  EXPLORE: 35000             # useful for spike / research sessions
```

**Optional — economy model for boilerplate** (edit `~/.cognition/models.yaml`, already created on first run):

Use a premium model for architecture and security-critical modules; route simple UI copy or docs to `gpt-4o-mini` or `deepseek-chat` via `cc start --model gpt-4o-mini` when appropriate.

### Step 3 — Initialize Cognition Engine in the webapp repo

```bash
cd xss-finder-webapp
cc init
```

This creates:

```text
xss-finder-webapp/
  .cognition/
    dna.json
    config.yaml
    sessions/
```

### Step 4 — Generate a phased plan for the XSS finder

```bash
cc plan --goal "Develop a web application that finds XSS vulnerabilities: users submit a URL or HTML, the backend runs static/heuristic checks for reflected and stored XSS patterns, results show severity and evidence snippets. Include a test suite with known-safe and known-vulnerable fixtures. Target Python FastAPI backend and a simple React frontend."
```

Review the printed phase map. Typical phases might look like:

| Phase | Focus |
|-------|--------|
| PHASE_01 | Discovery — scope, threat model, stack |
| PHASE_02 | Project skeleton, CI, config |
| PHASE_03 | Scanner core (parsing, rules) |
| PHASE_04 | API endpoints |
| PHASE_05 | Frontend UI |
| PHASE_06 | Test fixtures (XSS samples) |
| PHASE_07 | Auth / rate limits (if needed) |
| PHASE_08 | Hardening & documentation |

Confirm or re-plan:

```bash
cc plan --force --goal "..."   # only if you want to replace the plan
```

### Step 5 — Integrate with Cursor or Claude Code (the technique)

Cognition Engine **does not plug into your webapp’s runtime**. Integration is **workflow + files**:

```text
  Terminal (you)                    AI editor (Cursor / Claude Code)
  ─────────────                     ───────────────────────────────
  cc start  ──►  writes  ──►  .cognition/bootstrap.md  ──►  AI reads this
  cc end    ◄──  saves    ◄──  your edits + summary      ◄──  you code
```

#### Option A — Cursor (recommended)

1. Run `cc start` in `xss-finder-webapp/`.
2. Open **`.cognition/bootstrap.md`** — phase, sub-tasks, avoid list, budget.
3. Create **`.cursor/rules/cognition-engine.mdc`** (once):

```markdown
---
description: Cognition Engine session context
globs: *
alwaysApply: true
---

At the start of each coding session, read and follow:
`.cognition/bootstrap.md`

That file defines the current phase, tasks, and patterns to avoid (e.g. invented security libraries).
Do not introduce dependencies that are not already in the project without checking.
```

4. Start a Cursor Agent/Chat session — it should respect the rule and bootstrap.
5. When finished: `cc end --summary "Implemented URL fetch + basic reflected XSS rule"`.

#### Option B — Claude Code

1. `cc start`
2. Copy the contents of `.cognition/bootstrap.md` into **`CLAUDE.md`** at the project root (or add: “Read `.cognition/bootstrap.md` before coding.”).
3. Run Claude Code in the same directory.
4. `cc end` when done.

#### Option C — Manual paste (any editor)

1. `cc start --preview` → read output in terminal.
2. Paste bootstrap text into the **first message** of a new chat.
3. Code; then `cc end`.

### Step 6 — First coding session (example commands)

```bash
# See context without starting
cc start --preview

# Start session focused on scanner core
cc start --task "Implement reflected XSS detection for query parameters in HTML responses"

# While the AI generates code, validate critical files:
cc validate backend/scanner/reflected.py
cc validate backend/scanner/rules.py

# Check token budget mid-session (if using proxy, or after end)
cc budget

# Close session
cc end --summary "Added reflected XSS rule and 12 unit tests with fixtures"
```

### Step 7 — Next sessions (same project, no re-init)

```bash
cc status                    # see PHASE_03 progress, blockers
cc start                     # bootstrap picks up where DNA left off
# ... work in Cursor ...
cc validate path/to/new_file.py
cc end --summary "Stored XSS detection + API endpoint /scan"
cc insights                  # patterns from past sessions
```

You only run `cc init` and `cc plan` **once** per repo (unless you deliberately replan).

### Step 8 — Optional: token proxy

If you want **automatic** token counting and budget warnings:

1. In `~/.cognition/config.yaml`: `proxy.enabled: true` and valid `api_keys`.
2. In Cursor: set the OpenAI-compatible / custom API base URL to `http://127.0.0.1:8787` (if your setup routes through it).
3. Always: `cc start` → work → `cc end` → `cc budget`.

### Configuration summary for this example

| What | Where | Suggested value |
|------|--------|-----------------|
| API keys | `~/.cognition/config.yaml` | Your Anthropic/OpenAI keys |
| Shield strictness | `~/.cognition/config.yaml` | `high` for security code |
| Session budget | `~/.cognition/config.yaml` → `budgets.BUILD` | `75000` (adjust down if needed) |
| Project settings | `.cognition/config.yaml` | Created by `cc init`; tune with `cc config --list` |
| AI session context | `.cognition/bootstrap.md` | Regenerated every `cc start` |
| Cursor integration | `.cursor/rules/cognition-engine.mdc` | Points AI at bootstrap |
| Plan & memory | `.cognition/dna.json` | Updated by `cc plan`, `cc end` |

### What Cognition Engine is *not* doing

- It is **not** deployed inside your webapp to scan XSS for end users.
- It is **not** a replacement for OWASP ZAP or Burp — you are **building** a finder; `cc` manages **how you build it with AI**.

---

## Daily workflow (managing AI coding sessions)

Use this loop every time you sit down to code.

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌─────────┐
│  cc start   │ ──► │ AI tool +    │ ──► │  cc end         │ ──► │ cc      │
│  (context)  │     │ bootstrap.md │     │  (save memory)  │     │ status  │
└─────────────┘     └──────────────┘     └─────────────────┘     └─────────┘
```

### One-time per repository

```bash
cc init
cc plan --goal "Describe your product in 2–3 sentences"
```

Creates:

```
your-project/
  .cognition/
    dna.json           # Master plan, phases, insights, avoid registry
    config.yaml        # Project budgets and shield settings
    bootstrap.md       # Regenerated each cc start (give this to the AI)
    sessions/          # Session logs and metrics
    active_session.json
```

### Every coding session

| Step | Command | What to do |
|------|---------|------------|
| 1 | `cc start` | Builds session context; writes `bootstrap.md` |
| 2 | — | Open **`.cognition/bootstrap.md`** in your AI tool (see below) |
| 3 | — | Code normally in Cursor / Claude Code |
| 4 | `cc validate file.py` | Optional: check suspicious AI output |
| 5 | `cc budget` | Optional: check token zone mid-session |
| 6 | `cc end --summary "..."` | Saves progress, insights, next-step hint |

Between sessions:

```bash
cc status              # compact progress
cc status --detailed   # full map + history
cc history             # past sessions
cc insights            # recommendations from prior work
```

Work from another folder:

```bash
cc --project "E:\Projects\my-app" status
```

---

## Using with Cursor

1. Run `cc start` in your project root.
2. Open **`.cognition/bootstrap.md`**.
3. Either:
   - Paste the contents into the **first message** of a new Cursor chat, or
   - Add a Cursor rule (`.cursor/rules/`) that says: “Read and follow `.cognition/bootstrap.md` at session start.”
4. Code as usual.
5. Run `cc end` when finished.

Optional: enable the API proxy (see [Token proxy](#token-proxy-optional)) and set Cursor’s OpenAI-compatible base URL to `http://127.0.0.1:8787` for automatic token tracking.

---

## Using with Claude Code

1. Run `cc start`.
2. Copy **`.cognition/bootstrap.md`** into **`CLAUDE.md`** (or tell Claude to read that file first).
3. Work in the terminal/IDE as you normally would with Claude Code.
4. Run `cc end --summary "what you completed"`.

---

## Configuration

### Global: `~/.cognition/config.yaml`

Create or edit this file (never commit it to git):

```yaml
default_model: claude-sonnet-4-20250514
shield_sensitivity: medium   # low | medium | high

api_keys:
  anthropic: sk-ant-api03-...
  openai: sk-...
  deepseek: sk-...

proxy:
  enabled: false
  host: 127.0.0.1
  port: 8787

budgets:
  BUILD: 75000
  DEBUG: 50000
```

### Project: `.cognition/config.yaml`

Created by `cc init`. View or change:

```bash
cc config --list
cc config --key shield_sensitivity --value high
```

### Models: `~/.cognition/models.yaml`

Lists every LLM (Claude, GPT-4o, DeepSeek, Gemini, OpenRouter, …). Edit to add Ollama or a custom endpoint — **no code changes**; the file reloads on save.

```bash
cc models --list
cc models --status
cc models --route
```

See `packages/cognition-engine/config/default_models.yaml` for the full template.

---

## Token proxy (optional)

When enabled, all API traffic goes through Cognition Engine for counting, budget zones (green → yellow → red), and cost estimates.

1. Set in `~/.cognition/config.yaml`:

   ```yaml
   proxy:
     enabled: true
     port: 8787
   ```

2. Add API keys under `api_keys` in the same file.

3. Point your AI tool’s API base URL to: **`http://127.0.0.1:8787`**

4. Always bracket work with:

   ```bash
   cc start
   # ... coding ...
   cc end
   ```

5. Check spend: `cc budget`

---

## Complete command reference

| Command | Description | Example |
|---------|-------------|---------|
| `cc init` | Initialize project | `cc init` |
| `cc plan` | Generate/update plan | `cc plan --goal "SaaS dashboard" --phases 20` |
| `cc start` | Start session | `cc start --task "Implement login"` |
| `cc start --preview` | Show bootstrap only | `cc start --preview` |
| `cc end` | End session | `cc end --summary "Finished API routes"` |
| `cc status` | Project status | `cc status --detailed` |
| `cc status --phase` | One phase detail | `cc status --phase PHASE_03` |
| `cc budget` | Token budget | `cc budget --show` |
| `cc budget --set` | Set limit | `cc budget --set 100000` |
| `cc insights` | AI-generated insights | `cc insights` |
| `cc history` | Session history | `cc history --limit 20` |
| `cc config` | Config | `cc config --list` |
| `cc validate` | Shield check | `cc validate src/api.py` |
| `cc models` | Model registry | `cc models --list` |
| `cc completion install` | Tab completion | `cc completion install` |

**Global flags:** `--project PATH`, `--verbose`, `--version`

**Help:** `cc COMMAND --help`

---

## What each major feature does

| Feature | You interact via |
|---------|------------------|
| **DNA / master plan** | `cc plan`, `cc status` |
| **Bootstrap context** | `cc start` → `bootstrap.md` |
| **Session memory** | `cc end`, `cc history` |
| **Hallucination Shield** | `cc validate` |
| **Budget / proxy** | `cc budget`, proxy config |
| **Model routing** | `models.yaml`, `cc models` |
| **Insights & learning** | `cc insights`, automatic on `cc end` |

---

## Repository layout

```
CognitionEngine/
  packages/cognition-engine/   ← pip install here; `cc` CLI lives here
  adapters/                    ← Cursor / Claude Code notes
  examples/dogfood/            ← Example: CE managing itself
  docs/                        ← Product docs
```

**Package README (extra detail):** [packages/cognition-engine/README.md](packages/cognition-engine/README.md)

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `cc: command not found` | Run `pip install -e .` from `packages/cognition-engine` |
| “Not initialized” | Run `cc init` in your **project** root, not the CE repo |
| Empty bootstrap | Run `cc plan` first, then `cc start` |
| API errors | Check `~/.cognition/config.yaml` keys |
| Proxy not counting tokens | Ensure `proxy.enabled: true` and tool points to `127.0.0.1:8787` |

---

## Development (contributors)

```bash
cd packages/cognition-engine
pip install -e ".[dev]"
pytest tests/test_phase1_core.py tests/test_phase2_dna.py tests/test_phase3_memory.py \
  tests/test_phase4_bootstrap.py tests/test_phase5_proxy.py tests/test_phase6_shield.py \
  tests/test_phase7_cli.py tests/test_phase8_visualization_navigator.py \
  tests/test_phase9_models.py -q
```

---

## License

MIT
