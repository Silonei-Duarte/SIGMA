# Índices personalizados Oracle ERP

Última validação: 2026-06-23.

--------------------------------------------------------------------------------

## I_NEX_E900EOQ_LOTE

### SQL

```sql
CREATE INDEX I_NEX_E900EOQ_LOTE
ON E900EOQ (CODEMP, CODLOT, DATREA, HORREA);
```

### USO

Rastreamento público de lote. Busca eventos de produção/apontamento ERP do lote e ordena por `DATREA` e `HORREA`.

--------------------------------------------------------------------------------

## I_NEX_E210DLS_LOTE

### SQL

```sql
CREATE INDEX I_NEX_E210DLS_LOTE
ON E210DLS (CODEMP, CODLOT, CODDEP, CODPRO, CODDER);
```

### USO

Rastreamento público de lote. Busca saldo atual ERP dos lotes encontrados no rastreamento.

--------------------------------------------------------------------------------

## I_NEX_E210MVP_LOTE_FULL

### SQL

```sql
CREATE INDEX I_NEX_E210MVP_LOTE_FULL
ON E210MVP (CODEMP, CODLOT, USU_CODLIG, DATDIG, HORDIG, SEQMOV);
```

### USO

Rastreamento público de lote. Busca movimentos ERP do lote original, obtém `USU_CODLIG` e ordena por `DATDIG`, `HORDIG` e `SEQMOV`.

--------------------------------------------------------------------------------

## I_NEX_E210MVP_LIG

### SQL

```sql
CREATE INDEX I_NEX_E210MVP_LIG
ON E210MVP (CODEMP, USU_CODLIG, DATDIG, HORDIG, SEQMOV);
```

### USO

Rastreamento público de lote. Busca movimentos ERP ligados pelo mesmo `USU_CODLIG` e mantém transferências/reclassificações agrupadas no fluxo.

--------------------------------------------------------------------------------

## I_NEX_E210MVP_LOTE_CODLIG

### SQL

```sql
CREATE INDEX I_NEX_E210MVP_LOTE_CODLIG
ON E210MVP (CODEMP, CODLOT, ESTEOS, CODLIG, DATDIG, HORDIG, SEQMOV);
```

### USO

Rastreamento público de lote. Atende o fallback por `CODLIG` quando o movimento não possui `USU_CODLIG`, buscando o lote original e ordenando por `DATDIG`, `HORDIG` e `SEQMOV`.

--------------------------------------------------------------------------------

## I_NEX_E210MVP_CODLIG

### SQL

```sql
CREATE INDEX I_NEX_E210MVP_CODLIG
ON E210MVP (CODEMP, CODLIG, ESTEOS, DATDIG, HORDIG, SEQMOV, CODLOT);
```

### USO

Rastreamento público de lote. Busca movimentos ERP ligados pelo mesmo `CODLIG` quando o fallback é necessário, preservando a separação entre entrada e saída por `ESTEOS`.

--------------------------------------------------------------------------------

## I_NEX_E900EOQ_OP_RECURSO

### SQL

```sql
CREATE INDEX I_NEX_E900EOQ_OP_RECURSO
ON E900EOQ (CODEMP, CODORI, NUMORP, CODCRE, SEQEOQ);
```

### USO

Rastreamento público de lote. Busca a máquina/recurso da OP a partir dos movimentos de estoque `E210MVP.ORIORP` e `E210MVP.NUMDOC`, usando a menor sequência de operação com `CODCRE` preenchido.

--------------------------------------------------------------------------------
