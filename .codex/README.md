# Espelho Claude para Codex

`.claude/` é a fonte única dos agentes e skills do SIGMA.

Os arquivos em `agents/` são somente pontes nativas do Codex. Cada ponte exige
que o subagente leia o respectivo `.claude/agents/<nome>.md` antes de agir e
carregue as skills declaradas no front matter desse arquivo.

Assim, editar um agente ou skill em `.claude/` já vale para Codex na próxima
execução do subagente. Não copie regras para `.codex/agents/`.

Após adicionar ou renomear agentes, reinicie a sessão Codex para ela recarregar
a configuração do projeto.
