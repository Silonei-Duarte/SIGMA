# Trilha de auditoria — proposta para o SIGMA

Se o SIGMA precisar de histórico genérico, o desenho mínimo é um model local
append-only com: ator opcional, ação enumerada, área, tipo e chave do objeto,
empresa/filial quando aplicável, resumo seguro e instante. A leitura exige
permissão explícita e permite filtrar por período, ator, ação e objeto.

O serviço central recebe somente campos já normalizados e uma representação
branca do objeto; não aceita dicionário arbitrário nem payload externo. A
criação acontece depois de persistir a ação e, quando ambas forem locais,
dentro da mesma transação. O model não expõe edição ou exclusão por tela,
admin ou comando comum.

Antes de implementar, definir com o sênior: ações cobertas, retenção, quem lê,
política LGPD e quais fluxos de fila precisam de registro agregado em vez de
um evento por item.
