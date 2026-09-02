# Fila e agendamento no SIGMA

Worker novo entra em `producao/services/envia_pendencias.py` ou explica por
que exige scheduler próprio. A execução precisa de lock, timeout declarado,
registro de início/fim e regra de recuperação para item que ficou em
processamento após interrupção.

Não apague pendência por falha. Status pendente, processando, integrado e
falha têm transições explícitas; uma limpeza por retenção só existe quando a
regra de negócio disser que o registro já foi conciliado fora do SIGMA.

O teste prova que duas execuções não enviam o mesmo item, que timeout devolve
o item ao estado recuperável e que a resposta desconhecida não vira integrado.

## Observabilidade de falha

O painel **Status (Services)** (`producao/services/status.py`) é um
registry em memória: some com o processo e não acusa processo zumbi nem
worker morto sem registrar. Por isso o diagnóstico externo deriva do
banco — a única coisa que sobrevive ao processo — e não do registry.

O monitor derivado do banco ainda não existe. A exposição da rota de saúde
(autenticada × anônima com cache e limite de taxa) é decisão de política
do sênior. Quando existir, o motor segue este desenho:

- payload derivado de `FonteTelemetria.ultima_coleta_em`, status das
  filas e `intervalo_segundos` dos workers, com **lista branca de
  campos** — só sai o que está na lista — e cache como defesa, para que
  consulta de saúde não vire carga;
- régua de graus incluindo "não foi possível apurar": nada de dado velho
  passado por fresco;
- o próprio scheduler é monitorado: se ele para de concluir ciclos, a
  régua acusa "agendador mudo" — falha que nenhum worker registra.
