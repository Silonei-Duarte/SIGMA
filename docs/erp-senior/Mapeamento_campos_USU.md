# Campo USU no Oracle ERP

| Campo      | Tabela | Operações | Uso no projeto | Referências |
|------------|---|---|---|---|
| USU_ATRCCU | E011DEF | SELECT | Regra personalizada para definir como atribuir o centro de custo na transferência de produto. | WebService Apontamento/TransferenciaProduto.lsp |
| USU_CCUFIX | E011DEF | SELECT | Centro de custo fixo usado quando a definição fiscal determina atribuição fixa na transferência de produto. | WebService Apontamento/TransferenciaProduto.lsp |
| USU_UTIAVE | E011DEF | WHERE | Flag que indica se o motivo/defeito é utilizável na Área Vermelha. | setores/qualidade/views/liberar_area_vermelha.py |
| USU_SITLOT | E210DLS | SELECT, UPDATE, WHERE/GROUP BY | Situação personalizada do lote: valida pendência, exibe status, filtra busca, marca lote como excluído/pendente e recebe a ação do webservice. | setores/qualidade/views/liberar_lotes.py, setores/qualidade/views/liberar_area_vermelha.py, setores/qualidade/utils/rastreamento_lote.py, producao/services/altera_apontamento.py, WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp, WebService Apontamento/TransferenciaProduto.lsp, WebService Apontamento/MovimentarEstoque |
| USU_CODLIG | E210MVP | SELECT, UPDATE, WHERE | Código personalizado de ligação entre movimentos de estoque para rastreamento do lote; no webservice guarda o CODLIG original antes de zerar a ligação. | setores/qualidade/utils/rastreamento_lote.py, WebService Apontamento/TransferenciaProduto.lsp |
| USU_NUMBOB | E900EOQ | SELECT, WHERE/JOIN/GROUP BY | Número personalizado da bobina. Usado para buscar última bobina apontada, histórico de apontamentos, telas de qualidade e localizar o depósito do lote nos webservices. | producao/views/apontamentos_v1.py, setores/qualidade/views/liberar_lotes.py, setores/qualidade/views/liberar_area_vermelha.py, setores/qualidade/utils/rastreamento_lote.py, producao/services/altera_apontamento.py, WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_BXAORP | E900CMO | SELECT, UPDATE, WHERE | Backup do `BXAORP` original do componente da OP. Os webservices gravam o valor original antes do apontamento, usam o campo para identificar componentes com baixa automática original, desativam temporariamente `BXAORP` para evitar baixa duplicada e depois restauram o valor original ou validam o backup na baixa posterior. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp, WebService Apontamento/ApontamentoComponente.lsp, WebService Apontamento/BaixarComponentes.lsp |
| USU_QTDBOB | E900COP | SELECT | Quantidade de bobinas planejada/esperada da OP, usada na tela de apontamentos. | producao/views/apontamentos_v1.py |
| USU_DESCRE | E725CRE | SELECT | Descrição/local personalizado do centro de recurso usado no envio WMS. | producao/views/wms_views.py |
| USU_CODEMP | USU_TPALWMS | INSERT, UPDATE, WHERE | Empresa usada para localizar e atualizar o palete WMS recebido no apontamento de componente. O service grava empresa 1, equivalente à empresa 0001. Faz parte da chave da importação WMS. | producao/services/importa_palete.py, WebService Apontamento/ApontamentoComponente.lsp |
| USU_PALWMS | USU_TPALWMS | INSERT, WHERE | Código do palete WMS recebido em CodLotCmp, usado para buscar e atualizar o registro do componente apontado. Faz parte da chave da importação WMS junto com empresa, lote, componente e derivação. | producao/services/importa_palete.py, WebService Apontamento/ApontamentoComponente.lsp |
| USU_QTDDIS | USU_TPALWMS | SELECT, INSERT, UPDATE | Quantidade disponível do palete WMS usada como quantidade do componente recebido e para validar saldo na E210DLS. Na importação, só atualiza registro existente quando a quantidade muda. | producao/services/importa_palete.py, WebService Apontamento/ApontamentoComponente.lsp |
| USU_CODLOT | USU_TPALWMS | SELECT, INSERT, WHERE | Lote ERP vinculado ao palete WMS; substitui o palete recebido para validar saldo e gravar a baixa do componente. Faz parte da chave da importação WMS. | producao/services/importa_palete.py, WebService Apontamento/ApontamentoComponente.lsp |
| USU_CODCMP | USU_TPALWMS | SELECT, INSERT, WHERE | Código do componente vinculado ao palete WMS recebido no apontamento. Faz parte da chave da importação WMS. | producao/services/importa_palete.py, WebService Apontamento/ApontamentoComponente.lsp |
| USU_DERCMP | USU_TPALWMS | SELECT, INSERT, WHERE | Derivação do componente vinculado ao palete WMS recebido no apontamento. Faz parte da chave da importação WMS. | producao/services/importa_palete.py, WebService Apontamento/ApontamentoComponente.lsp |
| USU_DATGER | USU_TPALWMS | INSERT, UPDATE | Data de geração/processamento marcada quando o palete é importado/lido e novamente quando o apontamento é concluído. | producao/services/importa_palete.py, WebService Apontamento/ApontamentoComponente.lsp |
| USU_HORGER | USU_TPALWMS | INSERT, UPDATE | Hora de geração da importação do palete WMS, gravada em minutos do dia. | producao/services/importa_palete.py |
| USU_ARMWMS | USU_TPALWMS | INSERT, UPDATE | Armazém/origem WMS do palete importado; o service grava `wmwhse1`. | producao/services/importa_palete.py |
| USU_HORLOG | USU_TPALWMS | UPDATE | Hora de log atualizada quando o palete é lido e quando o apontamento é concluído. | WebService Apontamento/ApontamentoComponente.lsp |
| USU_LOGPRC | USU_TPALWMS | UPDATE | Log do processo do palete WMS, indicando leitura ou apontamento pelo APONTAR-COMPONENTE. | WebService Apontamento/ApontamentoComponente.lsp |
| USU_CODCMP | USU_TBXACMP | INSERT | Código do componente cuja baixa ficou pendente no apontamento. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_CODCRE | USU_TBXACMP | INSERT | Centro de recurso associado à pendência de baixa. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_CODEMP | USU_TBXACMP | INSERT | Empresa da pendência de baixa de componente registrada pelo webservice de apontamento. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_CODETG | USU_TBXACMP | INSERT | Etapa da OP vinculada à pendência de baixa de componente. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_CODORI | USU_TBXACMP | INSERT | Origem da OP vinculada à pendência de baixa de componente. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_DATLOG | USU_TBXACMP | INSERT | Data de gravação do registro de pendência. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_HORLOG | USU_TBXACMP | INSERT | Hora de gravação do registro de pendência. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_DATMOV | USU_TBXACMP | INSERT | Data do movimento usado para registrar a pendência de baixa. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_HORMOV | USU_TBXACMP | INSERT | Hora de gravação do registro de pendência. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_DERCMP | USU_TBXACMP | INSERT | Derivação do componente cuja baixa ficou pendente no apontamento. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_INDSTS | USU_TBXACMP | INSERT | Indicador de status da pendência; os webservices gravam 1 para baixa manual/assíncrona pendente. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_LOGPRC | USU_TBXACMP | INSERT | Log/processo de origem usado para rastrear a geração da pendência. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_CODLOT | USU_TBXACMP | INSERT | Lote que sera Consumido à pendência de baixa. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_LOTDES | USU_TBXACMP | INSERT | Lote destino/apontado associado à pendência de baixa. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_NUMORP | USU_TBXACMP | INSERT | Número da OP vinculada à pendência de baixa de componente. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |
| USU_QTDUTI | USU_TBXACMP | INSERT | Quantidade utilizada que deve ser baixada posteriormente. | WebService Apontamento/Apontamentos.lsp, WebService Apontamento/AumentarApontamento.lsp |

