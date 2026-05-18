"""Rotating REPL tips (Claude Code–style hints)."""

from __future__ import annotations

CE_TIPS: list[str] = [
    "Press Ctrl+M to search all models quickly.",
    "Copy reply button or Ctrl+Shift+C — also saves ~/.cognition/last_reply.txt.",
    "Click the chat log, drag to select text, then Ctrl+Shift+C.",
    "Use /shield to see hallucination prevention status.",
    "Use /showplan to print the 24-phase master plan in chat.",
    "Setup keys stores DeepSeek under DEEPSEEK — not OpenAI.",
    "Token usage updates live in the top bar during chat.",
    "Esc cancels a running model request.",
    "Type /goal once, then Generate plan for a full roadmap.",
    "/end can auto-commit with git.user_name in ~/.cognition/config.yaml.",
    "Set CE_GIT_USER_NAME and CE_GIT_USER_EMAIL for session commits.",
    "Linux: drag mouse to copy chat (CE_NATIVE_COPY=1 default). CE_NATIVE_COPY=0 for mouse UI.",
    "Manual commit: git add -A && git commit -m 'your message' in your shell.",
    "Run grep, python, and pipelines via the agent when you ask in chat.",
    "Change the model dropdown — the active API key slot updates automatically.",
]
