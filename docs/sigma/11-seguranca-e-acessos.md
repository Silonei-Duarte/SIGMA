---
titulo: Segurança e acessos
ordem: 11
---

## 10. Segurança e acessos

O SIGMA tem dois níveis principais de segurança: autenticação e autorização. Autenticação responde "quem e o usuário?". Autorização responde "o que esse usuário pode fazer?".

### 10.1 Autenticação

O login usa LDAP/Active Directory como primeira opcao e o backend Django como apoio. O uso de LDAPS com certificado CA protege a comunicação com o controlador de dominio.

O fallback para a senha local (backend Django) é controlado, não automático:
`AUTHENTICATION_BACKENDS` usa `accounts.auth_backends.LDAPBackendComFallbackControlado`
em vez do `LDAPBackend` puro. Quando o AD responde de forma autoritativa que a
credencial é inválida — senha errada, ou conta desativada/bloqueada/expirada
(o Active Directory usa o mesmo código de erro para todos esses casos) —, o
login é recusado ali mesmo e a senha local nunca chega a ser testada. A senha
local só entra em jogo quando o AD genuinamente não respondeu (indisponível) ou
quando o usuário não existe nele. Essas duas situações ficam registradas no
logger `accounts.ldap` (`SIGMA/settings.py::LOGGING`): nível `INFO` para
"usuário não encontrado no AD", nível `WARNING` para indisponibilidade —
níveis diferentes de propósito, para que uma queda real do AD não fique
escondida atrás do volume normal de "usuário não encontrado". Testes em
`accounts/tests/test_auth_backends.py`.

Quando um usuário permitido entra pela primeira vez, o SIGMA pode criar o cadastro local automaticamente. Esse cadastro local e necessário para vincular filial, operador ERP, permissões e histórico de ações.

### 10.2 Autorização

Depois do login, as telas e ações usam permissões. Algumas telas exigem apenas usuário autenticado; outras exigem permissão especifica de produção, qualidade ou manutenção. Ações de maior risco, como excluir filas pendentes ou registros não integrados, são restritas a superusuario ou staff conforme o caso.

Na tela de apontamento, a permissão **Pode apontar** (`producao.pode_apontar`) libera a validação de operador, a troca de operador, a troca de OP ativa e o apontamento. O desacoplamento da OP ativa exige que o operador tenha sido validado na tela. As telas de apontamento (a base e as versões v1, v2 e v3) ficam acessíveis a qualquer usuário autenticado — qual versão carrega depende do cadastro do recurso; as ações internas das versões são negadas na própria tela quando o usuário não aponta. As rotas de ação separadas (justificar paradas, encerrar paradas, desacoplar OP ativa e abrir parada manual) exigem **Pode apontar** no acesso pelo decorator comum; o escopo por empresa continua resolvido no corpo da view (usuário sem filial ou com empresa diferente não alcança o recurso).

Essa separação impede que um usuário operacional comum acesse manutenção administrativa, cadastros sensíveis ou operações de reprocessamento indevidas.

No Sequenciamento, o acesso à tela e ao menu exige `Pode acessar Sequenciamento`; consolidar ou executar o sequenciamento automático exige `Pode consolidar Sequenciamento ERP`. Essas são as únicas permissões do módulo exibidas na administração de usuários e grupos.

Em Produção, usuário não-staff só consulta e opera recursos da empresa da sua filial. Staff mantém escopo global; usuário sem filial não recebe dados operacionais. As ações que modificam filas, paradas e sequenciamentos exigem POST com proteção CSRF.

A mesma política de escopo vale para Qualidade, PCP, Manutenção, Logística e
Suprimentos: o backend resolve empresa e recurso a partir da filial antes de
consultar ou alterar registros. Usuário sem filial recebe lista vazia ou negação
conforme a rota; valores enviados pela requisição não ampliam o escopo. Nas telas
de manutenção, grupos nomeados definem observadores e responsáveis; IDs fixos de
grupo não são usados como regra de autorização.

No PCP, o Calendário de OPs exige a permissão **Pode visualizar Calendário de OPs** (`pcp.pode_visualizar_calendario_ops`), atribuível diretamente ao usuário ou por grupo. Usuários staff também possuem acesso.

