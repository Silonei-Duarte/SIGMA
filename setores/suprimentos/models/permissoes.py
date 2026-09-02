from django.db import models


class PermissoesSuprimentos(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("pode_visualizar_componentes_separar", "Pode visualizar Componentes a Separar"),
        ]

    def __str__(self):
        return "Permissões de Suprimentos"
