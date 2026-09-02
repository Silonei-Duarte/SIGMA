#!/usr/bin/env python
"""Formata e corrige com o Ruff cada arquivo Python que a IA acabou de
escrever — hook PostToolUse do Claude Code para as ferramentas Edit e Write.

Quem orienta a IA não tem como perceber um import fora de ordem ou um espaço
a mais. Rodar o Ruff no arquivo no instante em que ele é gravado tira a
formatação da lista de coisas que alguém precisa lembrar.

Só o arquivo tocado, nunca o projeto inteiro: o diff de uma demanda não pode
engolir a reformatação de código alheio. Sempre sai com 0 — falha do Ruff
aparece no `ruff check`/`ruff format --check` da esteira, não aqui.

Registrado em .claude/settings.json. Ver CLAUDE.md.
"""

import json
import subprocess
import sys
from pathlib import Path


def find_ruff(project_root: Path) -> Path | None:
    for candidate in (
        project_root / ".venv" / "Scripts" / "ruff.exe",
        project_root / ".venv" / "bin" / "ruff",
    ):
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw else {}
    except Exception:
        return 0

    if not isinstance(data, dict):
        return 0

    file_path = data.get("tool_input", {}).get("file_path")

    if not isinstance(file_path, str) or not file_path.lower().endswith(".py"):
        return 0

    project_root = Path(__file__).resolve().parents[2]

    try:
        real = Path(file_path).resolve()
        real.relative_to(project_root)
    except OSError, ValueError:
        return 0

    if not real.is_file():
        return 0

    ruff = find_ruff(project_root)

    if ruff is None:
        return 0

    subprocess.run([str(ruff), "check", "--fix", "--quiet", str(real)])
    subprocess.run([str(ruff), "format", "--quiet", str(real)])

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