## USU_TESTCMP: pendências ERP de estorno de componente

`DiminuirApontamento.lsp` grava uma linha por componente estornado, dentro da mesma transação dos acertos do lote. A chave primária é `USU_IDEUNI`, gerada com `ObterGuid`; `USU_SITPEN=1` representa pendência para o job ERP posterior. O job consumidor ainda não integra esta etapa e não deve ser inferido aqui.

| Campo | Uso na regra |
|---|---|
| `USU_IDEUNI` | Chave primária GUID da pendência. |
| `USU_CODEMP`, `USU_CODORI`, `USU_NUMORP`, `USU_CODETG` | Chave da OP/estágio estornado. |
| `USU_CODCMP`, `USU_DERCMP`, `USU_QTDEST` | Componente, derivação e quantidade calculada para estorno. |
| `USU_CODPRO`, `USU_CODDER` | Produto e derivação produzidos pela OP. |
| `USU_DATFIM`, `USU_LOGINC` | Data e contexto operacional da redução. |
| `USU_CODTNS` | Reservado para a transação do processamento posterior; a gravação inicial preserva o valor vazio do fluxo legado. |
| `USU_USUPRC`, `USU_DATPRC`, `USU_HORPRC` | Usuário, data e hora de criação da pendência. |
| `USU_SITPEN` | Situação inicial `1` (pendente). |
