# Cognition Engine

### The operating system for AI-assisted development

AI tools write code brilliantly in the moment — but they forget yesterday, ignore the plan, repeat mistakes, and burn tokens without warning.

**Cognition Engine** gives your AI coding workflow:

- **Persistent memory** — pick up exactly where you left off
- **Phased master plans** — 8–24 phases with sub-tasks and progress maps
- **Token budgets** — warn at 80%, wrap up at 90%, hard stop at 100%
- **Hallucination shield** — block invented imports before they touch your repo

---

## How it works

```
You: ce init          →  Scans project, creates dna.json + phase plan
You: ce start         →  Bootstrap: "PHASE_03, sub-task 2 — continue API endpoints"
You: work in Cursor   →  AI reads .cognition/bootstrap.md
You: ce end           →  Progress saved; tomorrow's start knows yesterday
```

---

## Built for developers who use

Claude Code · Cursor · Any tool that reads project context files

Open-source core. Pro features (proxy, advanced shield) planned.

---

## Get started

```bash
pip install -e packages/cognition-engine
ce init
ce start
```

[GitHub](.) · [V1 features](V1_FEATURES.md)
