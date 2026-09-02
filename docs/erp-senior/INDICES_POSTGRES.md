# Índices personalizados PostgreSQL

Última validação: 2026-05-26.

--------------------------------------------------------------------------------

## ix_liberacao_lote_codlot

### SQL

```sql
CREATE INDEX ix_liberacao_lote_codlot
ON qualidade.liberacao_lote (codemp, codlot, datger);
```

### USO

Rastreamento público de lote. Busca eventos locais de qualidade pelo lote original e ordena por `datger`.

--------------------------------------------------------------------------------

## ix_liberacao_lote_lottrf

### SQL

```sql
CREATE INDEX ix_liberacao_lote_lottrf
ON qualidade.liberacao_lote (codemp, lottrf, datger);
```

### USO

Rastreamento público de lote. Quando a URL recebe um lote transferido/reclassificado, encontra o lote original pelo `lottrf`.

--------------------------------------------------------------------------------

## idx_parada_recurso_fim

### SQL

```sql
CREATE INDEX idx_parada_recurso_fim
ON producao.paradas_maquina (recurso_id, fim);
```

### USO

Consultas de parada por recurso, principalmente para localizar parada em aberto ou histórico recente.

--------------------------------------------------------------------------------

## idx_parada_tipo_fim

### SQL

```sql
CREATE INDEX idx_parada_tipo_fim
ON producao.paradas_maquina (tipo, fim);
```

### USO

Consultas de parada por tipo manual ou sinal, filtrando paradas abertas ou encerradas.

--------------------------------------------------------------------------------

## oee_planeja_data_30140b_idx

### SQL

```sql
CREATE INDEX oee_planeja_data_30140b_idx
ON public.oee_planejado_diario (data);
```

### USO

Consultas de OEE planejado por data.

--------------------------------------------------------------------------------
