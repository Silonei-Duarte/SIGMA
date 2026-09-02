---
titulo: Aplicativo mobile
ordem: 4
---

### 3.6 Aplicativo Android

O aplicativo Android interno fica em `mobile/` e usa Capacitor `8.4.2`. Ele funciona como contêiner do SIGMA web e carrega somente `https://sigma.indaialpapel.com.br`; tráfego HTTP em texto claro permanece desativado e os logs do Capacitor ficam desabilitados. Como as telas são entregues pelo Django, mudanças nas páginas e regras do SIGMA entram em vigor sem gerar outro APK. Uma nova compilação é necessária quando mudar a configuração ou a camada nativa do aplicativo. A versão atual do APK é `1.0.4` (`versionCode` 5).

Configuração atual:

| Item | Valor |
|---|---|
| App ID | `br.com.indaialpapel.sigma` |
| Nome | `SIGMA` |
| Ícone | Logo IPEL de `static/images/logo.png` |
| Capacitor | `8.4.2` |
| Android mínimo | API 24 / Android 7 |
| Android alvo | API 36 |
| URL | `https://sigma.indaialpapel.com.br` |
| Cleartext | Desativado |
| Backup do aplicativo | Desativado |
| Versão | `1.0.4` (`versionCode 5`) |
| Permissões Android | Internet, câmera, localização aproximada/exata, notificações e leitura de imagens |

O dispositivo precisa resolver o domínio pelo DNS interno e acessar a faixa corporativa `172.16.0.0/16`, diretamente ou pela VPN corporativa.

As permissões sensíveis não são solicitadas ao abrir o aplicativo. O Android apresenta a confirmação somente quando uma função do SIGMA tentar usar câmera, localização, notificações ou leitura direta de imagens. A câmera é um recurso opcional e não restringe a instalação em dispositivos sem esse hardware. Galeria e arquivos também podem usar o seletor nativo do Android, sem conceder acesso amplo ao armazenamento. A declaração no manifesto apenas prepara o aplicativo; cada recurso ainda precisa ser implementado na página ou na camada nativa que irá utilizá-lo.

Os arquivos gerados pelo SIGMA, como os PDFs de QR Code da manutenção, são tratados pela camada nativa. O aplicativo repassa ao gerenciador de downloads do Android a URL HTTPS, o cookie da sessão autenticada e o agente do navegador. O arquivo recebe um horário no nome para evitar colisões, fica na pasta pública **Downloads** e o Android informa quando o download termina. Links que usam nova aba no navegador são abertos no próprio WebView quando executados pelo aplicativo, permitindo que esse tratamento seja acionado.

#### 3.6.1 Modelo do aplicativo e mapa de arquivos

O APK não contém uma cópia das telas do SIGMA. O Capacitor abre a aplicação web de produção definida em `mobile/capacitor.config.ts`; por isso, mudanças em templates, views e regras Django são publicadas no servidor e entram no aplicativo sem recompilar o APK. Uma nova versão do APK é necessária quando mudar configuração nativa, permissões, plugins, ícone, App ID, versão Android ou projeto Firebase do aplicativo.

A pasta `mobile/` pertence ao código-fonte usado para gerar o APK e não precisa existir em `/opt/SIGMA` no servidor de produção. O servidor executa o backend Django, guarda a credencial de envio em `/etc/sigma/firebase-admin.json` e mantém o APK disponível para usuários autenticados em `/opt/SIGMA/artifacts/SIGMA.apk`. A estrutura equivalente em desenvolvimento é `artifacts/SIGMA.apk`.

| Arquivo | Responsabilidade |
|---|---|
| `mobile/capacitor.config.ts` | App ID, nome, URL HTTPS, logs e comportamento dos plugins |
| `mobile/package.json` | Capacitor `8.4.2`, Push Notifications `8.1.2` e comandos de build |
| `mobile/android/build.gradle` | Android Gradle Plugin e Google Services `4.5.0` |
| `mobile/android/app/build.gradle` | versão, APIs Android e assinatura release |
| `mobile/android/app/src/main/AndroidManifest.xml` | permissões e requisitos de hardware |
| `mobile/android/app/google-services.json` | identifica o aplicativo Android no projeto Firebase |
| `mobile/build-release.ps1` | sincroniza o Capacitor, assina e atualiza `mobile/dist/SIGMA.apk` e `artifacts/SIGMA.apk` |
| `mobile/keystore/sigma-release.jks` | chave permanente usada para assinar todas as versões release |
| `artifacts/SIGMA.apk` | arquivo entregue pela view autenticada de notificações; ignorado pelo Git |

