"""First-time and project setup wizard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.cli import formatters, prompts
from src.cli.context import ProjectContext
from src.cli.git_helpers import (
    get_git_remote_url,
    git_init_project,
    has_gh_cli,
    is_git_repo,
    push_to_github,
    write_project_gitignore,
)
from src.cli.model_picker import prompt_select_model
from src.cli.setup_summary import (
    format_setup_summary_rich,
    save_last_setup,
    save_project_setup_summary,
)
from src.core.constants import COGNITION_DIR, GLOBAL_CONFIG_PATH, MODELS_REGISTRY_PATH
from src.core.user_state import set_flag
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


def setup_global(*, interactive: bool = True) -> tuple[Path, dict[str, Any]]:
    """Create ~/.cognition/config.yaml and models.yaml. Returns path + summary fragment."""
    summary: dict[str, Any] = {"install_type": "slim"}
    global_dir = Path(GLOBAL_CONFIG_PATH).expanduser().parent
    global_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = Path(GLOBAL_CONFIG_PATH).expanduser()
    models_path = ensure_models_yaml(Path(MODELS_REGISTRY_PATH).expanduser())

    api_configured: list[str] = []
    chosen_model = global_config_template()["default_model"]

    if not cfg_path.is_file():
        data = global_config_template()
        if interactive:
            if prompts.confirm("Configure API keys now?", False):
                for provider in ("anthropic", "openai", "deepseek"):
                    key = prompts.ask_text(f"{provider} API key (empty to skip)", default="")
                    if key.strip():
                        data.setdefault("api_keys", {})[provider] = key.strip()
                        api_configured.append(provider)
            chosen_model = prompt_select_model(
                default_id=data["default_model"],
                interactive=True,
            )
            data["default_model"] = chosen_model
        else:
            chosen_model = data["default_model"]
        cfg_path.write_text(yaml.safe_dump(data, default_flow_style=False), encoding="utf-8")
        formatters.print_success(f"Created {cfg_path}")
    else:
        formatters.print_info(f"Global config exists: {cfg_path}")
        existing = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        chosen_model = str(existing.get("default_model", chosen_model))
        api_configured = list((existing.get("api_keys") or {}).keys())
        if interactive and prompts.confirm("Change default model?", default=False):
            chosen_model = prompt_select_model(default_id=chosen_model, interactive=True)
            existing["default_model"] = chosen_model
            cfg_path.write_text(yaml.safe_dump(existing, default_flow_style=False), encoding="utf-8")

    summary["default_model"] = chosen_model
    summary["api_keys_configured"] = api_configured
    summary["models_registry"] = str(models_path)
    formatters.print_info(f"Models registry: {models_path}")
    formatters.print_info(f"Bundled defaults: {bundled_models_path()}")
    return cfg_path, summary


def prompt_git_setup(project_root: Path, *, interactive: bool = True) -> bool:
    """One-time-per-project local git offer."""
    if not interactive:
        return False
    if is_git_repo(project_root):
        return False
    marker = project_root / COGNITION_DIR / ".git_setup_done"
    if marker.is_file():
        return False
    if not prompts.confirm(
        "Initialize git for this project with a CE-friendly .gitignore? (recommended, one-time)",
        default=True,
    ):
        set_flag("git_setup_declined_once", True)
        return False
    return True


def prompt_github_push(project_root: Path, *, interactive: bool = True) -> str:
    """
    Ask to push the working project to GitHub (Hermes-style).
    Returns status: skipped | declined | success | failed | already_remote
    """
    if not interactive or not is_git_repo(project_root):
        return "skipped"
    if get_git_remote_url(project_root):
        formatters.print_info(f"Git remote already set: {get_git_remote_url(project_root)}")
        return "already_remote"
    marker = project_root / COGNITION_DIR / ".github_push_prompted"
    if marker.is_file():
        return "skipped"

    if not prompts.confirm(
        "Push this project to GitHub now? (creates repo and uploads — needs `gh` CLI or remote URL)",
        default=False,
    ):
        marker.write_text("declined\n", encoding="utf-8")
        return "declined"

    private = True
    if interactive:
        private = prompts.confirm("Private repository?", default=True)

    remote_url = ""
    if not has_gh_cli():
        formatters.print_warning("GitHub CLI (`gh`) not found or not logged in.")
        remote_url = prompts.ask_text(
            "Git remote URL (empty to skip push)",
            default="",
        ).strip()
        if not remote_url:
            marker.write_text("skipped\n", encoding="utf-8")
            return "skipped"

    ok, msg = push_to_github(
        project_root,
        private=private,
        remote_url=remote_url or None,
    )
    marker.write_text("done\n", encoding="utf-8")
    if ok:
        formatters.print_success(msg)
        return "success"
    formatters.print_warning(msg)
    return "failed"


def setup_project(
    project_path: Path,
    *,
    goal: str = "",
    run_plan: bool = True,
    phases: int = 24,
    install_cursor: bool = True,
    init_git: bool | None = None,
    push_github: bool | None = None,
    reinit: bool = False,
    interactive: bool = True,
) -> tuple[ProjectContext, dict[str, Any]]:
    """Initialize CE for a project directory."""
    summary: dict[str, Any] = {"project_path": str(project_path.resolve())}
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
        summary["goal_preview"] = goal_text[:120]

    if run_plan and goal_text:
        from src.planner.phase_generator import generate_goal_plan

        scan = ctx.scan()
        phase_list = generate_goal_plan(goal_text, num_phases=phases, language=scan["language"])
        ctx.save_plan(phase_list, goal=goal_text)
        formatters.print_success(f"Plan saved ({len(phase_list)} phases).")
        summary["phases"] = len(phase_list)

    if install_cursor:
        try:
            from src.cognition_engine.adapters.cursor import install_cursor

            boot = ctx.cognition_dir / "bootstrap.md"
            md = boot.read_text(encoding="utf-8") if boot.is_file() else ""
            paths = install_cursor(root, md)
            formatters.print_info(f"Cursor rules: {paths[-1]}")
        except Exception as exc:
            formatters.print_warning(f"Cursor adapter skipped: {exc}")

    do_git = init_git
    if do_git is None:
        do_git = prompt_git_setup(root, interactive=interactive)
    summary["git_initialized"] = bool(do_git) or is_git_repo(root)
    if do_git:
        write_project_gitignore(root)
        for msg in git_init_project(root, initial_commit=bool(goal_text or goal_file.is_file())):
            formatters.print_info(msg)
        (root / COGNITION_DIR / ".git_setup_done").write_text("1\n", encoding="utf-8")
        formatters.print_success("Git initialized for this project.")

    gh_status = "skipped"
    if push_github is True or (push_github is None and interactive and summary["git_initialized"]):
        gh_status = prompt_github_push(root, interactive=interactive)
    summary["github_push"] = gh_status

    g_model = _load_global().get("default_model") or global_config_template()["default_model"]
    model_id = str(g_model)
    ctx.config.update("default_model", model_id, persist=True)
    summary["default_model"] = model_id
    save_project_setup_summary(root, summary)
    return ctx, summary


def _load_global() -> dict[str, Any]:
    path = Path(GLOBAL_CONFIG_PATH).expanduser()
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


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
    init_git: bool | None = None,
    push_github: bool | None = None,
    install_semantic: bool = False,
) -> None:
    _, global_summary = setup_global(interactive=interactive)
    if install_semantic:
        _install_semantic_extra()
        global_summary["install_type"] = "semantic"
    project_summary: dict[str, Any] = {}
    if project_path:
        _, project_summary = setup_project(
            project_path,
            reinit=False,
            init_git=init_git,
            push_github=push_github,
            interactive=interactive,
        )
    merged = {**global_summary, **project_summary}
    save_last_setup(merged)
    formatters.print_rule("Setup complete")
    from rich.panel import Panel

    prompts.console.print(Panel(format_setup_summary_rich(merged, project_summary), title="Your setup", border_style="blue"))
    formatters.print_info("Run: cognition-engine          (interactive REPL)")
    formatters.print_info("Or:  cognition-engine chat")
    if not install_semantic:
        formatters.print_info(
            "Slim install (no PyTorch). For Chroma embeddings later: "
            "cognition-engine setup --semantic (inside CE venv only)"
        )


def _install_semantic_extra() -> None:
    import subprocess
    import sys

    from src.core.env_guard import is_venv_active

    if not is_venv_active():
        formatters.print_error(
            "Semantic install must run inside the CE virtualenv (never system pip on Kali)."
        )
        formatters.print_info("Activate: source ~/CognitionEngine/packages/cognition-engine/.venv/bin/activate")
        return

    pkg = Path(__file__).resolve().parents[2]
    formatters.print_warning(
        "Installing [semantic] extras (~4GB download: PyTorch + Chroma). This may take several minutes."
    )
    if not prompts.confirm("Continue with semantic install?", default=False):
        return
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-e", f"{pkg}[semantic]"],
    )
    formatters.print_success("Semantic extras installed.")
