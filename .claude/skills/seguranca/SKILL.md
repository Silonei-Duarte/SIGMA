---
name: seguranca
description: O padrão de segurança do SIGMA para quem escreve e para quem revisa código — o modelo de ameaça do ambiente (rede corporativa, senha de domínio no login, credencial de Oracle/Sapiens/WMS/Firebase, código gerado por IA), as regras por camada, os padrões que denunciam vulnerabilidade e o procedimento de revisão com escala de severidade. Use antes de dar por pronta qualquer view, formulário, integração ou configuração, e em toda revisão de segurança. Dispara em "segurança", "vulnerabilidade", "brecha", "OWASP", "injeção", "XSS", "CSRF", "SSRF", "autorização", "autenticação", "segredo", "credencial", "está seguro?".
paths: "accounts/** SIGMA/settings.py **/views/** **/forms.py"
---

# Segurança no SIGMA

O SIGMA autentica com a senha de domínio de cada pessoa (Active Directory),
guarda credencial de Oracle (ERP e Alchemy), do Sapiens, da API do WMS e a
conta de serviço do Firebase, e decide o que cada operador vê e altera na
produção. Boa parte do código é escrita por uma IA orientada por quem não
necessariamente programa. Este documento é o padrão que o agente
`seguranca` aplica na revisão e que o agente `backend`/`integracoes` segue
ao escrever.

## Modelo de ameaça

- **Rede**: aplicação roda na rede corporativa (`172.16.0.0/16` e VPN),
  atrás de Nginx, servida por Daphne. Não é exposta à internet pública.
- **Identidade**: login é a conta de domínio real da pessoa via LDAP —
  uma sessão comprometida no SIGMA é uma sessão de domínio sendo usada
  indevidamente.
- **Dado sensível guardado**: credencial de Oracle, Sapiens, WMS, LDAP
  (`LDAP_CA_CERT_FILE`, bind), conta de serviço do Firebase
  (`/etc/sigma/firebase-admin.json`), chave secreta do Django.
- **Superfície maior**: formulário de apontamento/qualidade/manutenção
  (entrada de operador de chão de fábrica, nem sempre técnico), views que
  fazem query Oracle direta com parâmetro vindo de tela, integrações que
  recebem retorno de sistema externo e confiam nele.
- **Decisão já registrada, não é achado**: LDAP sobre `ldaps://` (TLS) já
  é a configuração; a superfície aceita é a rede interna/VPN corporativa
  — não é achado dizer "a aplicação não está atrás de WAF público".

## Regras por camada

**View**

- Toda view que expõe dado de produção/qualidade exige
  `@login_required`. Se a tela é restrita a um papel, a checagem de
  `is_staff`/`is_superuser`/grupo precisa **existir e ser consistente**
  com telas equivalentes do mesmo app — a ausência da checagem, não a
  ausência de um decorator formal, é o achado (o projeto não usa
  decorator de permissão hoje; ver `backend-sigma`).
- Ação que altera estado (apontar, liberar lote, estornar) é `POST`,
  nunca `GET`.
- Autorização é sobre o objeto: não basta esconder botão ou filtrar a
  listagem. POST, JSON, detalhe, impressão e exclusão recebem o mesmo
  escopo de empresa/filial do usuário não-staff.
- Todo formulário que altera estado contém `{% csrf_token %}`; endpoint
  JSON autenticado mantém a proteção CSRF ou documenta o mecanismo
  equivalente.

**Entrada**

- `Form`/`ModelForm` sempre; `request.POST`/`GET` cru não desce para
  query Oracle nem para chamada SOAP/REST.
- Parâmetro de usuário em SQL (Oracle) é sempre bind variable
  (`cursor.execute(sql, {"param": valor})`), nunca f-string/concatenação
  — é o vetor de injeção mais provável neste projeto, porque há consulta
  Oracle direta em muitos arquivos (ver `backend-sigma`/`integracoes`).

**Template**

- `{{ }}` do Django já escapa; `|safe`/`mark_safe` só sobre dado que o
  próprio código gerou, nunca sobre nome de cliente, observação de
  usuário ou retorno de sistema externo.

**Sessão e autenticação**

- Login é sempre via `AUTHENTICATION_BACKENDS`
  (`django_auth_ldap.backend.LDAPBackend` + `ModelBackend`); não escrever
  bind LDAP manual paralelo numa view.
