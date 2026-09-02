# Oracle — ERP Senior e Alchemy

Dois bancos Oracle, dois aliases de conexão em `SIGMA/settings.py`:
`oracle_erp` (ERP Senior/Sapiens, produção e lote) e `oracle_alchemy`
(análises de qualidade). Os dois são **só leitura** para o SIGMA — nenhuma
gravação direta neles, nunca. Gravação no ERP é sempre por webservice
Sapiens (`soap-sapiens.md`); WMS via DBLINK é tratado em `wms.md`.

## Como consultar (padrão a seguir)

```python
from SIGMA.integracoes.oracle import cursor_oracle_erp


def buscar_op(numero_op: str) -> dict | None:
    with cursor_oracle_erp() as cursor:
        cursor.execute(
            "SELECT ... FROM tabela WHERE num_ped = :num_ped",
            {"num_ped": numero_op},
        )
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [col[0].lower() for col in cursor.description]
        return dict(zip(columns, row))
```

Pontos que não se negocia:

- **Sempre `cursor_oracle_erp()`/`cursor_oracle_alchemy()`**, nunca
  `oracledb.connect()` nem cursor direto em código novo — o client usa o
  alias Django gerenciado e a credencial de `SIGMA/settings.py`.
- **Bind variable sempre**, nunca f-string/concatenação montando o SQL
  com dado de entrada (`:num_ped`, não `f"... = '{numero_op}'"`).
- **O context manager `cursor_oracle_*()`** fecha o cursor sozinho; não
  guarde cursor como atributo de instância vivendo além da função.
- **Timeout de sessão** é o padrão do driver `oracledb` — se uma consulta
  específica for lenta e puder travar tela, considere paralelizar ou
  cachear no service, não no template.
- **Nome de coluna do Oracle** costuma vir em maiúsculas via `oracledb`;
  normalize (`.lower()`) antes de expor em dict/JSON, como no exemplo
  acima.

## Migração concluída

As chamadas de aplicação usam o client compartilhado. Se surgir um cursor
direto ou `oracledb.connect()` em código novo, trate como regressão e migre
para `cursor_oracle_erp()` ou `cursor_oracle_alchemy()`.

## Consulta ao vivo × fila

A maioria das leituras de Oracle no projeto hoje é consulta ao vivo, sob
ação de gente (abrir uma tela, resolver um apontamento). Só vira fila
quando o resultado precisa sobreviver a uma manutenção do Oracle ou
alimentar painel/TV com recarregamento automático (ver a tabela de decisão
em `../SKILL.md`). Antes de guardar o resultado de uma consulta numa
tabela nova do PostgreSQL, confirme que é mesmo esse o caso — cópia
desnecessária de dado do ERP é fonte de divergência.

## Teste

Nunca aponte teste para o Oracle real. Mocke no ponto de chamada:

```python
from unittest.mock import patch, MagicMock


@patch("django.db.connections")
def test_buscar_op_no_encontrada_devolve_none(self, mock_connections):
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    mock_connections.__getitem__.return_value.cursor.return_value.__enter__.return_value = cursor
    ...
```

Se não souber o formato real de uma tabela (nome de coluna, tipo), diga no
relatório que o mock usa um formato presumido — não invente com confiança
que não tem.
