#!/usr/bin/env python
"""Guarda de comandos irreversíveis — hook PreToolUse do Claude Code para a
ferramenta Bash.

Existe porque um `manage.py flush`, um `migrate <app> zero`, um `push
--force` ou um `rm -rf` numa pasta do projeto não têm desfazer — e o aviso
em CLAUDE.md não impede um comando que já foi digitado. Este script impede.

Lê o JSON do hook na entrada padrão; sai com 2 (bloqueia, e a mensagem na
saída de erro volta para a IA) ou com 0 (segue). Qualquer falha interna sai
com 0: a guarda nunca pode ser o que derruba o trabalho.

Registrado em .claude/settings.json. Ver CLAUDE.md.
"""

import json
import re
import subprocess
import sys

# Cada regra: expressão, motivo, o que fazer. A mensagem é lida pela IA e
# repassada à pessoa — por isso diz o caminho certo, não só "não".
RULES = [
    (
        r"\bmanage\.py\s+flush\b",
        "apaga TODOS os dados de TODAS as tabelas do banco apontado pelo .env do "
        "diretório atual — inclusive a fila de integração e o histórico local.",
        "Se for mesmo necessário em desenvolvimento, a pessoa roda à mão. Para "
        "mudar o esquema use uma migration nova.",
    ),
    (
        r"\bmanage\.py\s+migrate\b[^|;&\n]*\bzero\b",
        "reverte TODAS as migrations da app apontada — dropa as tabelas que elas "
        "criaram, inclusive dados.",
        "Para evoluir o esquema use migration nova + `manage.py migrate`. "
        "Reversão total é decisão do desenvolvedor sênior.",
    ),
    (
        r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE)\b",
        "instrução SQL que apaga tabela, schema, banco ou todo o conteúdo de uma "
        "tabela do PostgreSQL operacional.",
        "Mudança de esquema é migration nova. Se for mesmo necessário à mão, "
        "peça para o desenvolvedor sênior confirmar e executar.",
    ),
    (
        r"\bgit\s+push\b[^|;&]*(\s--force(-with-lease)?\b|\s-f\b|\s\+\S+)",
        "reescreve o histórico remoto; o que outra pessoa já puxou deixa de existir.",
        "Faça um commit novo que corrija o anterior (`git revert`, se preciso). "
        "Nunca force o push.",
    ),
    (
        r"\bgit\s+push\b[^|;&]*\s(--delete|-d)\b|\bgit\s+push\b[^|;&]*:refs/"
        r"(heads|tags)/",
        "apaga uma referência (branch ou tag) no remoto — sem desfazer.",
        "Apagar referência remota é decisão do desenvolvedor sênior; ele roda à "
        "mão se for mesmo o caso.",
    ),
    (
        r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f[a-z]*|checkout\s+--\s+\.|"
        r"restore\s+\.|branch\s+-D|tag\s+-d)\b",
        "descarta trabalho não commitado ou apaga referência local, sem desfazer.",
        "Se há mudanças a descartar, liste-as (`git status`, `git diff`) e peça "
        "à pessoa que confirme; ela desfaz à mão.",
    ),
    (
        r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*|--recursive)\s+(?:-[a-zA-Z]+\s+)*"
        r'["\']?(?:\./)?(?:/|~|\.|\*|\.git|\.env|\.venv|accounts|producao|'
        r"setores|telemetria|SIGMA|templates|static|theme|docs|certs|mobile|"
        r'Uteis_projeto)(?:/\*?)?["\']?(?=\s|$)',
        "remove recursivamente uma pasta do projeto ou do sistema.",
        "Remova arquivos específicos, um a um, ou peça à pessoa. Pastas geradas "
        "(`.venv`, `node_modules`, `staticfiles`) se recriam por `uv sync` e "
        "`manage.py collectstatic`.",
    ),
    (
        r"\b(cat|type|less|more|head|tail|bat|strings|Get-Content|gc)\b"
        r'[^|;&]*(^|[\s/\\"\'])\.env(\.production|\.local)?(?=\s|$|["\'])',
        "imprime o .env inteiro — credenciais reais (Oracle, Sapiens, WMS, "
        "LDAP, Firebase) iriam parar na conversa.",
        "Leia só a chave que precisa (`grep NOME_DA_CHAVE .env`) e nunca mostre "
        "o valor de segredo. O .env.example não é afetado por esta regra.",
    ),
]


def _arquivos_em_stage() -> list[str]:
    resultado = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode:
        return []
    return [linha.replace("\\", "/") for linha in resultado.stdout.splitlines()]


def _commit_tem_teste_para_views() -> bool:
    arquivos = _arquivos_em_stage()
    apps_com_views = {
        "/".join(caminho.split("/")[:-2])
        for caminho in arquivos
        if "/views/" in caminho and caminho.endswith(".py")
    }
    if not apps_com_views:
        return True
    apps_com_testes = {
        "/".join(caminho.split("/")[:-2])
        for caminho in arquivos
        if "/tests/" in caminho and caminho.endswith(".py")
    }
    return apps_com_views.issubset(apps_com_testes)


def main() -> int:
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw else {}
    except Exception:
        return 0

    if not isinstance(data, dict):
        return 0

    command = data.get("tool_input", {}).get("command")

    if not isinstance(command, str) or not command.strip():
        return 0

    if (
        re.search(r"\bgit\s+commit\b", command, re.IGNORECASE)
        and not _commit_tem_teste_para_views()
    ):
        sys.stderr.write(
            "BLOQUEADO: há view alterada em stage sem teste novo/alterado no mesmo app.\n"
            "Inclua a regressão em <app>/tests/test_*.py e rode a esteira antes do commit.\n"
        )
        return 2

    for pattern, reason, instead in RULES:
        if re.search(pattern, command, re.IGNORECASE):
            sys.stderr.write(
                "BLOQUEADO pela guarda do projeto (.claude/hooks/guarda_de_comandos.py).\n"
            )
            sys.stderr.write(f"Comando: {command}\n")
            sys.stderr.write(f"Motivo: {reason}\n")
            sys.stderr.write(f"Em vez disso: {instead}\n")
            sys.stderr.write(
                "Não tente contornar a guarda com outra forma do mesmo "
                "comando: informe a pessoa e siga com o resto da demanda.\n"
            )
            return 2

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
