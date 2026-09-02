from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("producao", "0019_consolidar_permissoes_sequenciamento"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="permissoesproducao",
            options={
                "default_permissions": (),
                "managed": False,
                "permissions": [
                    ("pode_apontar", "Pode apontar"),
                    ("pode_acessar_sequenciamento", "Pode acessar Sequenciamento"),
                    ("pode_consolidar_sequenciamento_erp", "Pode consolidar Sequenciamento ERP"),
                    ("pode_corrigir_lote", "Pode corrigir Lote"),
                    ("pode_acessar_relatorios_producao", "Pode acessar Relatórios de Produção"),
                ],
            },
        ),
    ]
