from django.db import models


class PermissoesLogistica(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("pode_visualizar_componentes_movimentar", "Pode visualizar Componentes a Movimentar"),
        ]

    def __str__(self):
        return "Permissões de Logística"
