from django.db import migrations

# A ordem fisica das colunas nao e alterada pelo PostgreSQL quando um campo e
# acrescentado ou renomeado. Esta lista representa a ordem atual dos models.
TABELAS = {
    "public.accounts_customuser": [
        "id",
        "password",
        "last_login",
        "is_superuser",
        "username",
        "first_name",
        "last_name",
        "email",
        "is_staff",
        "is_active",
        "date_joined",
        "filial_id",
        "idintegracao",
        "idoperador",
        "paginicial",
    ],
    "public.empresas": ["id", "codemp", "nome", "fantasia", "loteatual", "ativa"],
    "public.calendario": ["id", "filial_id", "descricao"],
    "public.centros_recursos": ["id", "setor_id", "codigo", "descricao", "codigo_integrador"],
    "public.recursos": [
        "id",
        "codigo",
        "descricao",
        "centro_recurso_id",
        "habilita_oee",
        "ativo",
        "ordenacao",
        "ordenacao_sequenciamento",
        "modelo_prd",
        "opers_simut",
        "permite_parada_manual",
        "tempo_parada_aut",
        "metadis",
        "metaper",
        "metaqual",
        "metaooee",
        "view_id",
        "quant_pes",
        "aponta_parada",
        "exibir_jus",
        "alt_just",
        "inic_parada_prog",
        "fin_parada_prog",
        "alt_parada_prog",
        "mod_he",
        "bobina",
    ],
    "public.turnos_recursos": [
        "id",
        "turnobase_id",
        "recurso_id",
        "dias",
        "hora_inicio",
        "hora_fim",
    ],
    "public.horas_extras_planejadas": [
        "id",
        "turnobase_id",
        "recurso_id",
        "dias",
        "data_inicio",
        "data_fim",
        "hora_inicio",
        "hora_fim",
        "considera_feriado",
    ],
    "public.oee_planejado_diario": ["id", "recurso_id", "data", "minutos_planejados"],
    "producao.paradas_maquina": [
        "id",
        "recurso_id",
        "inicio",
        "fim",
        "origem",
        "op",
        "estagio",
        "seqrot",
        "operador",
        "motivo",
        "hora_log",
        "usuario_id",
        "tipo",
        "status",
        "log",
        "data_hora",
    ],
    "producao.sequenciamento": [
        "id",
        "recurso_id",
        "ordenacao",
        "origem",
        "op",
        "estagio",
        "seqrot",
        "descricao",
        "codproduto",
        "derivacao",
        "tempo",
        "operacao",
    ],
    "producao.apontamento": [
        "id",
        "recurso_id",
        "usuario_id",
        "codemp",
        "origem",
        "numorp",
        "codetg",
        "seqrot",
        "numcad",
        "qtdre1",
        "qtdrfg",
        "lote",
        "log",
        "status",
        "data_hora",
        "codigo_integrador",
        "datmov",
        "hormov",
        "bobina",
        "origem_peso",
        "balanca",
    ],
    "producao.logs_parada": [
        "id",
        "parada_id",
        "recurso_id",
        "codemp",
        "origem",
        "numorp",
        "codetg",
        "seqrot",
        "numcad",
        "codigo_integrador",
        "datmov",
        "hormov",
        "op_ativa",
        "operador",
        "motivo",
        "tipo",
        "inicio",
        "fim",
        "hora_log",
        "usuario_id",
        "log_integracao",
        "status",
        "data_hora",
    ],
    "producao.apontamento_componente": [
        "id",
        "recurso_id",
        "usuario_id",
        "codemp",
        "origem",
        "numorp",
        "codetg",
        "seqrot",
        "numcad",
        "codigo_integrador",
        "datmov",
        "hormov",
        "lote",
        "log",
        "status",
        "data_hora",
    ],
    "producao.estorno_comp": [
        "id",
        "codemp",
        "acodori",
        "anumorp",
        "acodetg",
        "acodpro",
        "acodder",
        "acodcmp",
        "adercmp",
        "aqtdest",
        "adatfim",
        "acodtns",
        "lote",
        "status",
        "log",
        "data_hora",
    ],
    "qualidade.reuniao_participantes": ["id", "reuniao_id", "nome", "setor"],
    "qualidade.liberacao_lote": [
        "id",
        "codemp",
        "numbob",
        "codpro",
        "codder",
        "coddep",
        "deptrf",
        "codtns",
        "codigo_integrador",
        "codlot",
        "lottrf",
        "codori",
        "numorp",
        "qtdtot",
        "qtdlibe",
        "qtdaverm",
        "qtdrefu",
        "qtdrecl",
        "codpro_recl",
        "codder_recl",
        "coddft",
        "id_etiqueta",
        "observacao_geral",
        "log",
        "usuario_id",
        "status",
        "datager",
        "data_hora",
        "reuniao_id",
    ],
    "qualidade.wms_integracao_op": [
        "id",
        "codemp",
        "origem",
        "op",
        "lote",
        "palete",
        "quantidade",
        "codigo_integrador",
        "local",
        "codpro",
        "codder",
        "log",
        "status",
        "tipo_envio",
        "data_hora",
        "reuniao_id",
    ],
}


