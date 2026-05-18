"""First-time and project setup wizard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.cli import formatters, prompts
from src.cli.context import ProjectContext
from src.cli.git_helpers import git_init_project, write_project_gitignore
from src.core.constants import COGNITION_DIR, GLOBAL_CONFIG_PATH, MODELS_REGISTRY_PATH
from src.models.dynamic_registry import bundled_models_path, ensure_models_yaml


def global_config_template() -> dict[str, Any]:
    return {
        "default_model": "claude-sonnet-4-20250514",
        "shield_sensitivity": "medium",
        "proxy": {"enabled": False, "host": "127.0.0.1", "port": 8787},
        "api_keys": {},
        "git": {"auto_commit": False, "auto_commit_message_prefix": "ce:"},
    }


def project_config_template() -> dict[str, Any]:
    return {
        "default_model": "claude-sonnet-4-20250514",
        "shield_sensitivity": "medium",
        "git": {"auto_commit": True, "auto_commit_message_prefix": "ce:"},
    }


def setup_global(*, interactive: bool = True) -> Path:
    """Create ~/.cognition/config.yaml and models.yaml."""
    global_dir = Path(GLOBAL_CONFIG_PATH).expanduser().parent
    global_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = Path(GLOBAL_CONFIG_PATH).expanduser()
    models_path = ensure_models_yaml(Path(MODELS_REGISTRY_PATH).expanduser())

    if not cfg_path.is_file():
        data = global_config_template()
        if interactive:
            if prompts.confirm("Configure API keys now?", False):
                for provider in ("anthropic", "openai", "deepseek"):
                    key = prompts.ask_text(f"{provider} API key (empty to skip)", default="")
                    if key.strip():
                        data.setdefault("api_keys", {})[provider] = key.strip()
            model = prompts.ask_text("Default model id", default=data["default_model"])
            if model.strip():
                data["default_model"] = model.strip()
        cfg_path.write_text(yaml.safe_dump(data, default_flow_style=False), encoding="utf-8")
        formatters.print_success(f"Created {cfg_path}")
    else:
        formatters.print_info(f"Global config exists: {cfg_path}")

    formatters.print_info(f"Models registry: {models_path}")
    formatters.print_info(f"Bundled defaults: {bundled_models_path()}")
    return cfg_path


def setup_project(
    project_path: Path,
    *,
    goal: str = "",
    run_plan: bool = True,
    phases: int = 24,
    install_cursor: bool = True,
    init_git: bool = True,
    reinit: bool = False,
) -> ProjectContext:
    """Initialize CE for a project directory."""
    root = project_path.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    ctx = ProjectContext(root)
    if ctx.is_initialized() and not reinit:
        formatters.print_info("Project already initialized.")
    else:
        ctx.init_project(reinit=reinit)
        formatters.print_success(f"Initialized: {root.name}")

    write_project_gitignore(root)
    cfg_path = root / COGNITION_DIR / "config.yaml"
    if not cfg_path.is_file() or reinit:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(
            yaml.safe_dump(project_config_template(), default_flow_style=False),
            encoding="utf-8",
        )

    goal_text = goal.strip()
    goal_file = root / "GOAL.md"
    if not goal_text and goal_file.is_file():
        lines = goal_file.read_text(encoding="utf-8").splitlines()
        body: list[str] = []
        for line in lines[2:]:
            if line.strip() == "---":
                break
            body.append(line)
        goal_text = "\n".join(body).strip()

    if goal_text:
        ctx.set_project_goal(goal_text)
        _write_goal_file(root, goal_text)

    if run_plan and goal_text:
        from src.planner.phase_generator import generate_goal_plan

        scan = ctx.scan()
        phase_list = generate_goal_plan(goal_text, num_phases=phases, language=scan["language"])
        ctx.save_plan(phase_list, goal=goal_text)
        formatters.print_success(f"Plan saved ({len(phase_list)} phases).")

    if install_cursor:
        try:
            from src.cognition_engine.adapters.cursor import install_cursor

            boot = ctx.cognition_dir / "bootstrap.md"
            md = boot.read_text(encoding="utf-8") if boot.is_file() else ""
            paths = install_cursor(root, md)
            formatters.print_info(f"Cursor rules: {paths[-1]}")
        except Exception as exc:
            formatters.print_warning(f"Cursor adapter skipped: {exc}")

    if init_git:
        for msg in git_init_project(root, initial_commit=bool(goal_text or goal_file.is_file())):
            formatters.print_info(msg)

    return ctx


def _write_goal_file(root: Path, goal: str) -> None:
    if not goal.strip():
        return
    path = root / "GOAL.md"
    path.write_text(
        "# Project goal\n\n"
        f"{goal.strip()}\n\n"
        "---\n\n"
        "_Managed by Cognition Engine (`cognition-engine goal --set`)._\n",
        encoding="utf-8",
    )
    formatters.print_info(f"Goal file: {path}")


def run_full_setup(
    project_path: Path | None = None,
    *,
    interactive: bool = True,
) -> None:
    setup_global(interactive=interactive)
    if project_path:
        setup_project(project_path, reinit=False)
    formatters.print_rule("Setup complete")
    formatters.print_info("Run: cognition-engine chat   (interactive session)")
    formatters.print_info("Or:  cognition-engine start  (bootstrap only)")
