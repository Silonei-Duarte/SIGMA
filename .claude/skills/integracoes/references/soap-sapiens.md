# SOAP — ERP Senior/Sapiens

O SIGMA efetiva no ERP **só** pelos webservices SOAP do Sapiens/Senior —
nunca por gravação direta no Oracle (`oracle.md` é só leitura). O helper
de protocolo é `producao/utils/sapiens_soap.py`: monta namespace e
cabeçalhos conforme `SAPIENS_SOAP_VERSION`. O transporte compartilhado é
`producao/services/sapiens.py`: use `enviar_soap_sapiens()` sempre.

## O que existe hoje

Há transporte único em `enviar_soap_sapiens()`. Cada worker de fila mantém
somente o envelope e a interpretação da resposta de negócio:

- `producao/views/logs_apontamentos.py` — envia apontamento de OP,
  `SERVICE_CODIGO = "fila_logs_apontamentos"`, usa `ThreadPoolExecutor`
  para paralelizar, `WEBSERVICE_TIMEOUT_SEGUNDOS` declarado.
- `producao/views/logs_tempos_erp.py` — envia pacote de tempos de
  produção e paradas.
- Padrão semelhante em `logs_apontamento_componentes.py`,
  `logs_baixa_componentes.py`.

Se a peça nova for mais uma dessas, use `enviar_soap_sapiens()` para o
transporte e mantenha timeout declarado, lock de processamento e atualização
de status ao final. Não replique `requests.post`, cabeçalhos ou codificação.

## Regras específicas do protocolo

- **Escape de XML sempre**: `xml.sax.saxutils.escape(valor)` em todo dado
  de entrada que vai para dentro do envelope — nome de cliente, observação
  de usuário, o que for. Sem isso, um apóstrofo ou `&` no dado quebra o
  XML ou, pior, altera a estrutura do envelope.
- **`erroExecucao` (ou campo equivalente do retorno) preenchido é
  falha**, mesmo com HTTP 200 — é assim que o Sapiens sinaliza que não
  processou.
- **Timeout de conexão curto, de resposta mais longo** — declarado, nunca
  implícito (`requests` sem `timeout=` pendura a thread do worker
  indefinidamente).
- **Retentativa só para falha de conexão.** Uma resposta do Sapiens —
  mesmo de erro de negócio — significa que ele recebeu; reenviar dobra o
  apontamento.
- **Nunca logar o envelope inteiro sem mascarar credencial** se o
  cabeçalho carregar usuário/senha do serviço.

## Teste

Mocke `requests.post` (ou o que o helper usa por baixo) com uma resposta
XML copiada de uma chamada real quando existir; se não existir, use a
resposta do teste do exemplar mais próximo e diga no relatório que o
contrato é presumido. Cenários mínimos: sucesso, `erroExecucao` preenchido,
timeout/erro de conexão (status não deve virar "integrado").
