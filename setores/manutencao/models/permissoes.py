from django.db import models


class PermissoesChamado(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("pode_acessar_chamados", "Pode acessar chamados"),
            ("pode_manipular_chamados", "Pode manipular chamados"),
            ("pode_listar_todos_chamados", "Pode listar todos os chamados"),
            ("pode_manipular_os", "Pode manipular OS"),
            ("pode_listar_todas_os", "Pode listar todos as OS"),
            ("pode_acessar_os", "Pode acessar OS"),
        ]

    def __str__(self):
        return "Permissões de Chamados"