- `AUTH_PASSWORD_VALIDATORS` (`accounts/validators.py`) não é
  enfraquecido "para facilitar teste".
- Configuração de sessão/cookie permanece em `SIGMA/settings.py`: não
  desligar `HttpOnly`, `SameSite` ou proteção HTTPS para simplificar uma
  tela.

**Arquivos e erros**

- Upload valida tipo, tamanho e nome gerado; não usa nome fornecido pela
  pessoa como caminho nem serve arquivo privado diretamente.
- Exceção de banco, Oracle, SOAP ou HTTP vai ao log do servidor; tela e JSON
  retornam mensagem genérica, sem `str(exc)`.
- Mensagem de erro visível (tela, JSON, e-mail de falha de login) nunca
  revela se uma conta/login existe, caminho de arquivo do servidor, versão
  de pacote instalado ou stack trace — inclusive em "usuário ou senha
  inválidos" (não diferenciar "usuário não existe" de "senha errada") e em
  página de erro 500/404 customizada.

**Integração**

- Credencial só em `.env`/`/etc/sigma/sigma.env`, lida via `os.getenv()`
  em `SIGMA/settings.py`. Nunca em código, log, exceção, teste, commit.
- Log de payload SOAP/REST mascara token, senha e cabeçalho de
  autenticação.
- TLS nunca desligado (`verify=False` em `requests`, certificado LDAP
  ignorado) sem decisão explícita do sênior registrada em documento.
- URL HTTP não vem de formulário. Se a integração aceitar URL configurável,
  valida protocolo, host, porta, redirects e destino resolvido para evitar
  SSRF.

**Segredo**

- `SECRET_KEY`, credencial de Oracle/Sapiens/WMS/LDAP, chave do Firebase:
  nunca hardcoded, nunca em teste, nunca em exceção que pode aparecer em
  log.
- **Máscara de segredo converge para UM helper único** — casa planejada:
  `SIGMA/segredos.py` (ainda inexistente). Texto de origem desconhecida
  — erro de SMTP, Oracle, LDAP, Firebase, exceção de banco — não vai a
  log, tela ou e-mail sem passar por máscara. Enquanto o helper único
  não existe, use as máscaras por transporte já existentes
  (`mascarar_credenciais_soap_sapiens`, em `producao/utils/sapiens_soap.py`;
  `mascarar_url_coleta`, em `telemetria/validacao_http.py`) e **não crie
  uma terceira máscara dispersa**.

## Padrões que denunciam (grep rápido)

| Padrão | Onde procurar | Por quê |
|---|---|---|
| `oracledb.connect(` fora de `SIGMA/settings.py` | views/services | reautentica com credencial fora do fluxo único |
| `f"...{` seguido de `SELECT`/`WHERE`/`cursor.execute` | qualquer query Oracle | injeção SQL |
| `\|safe`, `mark_safe(` | templates | XSS se o dado vier de fora |
| `verify=False` | chamadas `requests` | TLS desligado |
| `os.getenv(` fora de `SIGMA/settings.py` | qualquer app | segredo/config espalhado, difícil de auditar |
| senha/token literal em string | qualquer arquivo, inclusive teste | segredo hardcoded |
| view sem `@login_required` que renderiza dado de produção/qualidade | `views/` | acesso sem autenticação |
| `innerHTML` com texto externo | templates JavaScript | XSS de DOM persistente |
| `JsonResponse(error=str(exc))` ou mensagem com `{exc}` | views/services | detalhe interno exposto ao usuário |
| mensagem que distingue "usuário não encontrado" de "senha inválida" | login, recuperação de senha | enumeração de conta |

## Escala de severidade

- **Crítico**: segredo exposto (commit, log, template), acesso sem
  autenticação a dado de produção/qualidade, injeção SQL confirmada,
  escalada para `is_superuser`.
- **Alto**: autorização inconsistente entre telas equivalentes, XSS
  confirmado com dado externo, TLS desligado sem decisão registrada.
- **Médio**: falta de timeout em integração (pode virar negação de
  serviço interna), retentativa de escrita com desfecho desconhecido.
- **Baixo/observação**: estilo, o que não é achado de segurança — vai
  para o `revisor`.

## Referências

| Arquivo | Quando ler |
|---|---|
| [references/revisao.md](references/revisao.md) | procedimento passo a passo de revisão de segurança |