Em Logística, o painel de Componentes a Movimentar e suas consultas JSON exigem **Pode visualizar Componentes a Movimentar** (`logistica.pode_visualizar_componentes_movimentar`). Em Suprimentos, a tela Componentes a Separar exige **Pode visualizar Componentes a Separar** (`suprimentos.pode_visualizar_componentes_separar`).

Em Manutenção, as telas de chamados — lista, abertura, detalhe, exclusão e os QR codes de recursos — exigem **Pode acessar chamados** (`manutencao.pode_acessar_chamados`); as telas de ordens de serviço exigem **Pode acessar OS** (`manutencao.pode_acessar_os`). Excluir ou editar chamados exige também **Pode manipular chamados** (`manutencao.pode_manipular_chamados`); abrir, editar ou excluir OS exige **Pode manipular OS** (`manutencao.pode_manipular_os`). As permissões **Pode listar todos os chamados** (`manutencao.pode_listar_todos_chamados`) e **Pode listar todas as OS** (`manutencao.pode_listar_todas_os`) não liberam rota: apenas ampliam o que é listado dentro da própria filial do usuário. A assimetria entre abrir chamado (exige apenas acesso) e abrir OS (exige acesso + manipular OS) é intencional, definida com o time responsável.

Em Telemetria, as telas de sensores e fontes HTTP — cadastro, edição, exclusão e a aba de telemetria do cadastro de recursos — exigem **Pode gerenciar sensores** (`telemetria.pode_gerenciar_sensores`), permissão própria do módulo. Sensores e fontes possuem filial própria: usuário não-staff só consulta, edita, exclui e vincula registros da própria filial; staff e superusuário mantêm escopo global, incluindo registros sem filial. Registros existentes tiveram a filial derivada dos vínculos com recursos na migration `telemetria/0008`; os que não tinham vínculo derivável permaneceram sem filial (visíveis só a staff) até atribuição consciente pela administração.

No portal de cadastros do SIGMA (accounts), duas permissões dividem o papel:
**Pode manipular Cadastros** (`accounts.manipular_cadastros`) libera as telas
de empresas, filiais, departamentos, setores, centros de recursos, recursos,
taras, turnos e turno base, calendários e eventos, horas extras planejadas e o
reprocessamento do planejado OEE; **Pode administrar acessos**
(`accounts.administrar_acessos`) é poder de concessão — só ela abre usuários,
edição/cadastro/exclusão de usuário e grupos (incluir quem concede credenciais
na mesma permissão dos cadastros permitiria escalação). As duas nascem por
função pós-migrate. A tela de **Configurações da Aplicação**
(`/configuracoes/`) exige **Pode configurar parâmetros da aplicação**
(`accounts.configurar_aplicacao`), também nascida por função pós-migrate —
separada dos cadastros porque altera o funcionamento de workers e serviços,
não um registro de negócio; a tela é para variáveis não sensíveis e a
rejeição de chaves com nome de segredo vale na gravação e também na leitura
(`obter()`), para que linha gravada por outra via não encontre superfície
que sirva a credencial. O painel `/services/status/` fica restrito a staff
(exposição de infraestrutura); a página inicial exige apenas login; os endpoints
AJAX de cascata e as ferramentas de utilitários (notificações/APK) permanecem de
acesso logado enquanto não forem mapeados. O envio de e-mail de teste é a exceção:
exige **Pode administrar acessos** (`accounts.administrar_acessos`), inclusive no
controle exibido na tela; staff e superusuário mantêm o bypass administrativo.

