# REST, webhooks e HTTP no SIGMA

Cliente HTTP novo centraliza URL configurada em `SIGMA/settings.py`, timeout,
tratamento de erro e máscara de log. Host, porta e caminho não vêm de entrada
da pessoa; URL com userinfo, query sensível ou redirecionamento aberto é
superfície de SSRF e vazamento.

Defina timeout de conexão curto e de resposta compatível com o worker. Só
retente falha transitória de rede ou resposta explicitamente reutilizável; uma
escrita com resultado desconhecido não é reenviada sem chave de idempotência
aceita pelo sistema externo. Desabilite redirects se a integração não precisar
deles; se precisar, valide cada destino contra a mesma política de host.

Webhook de entrada autentica assinatura/token antes de interpretar payload,
deduplica pelo identificador do evento e responde rápido, delegando trabalho
longo à fila local. Testes mockam a chamada HTTP e cobrem timeout, resposta
inválida, 429/503 quando houver retentativa e duplicidade.
