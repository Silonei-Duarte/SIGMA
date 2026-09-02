from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType


def criar_permissao_manipular_cadastros():
    ct = ContentType.objects.get_or_create(app_label="accounts", model="customuser")[0]
    Permission.objects.get_or_create(
        codename="manipular_cadastros", name="Pode manipular Cadastros", content_type=ct
    )


def criar_permissao_administrar_acessos():
    """Gestão de usuários e grupos é poder de concessão: separada da
    permissão de cadastros para um concedente jamais escalar privilégio
    pelo formulário de usuário/grupo."""
    ct = ContentType.objects.get_or_create(app_label="accounts", model="customuser")[0]
    Permission.objects.get_or_create(
        codename="administrar_acessos",
        name="Pode administrar acessos (usuários e grupos)",
        content_type=ct,
    )


def criar_permissao_configurar_aplicacao():
    """Tela de configurações da aplicação: altera comportamento de workers e
    serviços em runtime — separada dos cadastros porque o alcance não é um
    registro, é o funcionamento do sistema."""
    ct = ContentType.objects.get_or_create(app_label="accounts", model="configuracaoaplicacao")[0]
    Permission.objects.get_or_create(
        codename="configurar_aplicacao",
        name="Pode configurar parâmetros da aplicação",
        content_type=ct,
    )
