import importlib

from django.db import migrations

ORDEM = [
    "id",
    "troca_op_ativa_id",
    "operador",
    "recurso_id",
    "inicio",
    "fim",
    "motivo",
    "usuario_id",
    "tipo",
    "status",
    "log",
    "data_hora",
]


def reordenar(apps, schema_editor):
    modulo = importlib.import_module("producao.migrations.0005_reordenar_colunas_tabelas_sigma")
    tabelas_originais = modulo.TABELAS
    try:
        modulo.TABELAS = {"producao.paradas_maquina": ORDEM}
        modulo.reordenar(apps, schema_editor)
    finally:
        modulo.TABELAS = tabelas_originais


class Migration(migrations.Migration):
    atomic = True
    dependencies = [("producao", "0013_vincular_parada_a_troca_op")]
    operations = [migrations.RunPython(reordenar, migrations.RunPython.noop)]
