from __future__ import annotations

from pathlib import Path

COGNITION_RULE_MARKER = "<!-- cognition-engine -->"
RULE_SNIPPET = """
{cognition_rule_marker}
## Cognition Engine

At the start of each coding session, read `.cognition/bootstrap.md` for current phase, sub-task, and constraints.
When finishing work, remind the user to run `ce end --summary "..."`.
"""


def install_cursor(root: Path, bootstrap_markdown: str | None = None) -> list[str]:
    """Write bootstrap and Cursor rules snippet."""
    cog = root / ".cognition"
    cog.mkdir(parents=True, exist_ok=True)
    if bootstrap_markdown:
        (cog / "bootstrap.md").write_text(bootstrap_markdown, encoding="utf-8")

    rules_dir = root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rule_path = rules_dir / "cognition-engine.mdc"

    body = RULE_SNIPPET.format(cognition_rule_marker=COGNITION_RULE_MARKER)
    if rule_path.is_file():
        existing = rule_path.read_text(encoding="utf-8")
        if COGNITION_RULE_MARKER in existing:
            return [str(cog / "bootstrap.md"), str(rule_path)]
    else:
        existing = ""

    rule_path.write_text(
        f"---\ndescription: Cognition Engine session bootstrap\nalwaysApply: true\n---\n{body}",
        encoding="utf-8",
    )
    return [str(cog / "bootstrap.md"), str(rule_path)]
