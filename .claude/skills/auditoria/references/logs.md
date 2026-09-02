# Log operacional no SIGMA

Use `logging.getLogger(__name__)` no módulo e preserve o stack no servidor com
`logger.exception(...)` ou `exc_info=True`. A mensagem mostrada na tela ou no
JSON é genérica; ela não contém `str(exc)` de driver, banco, SOAP ou HTTP.

Cada log útil identifica a operação e, quando necessário, IDs locais seguros:
empresa, filial, PK da fila e código de correlação. Não inclua credenciais,
cookies, URLs completas com query/userinfo, envelopes nem respostas brutas.

Falha de integração registra o motivo e mantém a pendência visível para
reprocessamento. Sucesso rotineiro não precisa poluir o log: use o registro de
execução/fila já existente como fonte operacional.
