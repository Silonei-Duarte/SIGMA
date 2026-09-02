from django.db import models


class PermissoesPcp(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("pode_visualizar_calendario_ops", "Pode visualizar Calendário de OPs"),
        ]

    def __str__(self):
        return "Permissões de PCP"
