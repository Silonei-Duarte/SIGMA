# WMS XC — API HTTP e DBLINK Oracle

O SIGMA fala com o WMS de duas formas diferentes, para coisas diferentes:

- **API HTTP/JSON** para **efetivar** — criar lote, ajustar estoque,
  registrar pendência. Payload montado em
  `setores/qualidade/utils/wms_integracao.py` (`montar_sku_wms`,
  `dados_wms_liberacao_lote`); quem chama é
  `setores/qualidade/views/wms_views.py`, `liberar_lotes.py`,
  `liberar_area_vermelha.py`, via `requests.post`/`get`.
- **DBLINK Oracle** para **consultar** — paletes, saldos, locais. É
  leitura via o mesmo mecanismo de `oracle.md` (alias de conexão), só que
  a query atravessa um DBLINK configurado no lado Oracle até o banco do
  WMS. Não confundir com a API: DBLINK nunca grava.

## Regras

- **Efetivação (criar lote, ajustar estoque) segue o mesmo cuidado de
  envio do `soap-sapiens.md`**: grava intenção local antes de chamar a
  API, trata desfecho desconhecido como pendente (não reenvia sem
  confirmar), timeout declarado.
- **Reaproveite `wms_integracao.py`** para montar payload; não remonte o
  formato do zero numa view nova — se o formato mudar, muda num lugar só.
- **Consulta por DBLINK é leitura**, mesma regra de `oracle.md`: bind
  variable, nunca concatenação de SQL.
- **Erro da API do WMS** (corpo de erro, status HTTP não-2xx) é falha —
  não silencie em `try/except` genérico; registre o motivo no local onde
  a pendência é visível.

## Teste

Mocke `requests.post`/`requests.get` com o corpo de resposta real da API
do WMS quando disponível. Para DBLINK, mocke a conexão Oracle como em
`oracle.md` — o teste não precisa saber que é DBLINK do lado do banco, só
que a consulta pode devolver vazio (sem palete) ou preenchida.
