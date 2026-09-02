from datetime import timedelta

from django.db import migrations


def _segundo(valor):
    return valor.replace(microsecond=0) if valor is not None else None


def _reconstruir_justificativas(apps, schema_editor):
    ParadaMaquina = apps.get_model("producao", "ParadaMaquina")
    JustificativaParada = apps.get_model("producao", "JustificativaParada")

    for parada in ParadaMaquina.objects.order_by("id").iterator():
        inicio = _segundo(parada.inicio)
        fim = _segundo(parada.fim)
        ParadaMaquina.objects.filter(pk=parada.pk).update(
            inicio=inicio,
            fim=fim,
            data_hora=_segundo(parada.data_hora),
        )

        justificativas = list(
            JustificativaParada.objects.filter(parada_id=parada.pk).order_by("sequencia", "id")
        )
        for indice, justificativa in enumerate(justificativas):
            parcial = inicio if indice == 0 else _segundo(justificativa.parcial)
            proxima = (
                _segundo(justificativas[indice + 1].parcial)
                if indice + 1 < len(justificativas)
                else fim
            )
            if proxima is None:
                tempo = None
            else:
                tempo = proxima - parcial
                if tempo < timedelta():
                    raise RuntimeError(
                        f"Justificativa {justificativa.pk} ficaria com duração negativa ao normalizar segundos."
                    )
            JustificativaParada.objects.filter(pk=justificativa.pk).update(
                parcial=parcial,
                tempo=tempo,
                data_hora=_segundo(justificativa.data_hora),
            )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0019_recurso_tempo_parada_aut_segundos"),
        ("producao", "0031_regraparadarecurso"),
    ]

    operations = [
        migrations.RunPython(_reconstruir_justificativas, migrations.RunPython.noop),
        migrations.RunSQL(
            sql="""
                UPDATE producao.pacotes_tempo_erp
                   SET corte_inicio_real = date_trunc('minute', corte_inicio_real),
                       corte_fim_real = date_trunc('minute', corte_fim_real);

                ALTER TABLE producao.apontamento
                ALTER COLUMN data_hora TYPE timestamp(0) with time zone
                USING date_trunc('second', data_hora);

                ALTER TABLE producao.apontamento_componente
                ALTER COLUMN data_hora TYPE timestamp(0) with time zone
                USING date_trunc('second', data_hora);

                ALTER TABLE producao.estorno_comp
                ALTER COLUMN data_hora TYPE timestamp(0) with time zone
                USING date_trunc('second', data_hora);

                ALTER TABLE producao.logs_troca_op_ativa
                ALTER COLUMN horario_troca TYPE timestamp(0) with time zone
                USING date_trunc('second', horario_troca),
                ALTER COLUMN horario_saida TYPE timestamp(0) with time zone
                USING date_trunc('second', horario_saida),
                ALTER COLUMN data_hora TYPE timestamp(0) with time zone
                USING date_trunc('second', data_hora);

                ALTER TABLE producao.paradas_maquina
                ALTER COLUMN inicio TYPE timestamp(0) with time zone
                USING date_trunc('second', inicio),
                ALTER COLUMN fim TYPE timestamp(0) with time zone
                USING date_trunc('second', fim),
                ALTER COLUMN data_hora TYPE timestamp(0) with time zone
                USING date_trunc('second', data_hora);

                ALTER TABLE producao.justificativas_paradas
                ALTER COLUMN parcial TYPE timestamp(0) with time zone
                USING date_trunc('second', parcial),
                ALTER COLUMN tempo TYPE interval(0)
                USING date_trunc('second', tempo),
                ALTER COLUMN data_hora TYPE timestamp(0) with time zone
                USING date_trunc('second', data_hora);

                ALTER TABLE producao.pacotes_tempo_erp
                ALTER COLUMN corte_inicio_real TYPE timestamp(0) with time zone
                USING date_trunc('minute', corte_inicio_real),
                ALTER COLUMN corte_fim_real TYPE timestamp(0) with time zone
                USING date_trunc('minute', corte_fim_real),
                ALTER COLUMN data_hora_log TYPE timestamp(0) with time zone
                USING date_trunc('second', data_hora_log);

                ALTER TABLE producao.itens_pacote_tempo_erp
                ALTER COLUMN hora_inicio TYPE time(0)
                USING hora_inicio::time(0),
                ALTER COLUMN hora_fim TYPE time(0)
                USING hora_fim::time(0);
            """,
            reverse_sql="""
                ALTER TABLE producao.apontamento
                ALTER COLUMN data_hora TYPE timestamp(6) with time zone
                USING data_hora;

                ALTER TABLE producao.apontamento_componente
                ALTER COLUMN data_hora TYPE timestamp(6) with time zone
                USING data_hora;

                ALTER TABLE producao.estorno_comp
                ALTER COLUMN data_hora TYPE timestamp(6) with time zone
                USING data_hora;

                ALTER TABLE producao.logs_troca_op_ativa
                ALTER COLUMN horario_troca TYPE timestamp(6) with time zone
                USING horario_troca,
                ALTER COLUMN horario_saida TYPE timestamp(6) with time zone
                USING horario_saida,
                ALTER COLUMN data_hora TYPE timestamp(6) with time zone
                USING data_hora;

                ALTER TABLE producao.paradas_maquina
                ALTER COLUMN inicio TYPE timestamp(6) with time zone
                USING inicio,
                ALTER COLUMN fim TYPE timestamp(6) with time zone
                USING fim,
                ALTER COLUMN data_hora TYPE timestamp(6) with time zone
                USING data_hora;

                ALTER TABLE producao.justificativas_paradas
                ALTER COLUMN parcial TYPE timestamp(6) with time zone
                USING parcial,
                ALTER COLUMN tempo TYPE interval(6)
                USING tempo,
                ALTER COLUMN data_hora TYPE timestamp(6) with time zone
                USING data_hora;

                ALTER TABLE producao.pacotes_tempo_erp
                ALTER COLUMN corte_inicio_real TYPE timestamp(6) with time zone
                USING corte_inicio_real,
                ALTER COLUMN corte_fim_real TYPE timestamp(6) with time zone
                USING corte_fim_real,
                ALTER COLUMN data_hora_log TYPE timestamp(6) with time zone
                USING data_hora_log;

                ALTER TABLE producao.itens_pacote_tempo_erp
                ALTER COLUMN hora_inicio TYPE time(6)
                USING hora_inicio,
                ALTER COLUMN hora_fim TYPE time(6)
                USING hora_fim;
            """,
        ),
    ]