Em Qualidade, a tela de liberação de lotes exige **Pode acessar a tela de liberação de lotes** (`qualidade.pode_acessar_liberacao_lotes`); destinar lotes nela exige também **Pode destinar lotes na tela de liberação** (`qualidade.pode_destinar_lotes_liberacao`). A tela da área vermelha e suas consultas de apoio (descrição de transformação, etiquetas) exigem **Pode acessar a tela de liberação da área vermelha** (`qualidade.pode_acessar_area_vermelha`); registrar destinação na reunião e buscar usuários ERP exigem **Pode destinar lotes na área vermelha** (`qualidade.pode_destinar_area_vermelha`). A consulta de lote aceita qualquer uma das duas permissões de acesso (`pode_acessar_area_vermelha` ou `pode_acessar_liberacao_lotes`). As observações de etiqueta exigem **Pode cadastrar observações de etiqueta** (`qualidade.pode_cadastrar_observacoes_etiqueta`). A tela de integração WMS e os envios e reenvios manuais ficam abertos a qualquer usuário autenticado: não-staff só consulta e opera pendências da empresa da própria filial, enquanto staff mantém visão e operação global. Excluir pendências WMS exige a permissão unificada `producao.pode_excluir_pendencias_integracao` (ver parágrafo das filas abaixo) e respeita o mesmo escopo por empresa para não-staff. A rota pública de rastreamento de lote (QR da etiqueta) não exige login e é limitada por taxa por IP (30 req/min). **Requisito:** Nginx deve sobrescrever `X-Forwarded-For` (`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`) para que o rate limit use IP confiável — já configurado em produção.

Nas filas de integração de produção (apontamentos, componentes, baixas e tempos ERP), as telas e os envios e reenvios permanecem abertos a qualquer usuário autenticado, com escopo por empresa no corpo da view; a concorrência dos envios é controlada por trava única por fila. Excluir pendências dessas filas exige `producao.pode_excluir_pendencias_integracao` no acesso (staff e superusuário passam pelo bypass do decorator) e continua limitada ao escopo do usuário no corpo da view: não-staff só exclui pendências da própria empresa/recursos visíveis. A fila WMS usa essa mesma permissão unificada de exclusão; a permissão própria de exclusão WMS anterior (`qualidade.pode_excluir_integracao_wms`) foi removida por redundância.

No log de tempo produção (`log-tempo-producao`), a tela fica aberta a qualquer autenticado com dados filtrados pela filial; excluir período produtivo ou parada exige `producao.pode_excluir_pendencias_integracao` (com o mesmo limite de escopo); alterar os horários físicos da parada exige `producao.pode_alterar_paradas`, com staff autorizado pelo bypass; abrir parada manual pelo log também exige `pode_alterar_paradas` — diferente das telas de apontamento, onde abrir parada manual depende de o recurso ter "Permite Parada Manual" (e do `pode_apontar` da rota de ação). Salvar justificativas segue avaliado parada a parada pela regra `alt_just` do recurso somada à permissão/staff.

As rotas privadas de PCP, Logística, Suprimentos, Manutenção, Telemetria, Qualidade e Produção usam o decorator comum `@permissao_requerida()` de `SIGMA/autorizacao.py`: ele exige login, autoriza staff e superusuário e devolve HTTP 403 a usuário autenticado sem a permissão. O decorator aceita uma permissão ou uma sequência de permissões (qualquer uma libera a rota). A permissão libera o acesso à rota; ela não substitui o escopo por empresa/filial, que continua resolvido dentro de cada view (usuário não-staff só consulta a empresa da própria filial, valores enviados na requisição não ampliam o escopo e usuário sem filial recebe lista vazia ou negação conforme a rota). O `handler403` global exibe uma página amigável nas navegações HTML, sem expor a permissão negada; o retorno aceita apenas `Referer` da mesma origem e usa a página inicial como fallback. Requisições JSON e XHR recebem JSON genérico com o mesmo status 403.

### 10.3 Observações de segurança

Pontos de segurança:

- Em produção, o sistema aceita somente o host `sigma.indaialpapel.com.br`.
- O Nginx redireciona o domínio de HTTP para HTTPS e recusa acesso direto pelo IP.
- O Nginx não informa sua versão nem o sistema operacional nos headers HTTP.
- Cookies de sessão e CSRF são enviados somente por HTTPS.
- As senhas ficam em variáveis de ambiente, o que é adequado.
- Este documento não registra senhas nem usuários técnicos.
- URLs de Telemetria são limitadas por allowlist, sem redirects ou credenciais
  embutidas, e respostas HTTP possuem limite de tamanho.
- Erros de Oracle, ORM, HTTP e SOAP são registrados no servidor; páginas e JSON
  expõem somente mensagens genéricas.

Todo texto de origem desconhecida que siga para log, tela ou e-mail passa por
`mascarar_segredos()`, em `SIGMA/segredos.py`. O helper centraliza a substituição
dos valores de segredo conhecidos pela aplicação e agrega as máscaras já próprias
do envelope SOAP e das URLs de telemetria. As máscaras dos transportes continuam
nos seus módulos de origem; a chamada central é a proteção comum antes de o texto
ser persistido, exibido ou enviado.