def _q(nome):
    return '"' + nome.replace('"', '""') + '"'


def reordenar(apps, schema_editor):
    cursor = schema_editor.connection.cursor()
    existentes = []
    estruturas = {}

    for qualificada, ordem in TABELAS.items():
        esquema, tabela = qualificada.split(".", 1)
        cursor.execute("SELECT to_regclass(%s)", [qualificada])
        if cursor.fetchone()[0] is None:
            continue
        cursor.execute(
            """
            SELECT a.attname
              FROM pg_attribute a
             WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped
             ORDER BY a.attnum
        """,
            [qualificada],
        )
        atuais = [r[0] for r in cursor.fetchall()]
        if atuais == ordem:
            continue
        if set(atuais) != set(ordem):
            raise RuntimeError(
                f"Colunas inesperadas em {qualificada}: banco={atuais}; migration={ordem}"
            )
        existentes.append((qualificada, esquema, tabela, ordem))

    if not existentes:
        return

    alvos = [x[0] for x in existentes]
    cursor.execute(
        """
        SELECT c.conrelid::regclass::text, c.conname, pg_get_constraintdef(c.oid, true)
          FROM pg_constraint c
         WHERE c.contype = 'f'
           AND c.confrelid IN (SELECT to_regclass(x) FROM unnest(%s::text[]) AS x)
    """,
        [alvos],
    )
    fks_entrada = cursor.fetchall()

    for tabela_origem, nome, _ in fks_entrada:
        cursor.execute(f"ALTER TABLE {tabela_origem} DROP CONSTRAINT {_q(nome)}")

    for qualificada, esquema, tabela, ordem in existentes:
        cursor.execute(
            """
            SELECT conname, contype, pg_get_constraintdef(oid, true)
              FROM pg_constraint
             WHERE conrelid = %s::regclass AND contype <> 'n'
             ORDER BY CASE contype WHEN 'p' THEN 1 WHEN 'u' THEN 2 WHEN 'c' THEN 3 ELSE 4 END
        """,
            [qualificada],
        )
        constraints = cursor.fetchall()
        nomes_constraints = [x[0] for x in constraints]
        cursor.execute(
            """
            SELECT indexname, indexdef FROM pg_indexes
             WHERE schemaname=%s AND tablename=%s
               AND indexname <> ALL(%s)
        """,
            [esquema, tabela, nomes_constraints or [""]],
        )
        indices = cursor.fetchall()
        cursor.execute(
            """
            SELECT tgname, pg_get_triggerdef(oid, true)
              FROM pg_trigger WHERE tgrelid=%s::regclass AND NOT tgisinternal
        """,
            [qualificada],
        )
        triggers = cursor.fetchall()
        cursor.execute(
            """
            SELECT grantee, privilege_type FROM information_schema.role_table_grants
             WHERE table_schema=%s AND table_name=%s AND grantee <> current_user
        """,
            [esquema, tabela],
        )
        grants = cursor.fetchall()
        cursor.execute(
            """
            SELECT a.attname, pg_get_serial_sequence(%s, a.attname)
              FROM pg_attribute a
             WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped
               AND a.attidentity = ''
        """,
            [qualificada, qualificada],
        )
        sequences = [(c, s) for c, s in cursor.fetchall() if s]

        definicoes = []
        for coluna in ordem:
            cursor.execute(
                """
                SELECT format_type(a.atttypid,a.atttypmod), a.attnotnull,
                       pg_get_expr(d.adbin,d.adrelid), a.attidentity, a.attgenerated,
                       CASE WHEN a.attcollation <> t.typcollation THEN quote_ident(coll.collname) END
                  FROM pg_attribute a
                  JOIN pg_type t ON t.oid=a.atttypid
                  LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
                  LEFT JOIN pg_collation coll ON coll.oid=a.attcollation
                 WHERE a.attrelid=%s::regclass AND a.attname=%s
            """,
                [qualificada, coluna],
            )
            tipo, notnull, default, identity, generated, collation = cursor.fetchone()
            parte = f"{_q(coluna)} {tipo}"
            if collation:
                parte += f" COLLATE {collation}"
            if generated:
                parte += f" GENERATED ALWAYS AS ({default}) STORED"
            elif identity:
                parte += f" GENERATED {'ALWAYS' if identity == 'a' else 'BY DEFAULT'} AS IDENTITY"
            elif default:
                parte += f" DEFAULT {default}"
            if notnull:
                parte += " NOT NULL"
            definicoes.append(parte)

        temporaria = f"__reord_{tabela}"
        qtemp = f"{_q(esquema)}.{_q(temporaria)}"
        qtable = f"{_q(esquema)}.{_q(tabela)}"
        colunas = ", ".join(_q(c) for c in ordem)
        for _, seq in sequences:
            cursor.execute(f"ALTER SEQUENCE {seq} OWNED BY NONE")
        cursor.execute(f"CREATE TABLE {qtemp} ({', '.join(definicoes)})")
        cursor.execute(f"INSERT INTO {qtemp} ({colunas}) SELECT {colunas} FROM {qtable}")
        cursor.execute(f"DROP TABLE {qtable}")
        cursor.execute(f"ALTER TABLE {qtemp} RENAME TO {_q(tabela)}")
        estruturas[qualificada] = (constraints, indices, triggers, grants, sequences)

    for qualificada, _, _, _ in existentes:
        constraints, indices, triggers, grants, sequences = estruturas[qualificada]
        for nome, _, definicao in constraints:
            cursor.execute(f"ALTER TABLE {qualificada} ADD CONSTRAINT {_q(nome)} {definicao}")
        for _, definicao in indices:
            cursor.execute(definicao)
        for _, definicao in triggers:
            cursor.execute(definicao)
        for coluna, seq in sequences:
            cursor.execute(f"ALTER SEQUENCE {seq} OWNED BY {qualificada}.{_q(coluna)}")
        for coluna in TABELAS[qualificada]:
            cursor.execute("SELECT pg_get_serial_sequence(%s, %s)", [qualificada, coluna])
            seq = cursor.fetchone()[0]
            if seq:
                cursor.execute(
                    f"SELECT setval(%s, COALESCE((SELECT MAX({_q(coluna)}) FROM {qualificada}), 1), EXISTS(SELECT 1 FROM {qualificada}))",
                    [seq],
                )
        for grantee, privilegio in grants:
            cursor.execute(f"GRANT {privilegio} ON TABLE {qualificada} TO {_q(grantee)}")

    for tabela_origem, nome, definicao in fks_entrada:
        cursor.execute(f"ALTER TABLE {tabela_origem} ADD CONSTRAINT {_q(nome)} {definicao}")


class Migration(migrations.Migration):
    atomic = True

    dependencies = [
        ("producao", "0004_rename_seqroteiro_sequenciamento_seqrot"),
        ("accounts", "0008_remove_logtrocaopativa_codigo_barra_op_and_more"),
        ("qualidade", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(reordenar, migrations.RunPython.noop),
    ]
