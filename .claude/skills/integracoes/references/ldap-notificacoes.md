# Active Directory, Firebase e e-mail

## Active Directory (LDAP)

Autenticação é `django_auth_ldap`, configurado em `SIGMA/settings.py`
(`AUTHENTICATION_BACKENDS = ["accounts.auth_backends.LDAPBackendComFallbackControlado",
"django.contrib.auth.backends.ModelBackend"]`). `accounts/auth_backends.py`
existe de novo — revivido em 2026-09-02 de forma preventiva, seguindo o
checklist de `docs/pendencias-producao.md` item 3 (achado real de outro
sistema com o mesmo desenho AD+senha local, no projeto irmão SIGT; o `.pyc`
órfão que existia antes indicava que o sigma já tinha cogitado essa mesma
necessidade). A prova de que o comportamento abaixo é o que o sigma
realmente executa está em `accounts/tests/test_auth_backends.py`, não no
documento do SIGT. `LDAPBackendComFallbackControlado` sobrescreve
`authenticate_ldap_user()` para que uma rejeição autoritativa do AD (senha
errada, conta desativada/bloqueada/expirada, grupo exigido não satisfeito)
levante `PermissionDenied` e interrompa a cadeia de
`AUTHENTICATION_BACKENDS` — só cai para `ModelBackend` quando o AD está
indisponível ou o usuário não existe nele. Log em `accounts.ldap`
(`SIGMA/settings.py::LOGGING`), INFO para "não encontrado", WARNING para
indisponibilidade e rejeição. Não recrie essa distinção com outro
mecanismo; estenda `LDAPBackendComFallbackControlado` se precisar de mais
uma regra de bloqueio autoritativo.

- Credencial de bind e URL do servidor vêm de variável de ambiente, lidas em
  `SIGMA/settings.py`.
- Não escreva bind LDAP manual numa view. Se precisar consultar o AD fora do
  login, verifique primeiro se `django_auth_ldap` já expõe o dado via
  `user.ldap_user`.
- `AUTH_PASSWORD_VALIDATORS` em `SIGMA/settings.py` inclui validadores
  customizados (`accounts/validators.py`).

## Firebase (push)

Serviço central: `accounts/services/notificacoes.py`, usando
`firebase-admin` com a conta de serviço do servidor. Ver
`docs/sigma/04-aplicativo-mobile.md` para o desenho completo.

- Nunca grave chave de conta de serviço em código, `.env` versionado ou
  template.
- Envio novo reaproveita a função central; não chame o SDK direto de uma view.
- Token rejeitado pelo FCM marca o dispositivo como inativo; não apague o
  registro.

## E-mail (SMTP Office 365)

Backend customizado em `SIGMA/email_backends`. Credencial vem de variável de
ambiente lida em `SIGMA/settings.py`; nunca hardcode endereço de servidor ou
senha de conta de serviço no código.
