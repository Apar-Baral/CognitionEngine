# Cognition Engine

AI-assisted development with **session memory**, a **phased plan** in DNA, **token awareness**, and a **hallucination shield**. Ships as the **`ce`** / **`cognition-engine`** CLI and a **full-screen agent TUI**.

**Repo:** [github.com/Apar-Baral/CognitionEngine](https://github.com/Apar-Baral/CognitionEngine)

---

## Install (once)

Python **3.11+**. Install the package from **`packages/cognition-engine/`** (not the monorepo root):

```bash
git clone https://github.com/Apar-Baral/CognitionEngine.git
cd CognitionEngine/packages/cognition-engine
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip && pip install -e .
ce --version
```

**Linux:** use `ce` or `cognition-engine`, not bare `cc` (that is the system C compiler).

---

## Minimal CLI example

Run in **your app folder** (not inside the Cognition Engine repo):

```bash
cd ~/projects/my-app
export ANTHROPIC_API_KEY=...    # or set keys in ~/.cognition/config.yaml
ce init
ce plan --goal "Add REST API with auth and tests"
ce start --preview             # see what the AI will read
ce start                       # writes .cognition/bootstrap.md
# … work in Cursor / Claude Code using that file …
ce end --summary "Implemented auth and first endpoints"
ce status
```

---

## Agent TUI

```bash
cd ~/projects/my-app
cognition-engine
```

Use **sidebar** actions for setup / plan / start. **Model** dropdown is in the **top strip** (use **Ctrl+M** for search). Type **`/`** in the prompt to see **slash commands**. **Click the chat log**, then drag to select text; if the terminal should own copy (**Ctrl+Shift+C** on Linux), run with **`CE_NATIVE_COPY=1`** and scroll with **PgUp** / **PgDn**.

---

## More detail

- Package-specific notes: [`packages/cognition-engine/README.md`](packages/cognition-engine/README.md)  
- Git attribution: [`docs/GIT_ATTRIBUTION.md`](docs/GIT_ATTRIBUTION.md)  
- Feature roadmap notes: [`docs/V1_FEATURES.md`](docs/V1_FEATURES.md)