O HTTPS termina no Nginx, que encaminha `X-Forwarded-Proto` ao Django. A aplicação reconhece a requisição original como segura por `SECURE_PROXY_SSL_HEADER`.

#### 10.3.1 HTTPS e renovação do certificado

O Nginx publica o SIGMA somente em `https://sigma.indaialpapel.com.br`. O domínio em HTTP redireciona para HTTPS; requisições pelo IP são recusadas. O Daphne escuta apenas em `127.0.0.1:8000`, sem exposição direta da aplicação na rede.

O domínio resolve no DNS interno para `172.16.30.63` e não possui resolução nos servidores DNS públicos. O firewall do servidor aceita HTTP e HTTPS somente quando o endereço de origem pertence à faixa corporativa `172.16.0.0/16`; as demais origens são bloqueadas. O acesso pela VPN corporativa depende de o tráfego chegar ao servidor por essa faixa autorizada.

O certificado em uso é coringa para `*.indaialpapel.com.br`, emitido pela Let's Encrypt, com validade até 10/09/2026. Os arquivos ativos ficam em:

```text
/etc/ssl/sigma/cert.pem
/etc/ssl/sigma/chain.pem
/etc/ssl/sigma/fullchain.pem
/etc/ssl/sigma/privkey.pem
```

O Nginx usa `fullchain.pem` em `ssl_certificate` e `privkey.pem` em `ssl_certificate_key`. O PFX recebido da infraestrutura é usado somente durante a conversão e não permanece no servidor depois da instalação.

Para consultar o certificado publicado e sua validade:

```bash
openssl s_client \
  -connect sigma.indaialpapel.com.br:443 \
  -servername sigma.indaialpapel.com.br </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

Antes do vencimento, solicitar à infraestrutura um novo PFX coringa e sua senha. Enviar o arquivo temporariamente para `/home/nexus/certificado_sigma.pfx` e executar:

```bash
install -d -m 700 /tmp/sigma-cert
read -s -p "Senha do PFX: " PFX_PASSWORD
export PFX_PASSWORD

openssl pkcs12 \
  -in /home/nexus/certificado_sigma.pfx \
  -passin env:PFX_PASSWORD -clcerts -nokeys 2>/dev/null \
  | openssl x509 -out /tmp/sigma-cert/cert.pem

openssl pkcs12 \
  -in /home/nexus/certificado_sigma.pfx \
  -passin env:PFX_PASSWORD -cacerts -nokeys 2>/dev/null \
  | awk '/-----BEGIN CERTIFICATE-----/{p=1} p{print} /-----END CERTIFICATE-----/{p=0}' \
  > /tmp/sigma-cert/chain.pem

openssl pkcs12 \
  -in /home/nexus/certificado_sigma.pfx \
  -passin env:PFX_PASSWORD -nocerts -nodes 2>/dev/null \
  | openssl pkey -out /tmp/sigma-cert/privkey.pem

unset PFX_PASSWORD
cat /tmp/sigma-cert/cert.pem /tmp/sigma-cert/chain.pem \
  > /tmp/sigma-cert/fullchain.pem

openssl x509 -in /tmp/sigma-cert/cert.pem \
  -noout -subject -issuer -dates -ext subjectAltName
openssl verify -untrusted /tmp/sigma-cert/chain.pem \
  /tmp/sigma-cert/cert.pem

sudo install -o root -g root -m 644 \
  /tmp/sigma-cert/cert.pem \
  /tmp/sigma-cert/chain.pem \
  /tmp/sigma-cert/fullchain.pem \
  /etc/ssl/sigma/
sudo install -o root -g root -m 600 \
  /tmp/sigma-cert/privkey.pem \
  /etc/ssl/sigma/privkey.pem

sudo nginx -t && sudo systemctl reload nginx
rm -f /home/nexus/certificado_sigma.pfx
rm -rf /tmp/sigma-cert
```

Depois da recarga, executar novamente a consulta do certificado publicado e confirmar o novo período de validade e o nome `*.indaialpapel.com.br`.

---

*Verificado contra o código em 2026-08-29.*
