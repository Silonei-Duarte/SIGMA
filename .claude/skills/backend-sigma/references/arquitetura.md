# Arquitetura do SIGMA — mapa detalhado

Este arquivo lista exemplares reais, classificados como **bom** (copie a
forma) ou **legado** (existe, funciona, mas não é para replicar em código
novo). A classificação existe porque o SIGMA não teve revisão de
arquitetura em tempo real por um bom tempo — ver "O que existe hoje" em
`../SKILL.md`.

## Apps e como estão organizados

| App | O que cobre | Organização |
|---|---|---|
| `accounts` | login, LDAP/AD, cadastro (empresa, filial, departamento, setor, centro de recurso, recurso, calendário, turnos, horas extras), notificações push | pacotes `models/`, `views/`, `services/`, `utils/`; o `models.py` de raiz (stub do `startapp`) foi removido em 2026-08-27 |
| `producao` | sequenciamento, apontamento de OP e componente, status de recurso | pacotes `models/`, `services/`, `utils/`; `views/` é pacote e o `views.py` de raiz (stub do `startapp`) foi removido em 2026-08-27; `views/__init__.py` só reexporta 3 dos ~12 módulos — os demais entram direto em `producao/urls.py` |
| `setores/qualidade`, `setores/manutencao`, `setores/pcp`, `setores/logistica`, `setores/suprimentos` | um app Django por área de negócio, mesmo padrão de pacotes | confira `views/__init__.py` de cada um antes de assumir que reexporta tudo |
| `telemetria` | coleta HTTP JSON, WebSocket da balança, OEE planejado | mesmo padrão; é o único app com `TextChoices` real (`TipoValor`) |
| `SIGMA` | settings, urls raiz, asgi/wsgi | configuração do projeto, não um app de domínio |
| `theme` | Tailwind (django-tailwind) | `theme/static_src/src/styles.css` é a fonte dos tokens — skill `interface-sigma` |

## Models — exemplares de máquina de estado

- **Bom, mas ainda por adotar em massa**: `producao/models/estrutura.py`,
  classe `PacoteTempoERP` — constantes de classe nomeadas
  (`STATUS_PENDENTE`, `STATUS_ENVIADO`, ...) e `STATUS_CHOICES` explícito.
  Mais claro que inteiro cru, mas ainda não é `TextChoices`.
- **Alvo real**: `telemetria/models/estrutura.py`, classe interna
  `TipoValor(models.TextChoices)`. É o único lugar do projeto no idioma
  Django atual para catálogo. Catálogo novo nasce assim.
- **Legado, não copiar em model novo**: `producao/models/estrutura.py`,
  classes `Apontamento`, `ApontamentoComponente`, `BaixaComponente` —
  campo `status = models.IntegerField(default=0)` com
  comentário `# 0: Não integrado, 1: Integrado, ...` e nenhum `choices`.
  Ler e entender é necessário (é a fila de integração real); reproduzir a
  forma, não.

## Views — exemplares

- **Autenticação/LDAP**: `accounts/views/auth.py` —
  `PaginaInicialLoginView(LoginView)` com `dispatch()` e
  `get_success_url()` próprios, mais a função `home()` com
  `@login_required`. O bind LDAP em si não tem view: é
  `AUTHENTICATION_BACKENDS` em `SIGMA/settings.py`
  (`django_auth_ldap.backend.LDAPBackend`).
- **Autorização de rota nova**: `SIGMA/autorizacao.py` fornece
  `@permissao_requerida()`, com bypass de staff/superusuário e HTTP 403 para
  usuário autenticado sem permissão. Views legadas continuam function-based e
  podem ter checagem manual; o filtro de empresa/filial/ownership permanece
  obrigatório mesmo após aplicar o decorator.
- **Function-based é o padrão dominante** no projeto inteiro; class-based
  view é exceção (só a de login).

## Onde fica o código de integração

| Sistema | Protocolo/helper | Quem chama de fato |
|---|---|---|
| Oracle ERP / Alchemy | `SIGMA.integracoes.oracle` sobre os aliases Django | `cursor_oracle_erp()` e `cursor_oracle_alchemy()` centralizam cursor e conexão |
| SOAP Sapiens | `producao.services.sapiens` + `producao/utils/sapiens_soap.py` | `enviar_soap_sapiens()` centraliza transporte; consumidor mantém envelope e regra de negócio do retorno |
| WMS (API) | payload montado em `setores/qualidade/utils/wms_integracao.py` (`montar_sku_wms`, `dados_wms_liberacao_lote`) | `setores/qualidade/views/wms_views.py`, `liberar_lotes.py`, `liberar_area_vermelha.py` via `requests.post`/`get` |
| Telemetria HTTP | `telemetria/services/coleta.py` coleta cada fonte JSON e republica atualizações de `pesoBalanca` via WebSocket | fonte independente; ausência da variável é ignorada |
| LDAP/AD | `django_auth_ldap`, configurado em `SIGMA/settings.py` (`AUTHENTICATION_BACKENDS`, `AUTH_LDAP_*`) | sem bind manual paralelo |

## A fila de integração local — o padrão que funciona

- **Model da fila**: `producao/models/estrutura.py`, classe `Apontamento`
  (campo `status`: 0 não integrado, 1 integrado, 2 processando, 3
  excluído).
- **Worker que processa**: `producao/views/logs_apontamentos.py` —
  `PROCESSAMENTO_LOGS_LOCK`, `SERVICE_CODIGO = "fila_logs_apontamentos"`,
  função `disparar_envio_apontamentos`, que envia por SOAP e atualiza o
  `status`.
- **Agendador central**: `producao/services/envia_pendencias.py`, classe
  `EnviaPendenciasScheduler` — thread daemon que roda a cada 300s e
  dispara, por importação sob demanda, cada worker de fila: apontamentos,
  tempos ERP, componentes, baixas, integrações WMS, consulta de lotes.
- Filas irmãs, mesmo padrão: `PacoteTempoERP` +
  `producao/services/envia_tempos_erp.py`; componentes/baixas em
  `producao/views/logs_apontamento_componentes.py` e
  `logs_baixa_componentes.py`; WMS em
  `setores/qualidade/views/wms_views.py`.

**Regra ao criar fila nova**: siga esse desenho — status na linha, nunca
apagar por falha, worker registrado no `EnviaPendenciasScheduler` (ou
justifique um scheduler próprio no relatório).

## Configuração

- Tudo em `SIGMA/settings.py`. `load_dotenv()` lê `.env` (dev);
  `load_dotenv("/etc/sigma/sigma.env")` lê o arquivo de produção — os dois
  na mesma chamada, o segundo sobrepõe se existir.
- `SECRET_KEY` explode (`ImproperlyConfigured`) se a variável não existir
  — é o padrão a seguir para qualquer credencial obrigatória nova.
- Validador de senha customizado: `accounts/validators.py`
  (`UppercaseValidator`, `LowercaseValidator`, `SymbolValidator`,
  `DigitValidator`), registrado em `AUTH_PASSWORD_VALIDATORS`.