`mobile/android/app/google-services.json`, a chave Firebase do servidor, o keystore, suas senhas e o APK gerado ficam fora do Git. O `google-services.json` identifica o aplicativo, mas não autoriza o envio de mensagens. A autorização de envio pertence exclusivamente à conta de serviço instalada no servidor.

#### 3.6.2 Arquitetura das notificações

O projeto Firebase é `sigma-f611c` e o aplicativo Android registrado usa o pacote `br.com.indaialpapel.sigma`. O cliente usa `@capacitor/push-notifications`; o servidor usa `firebase-admin` `7.5.0`.

```text
Aplicativo Android autenticado
  -> solicita permissão somente após ação do usuário
  -> Google Play Services gera o token FCM do aparelho
  -> POST autenticado e protegido por CSRF registra o token no Django
  -> tabela dispositivos_notificacao associa token e usuário

Regra de negócio no Django
  -> enviar_notificacao_usuario(usuario, título, mensagem, dados)
  -> Firebase Admin autentica com a conta de serviço do servidor
  -> FCM entrega a mensagem ao token ativo do usuário
  -> Android exibe a notificação no canal sigma_geral
```

Componentes do backend:

| Arquivo | Responsabilidade |
|---|---|
| `accounts/models/notificacoes.py` | modelo `DispositivoNotificacao` |
| `accounts/migrations/0018_dispositivonotificacao.py` | criação da tabela `dispositivos_notificacao` |
| `accounts/views/utilitarios.py` | página de utilitários, download autenticado do APK, registro do token, envio de notificação de teste e envio de e-mail de teste |
| `accounts/services/notificacoes.py` | inicialização do Firebase Admin e função central de envio |
| `templates/accounts/utilitarios.html` | autorização, registro e teste no Android, download do APK e teste de envio de e-mail |
| `SIGMA/settings.py` | leitura de `FIREBASE_CREDENTIALS_FILE` e `SIGMA_APK_FILE` |

Rotas atuais:

| Rota | Método | Função |
|---|---|---|
| `/notificacoes/teste/` | `GET` autenticado | abre a tela de teste |
| `/notificacoes/apk/` | `GET` autenticado | baixa o APK atual como `SIGMA.apk` |
| `/notificacoes/dispositivos/registrar/` | `POST` autenticado com CSRF | associa o token ao usuário conectado |
| `/notificacoes/teste/enviar/` | `POST` autenticado com CSRF | envia mensagem fixa apenas ao próprio usuário |

Tokens FCM são únicos. Um novo registro atualiza o proprietário e reativa o dispositivo. Tokens rejeitados pelo FCM como não registrados ou pertencentes a outro projeto são marcados como inativos. O sistema não expõe chave privada, token ou escolha livre de destinatário ao navegador.

#### 3.6.3 Configuração do Firebase e do servidor

Para reconstruir a integração ou preparar outro ambiente:

1. No Firebase, usar o projeto `sigma-f611c` e manter cadastrado o aplicativo Android `br.com.indaialpapel.sigma`.
2. Baixar o `google-services.json` desse aplicativo e colocá-lo em `mobile/android/app/google-services.json`.
3. Gerar uma chave JSON para a conta de serviço utilizada pelo Firebase Admin.
4. Instalar a chave somente no servidor, fora de `/opt/SIGMA`, com proprietário `nexus` e permissão `600`:

```bash
sudo install -o nexus -g nexus -m 600 serviceAccountKey.json /etc/sigma/firebase-admin.json
```

5. Manter em `/etc/sigma/sigma.env`:

```dotenv
FIREBASE_CREDENTIALS_FILE=/etc/sigma/firebase-admin.json
SIGMA_APK_FILE=/opt/SIGMA/artifacts/SIGMA.apk
```

6. Instalar as dependências bloqueadas, aplicar a migração e reiniciar o serviço:

```bash
cd /opt/SIGMA
/home/nexus/.local/bin/uv sync --frozen
.venv/bin/python manage.py migrate accounts --noinput
sudo systemctl restart sigma.service
systemctl is-active sigma.service
```

