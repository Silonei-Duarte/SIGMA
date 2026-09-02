import importlib

from django.db import migrations

ORDEM = [
    "id",
    "recurso_id",
    "origem",
    "op",
    "estagio",
    "seqrot",
    "horario_troca",
    "horario_saida",
    "id_operador",
    "status",
    "log",
    "data_hora",
]


def reordenar(apps, schema_editor):
    modulo = importlib.import_module("producao.migrations.0005_reordenar_colunas_tabelas_sigma")
    tabelas_originais = modulo.TABELAS
    try:
        modulo.TABELAS = {"producao.logs_troca_op_ativa": ORDEM}
        modulo.reordenar(apps, schema_editor)
    finally:
        modulo.TABELAS = tabelas_originais


class Migration(migrations.Migration):
    atomic = True
    dependencies = [("producao", "0011_registrar_logtrocaopativa_em_producao")]
    operations = [migrations.RunPython(reordenar, migrations.RunPython.noop)]
