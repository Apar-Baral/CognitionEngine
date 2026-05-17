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

```bash
git clone https://github.com/Apar-Baral/CognitionEngine.git
cd CognitionEngine/packages/cognition-engine
pip install -e .
```

Verify:

```bash
cc --version
cc --help
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