Ao substituir a conta de serviço, repetir a instalação do arquivo com permissão `600` e reiniciar `sigma.service`. Nunca copiar essa chave para `mobile/android/app`, para o APK, para o Git ou para uma tela do sistema.

Para entregar notificações, o servidor SIGMA precisa de acesso de saída à internet por HTTPS, porta `443`, para os serviços Firebase/Google, e o dispositivo Android precisa de internet e dos serviços Google Play. Não é necessário publicar o SIGMA na internet nem liberar porta de entrada no firewall: as mensagens partem do servidor para o Firebase e são entregues ao celular pela conexão mantida pelo Google. O acesso às páginas do SIGMA continua restrito à rede corporativa ou VPN; sem internet a notificação fica pendente até o dispositivo recuperar conectividade.

#### 3.6.4 Teste e novos disparos

O botão de chave inglesa (🔧) no cabeçalho abre `https://sigma.indaialpapel.com.br/utilitarios/`. A página oferece o download autenticado da versão atual do APK. Quando aberta pelo aplicativo Android, o botão **Ativar e enviar teste** solicita a permissão, registra o token e envia `Teste do SIGMA` somente para os aparelhos ativos do usuário conectado. O navegador comum pode baixar o APK e abrir a página, mas não possui o plugin nativo e não registra dispositivo. A mesma página também tem um teste de envio de e-mail (ver 6.8), útil para validar rapidamente se o backend Microsoft Graph está enviando sem precisar de um evento operacional real.

Nenhum evento operacional dispara notificação automaticamente. Para adicionar um disparo, chamar o serviço no ponto da regra de negócio, passando um objeto de usuário obtido e validado pelo servidor:

```python
from accounts.services.notificacoes import enviar_notificacao_usuario

enviar_notificacao_usuario(
    usuario=responsavel,
    titulo="Título da notificação",
    mensagem="Mensagem apresentada no Android",
    dados={"tipo": "identificador_do_evento"},
)
```

Não criar endpoint que aceite livremente token, destinatário, título ou mensagem enviados pelo navegador. Views, signals e workers devem determinar o destinatário no backend e chamar a função central. Um novo disparo Django não exige outro APK; recompilar apenas quando o comportamento nativo de recebimento ou abertura precisar mudar.

#### 3.6.5 Geração e assinatura do APK

Para instalar dependências, sincronizar a plataforma Android e gerar o APK de produção assinado pelo terminal:

```powershell
cd mobile
npm install
npm run apk:release
```

O script `mobile/build-release.ps1` lê `SIGMA_KEYSTORE_PASSWORD` do arquivo `.env` na raiz do projeto, configura o JDK e o Android SDK locais, executa `npx cap sync android`, compila com Gradle e copia o mesmo APK para:

```text
mobile/dist/SIGMA.apk
artifacts/SIGMA.apk
```

Depois de gerar uma nova versão, enviar `artifacts/SIGMA.apk` para `/opt/SIGMA/artifacts/SIGMA.apk`. A view `baixar_apk_sigma` lê `SIGMA_APK_FILE`, exige usuário autenticado e responde o arquivo como anexo `SIGMA.apk`; o APK não passa pelo diretório `static` nem pelo `collectstatic`.

O APK de produção é assinado pela chave `mobile/keystore/sigma-release.jks`, alias `sigma`, RSA 4096, válida até 07/12/2053. A chave e sua senha não são versionadas e devem ser preservadas em armazenamento seguro externo ao repositório. Todas as atualizações precisam usar essa mesma chave. Em cada nova versão, incrementar o `versionCode`, ajustar o `versionName` quando necessário e executar novamente `npm run apk:release`.

O `.env` local e o arquivo de ambiente de produção contêm a variável em texto cru e não são versionados. Para preparar outra máquina, copiar o mesmo keystore e configurar:

```dotenv
SIGMA_KEYSTORE_PASSWORD=senha-da-chave
```

A variável de ambiente do processo, quando definida, tem prioridade sobre o `.env`. A produção mantém a mesma variável no arquivo de ambiente para centralizar a configuração, embora a assinatura e a geração do APK sejam executadas na máquina de desenvolvimento.

---

*Verificado contra o código em 2026-08-19.*
