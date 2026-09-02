from django.db import models


class PermissoesTelemetria(models.Model):
    """Permissões do módulo de telemetria.

    Uma única permissão cobre as quatro rotas do módulo — cadastro de sensores
    e de fontes HTTP, exclusões e configuração de sensores no recurso. Elas
    formam um único papel: o administrador do módulo, que cadastra, configura
    e exclui. Separar por ação criaria permissões que os grupos existentes não
    distinguem e multiplicaria a concessão sem ganho de segurança.
    """

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("pode_gerenciar_sensores", "Pode gerenciar sensores"),
        ]

    def __str__(self):
        return "Permissões de Telemetria"
