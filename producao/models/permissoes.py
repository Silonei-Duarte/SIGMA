from django.db import models


class PermissoesProducao(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("pode_apontar", "Pode apontar"),
            ("pode_acessar_sequenciamento", "Pode acessar Sequenciamento"),
            ("pode_consolidar_sequenciamento_erp", "Pode consolidar Sequenciamento ERP"),
            ("pode_corrigir_lote", "Pode corrigir Lote"),
            ("pode_acessar_relatorios_producao", "Pode acessar Relatórios de Produção"),
            (
                "pode_excluir_pendencias_integracao",
                "Pode excluir pendências de integração",
            ),
        ]

    def __str__(self):
        return "Permissões de Produção"
