"""Shell tab completion installation."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def detect_shell() -> str:
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return "zsh"
    if "fish" in shell:
        return "fish"
    return "bash"


def install_completions(shell: str | None = None) -> None:
    shell = (shell or detect_shell()).lower()
    script = _completion_script(shell)
    home = Path.home()

    if shell == "bash":
        target = home / ".bash_completion.d" / "cc"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(script, encoding="utf-8")
        line = f'source "{target}"'
        rc = home / ".bashrc"
        _append_line(rc, line)
        print(f"Installed bash completion: {target}")
    elif shell == "zsh":
        target = home / ".zfunc" / "_cc"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(script, encoding="utf-8")
        print(f"Installed zsh completion: {target}")
        print("Add to .zshrc: fpath=(~/.zfunc $fpath); autoload -Uz compinit && compinit")
    elif shell == "fish":
        target = home / ".config" / "fish" / "completions" / "cc.fish"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(script, encoding="utf-8")
        print(f"Installed fish completion: {target}")
    else:
        print(script)


def _append_line(path: Path, line: str) -> None:
    if path.is_file() and line in path.read_text(encoding="utf-8"):
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n# Cognition Engine completion\n{line}\n")


def _completion_script(shell: str) -> str:
    if shell == "fish":
        return '''complete -c cc -f -a "init plan start end status budget insights history config validate completion version"'''
  # bash/zsh via typer
    try:
        result = subprocess.run(
            ["cc", "--install-completion", shell],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout.strip():
            return result.stdout
    except FileNotFoundError:
        pass
    return _TYPER_FALLBACK_BASH


_TYPER_FALLBACK_BASH = '''
_cc_completion() {
  local cur="${COMP_WORDS[COMP_CWORD]}"
  local commands="init plan start end status budget insights history config validate completion"
  COMPREPLY=( $(compgen -W "${commands}" -- "${cur}") )
}
complete -F _cc_completion cc
'''
