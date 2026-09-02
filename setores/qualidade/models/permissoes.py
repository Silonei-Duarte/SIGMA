from django.db import models


class PermissoesQualidade(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("pode_acessar_liberacao_lotes", "Pode acessar a tela de liberação de lotes"),
            ("pode_destinar_lotes_liberacao", "Pode destinar lotes na tela de liberação"),
            ("pode_acessar_area_vermelha", "Pode acessar a tela de liberação da área vermelha"),
            ("pode_destinar_area_vermelha", "Pode destinar lotes na área vermelha"),
            ("pode_cadastrar_observacoes_etiqueta", "Pode cadastrar observações de etiqueta"),
        ]

    def __str__(self):
        return "Permissões de Qualidade"
