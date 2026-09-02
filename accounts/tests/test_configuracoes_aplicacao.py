"""Testes das configurações da aplicação: model, service com cache e telas."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import ConfiguracaoAplicacao
from accounts.models.permissoes import criar_permissao_configurar_aplicacao
from accounts.services import configuracoes as servico
from accounts.views import editar_configuracao, voltar_ao_padrao_configuracao

User = get_user_model()

CHAVE_LIMIAR = "RELATORIO_FALHAS_LIMIAR_ATRASO_MINUTOS"
CHAVE_DESTINATARIOS = "RELATORIO_FALHAS_EMAIL_DESTINATARIOS"
CHAVE_HORARIOS = "RELATORIO_FALHAS_HORARIOS"
TOPICO_EMAIL = "E-mail — Relatórios"


def _item_da_listagem(resposta, chave):
    """Item da chave no contexto da listagem — os valores de tela, sem casar HTML."""
    for grupo in resposta.context["topicos"]:
        for item in grupo["itens"]:
            if item["chave"] == chave:
                return item
    raise AssertionError(f"{chave} não está na listagem")


class ConfiguracaoServiceObterTests(TestCase):
    """Leitura com cache in-process: segunda leitura não consulta o banco."""

    def setUp(self):
        servico.limpar_cache()

    def test_segunda_leitura_serve_do_cache_sem_query(self):
        ConfiguracaoAplicacao.objects.create(chave="FILA_X", valor="1", descricao="d")
        # O signal de salvamento já popula o cache (comportamento desejado);
        # para medir a leitura a partir do zero, esvazia depois de criar.
        servico.limpar_cache()

        with CaptureQueriesContext(connection) as primeira:
            self.assertEqual(servico.obter("FILA_X"), "1")
        self.assertEqual(len(primeira), 1)

        with CaptureQueriesContext(connection) as segunda:
            self.assertEqual(servico.obter("FILA_X"), "1")
            self.assertEqual(servico.obter("FILA_X"), "1")
        self.assertEqual(len(segunda), 0)

    def test_chave_conhecida_sem_linha_no_banco_devolve_padrao(self):
        self.assertEqual(servico.obter(CHAVE_LIMIAR), "5")

        # O default também é cacheado: repetir não volta ao banco.
        with CaptureQueriesContext(connection) as contexto:
            self.assertEqual(servico.obter(CHAVE_LIMIAR), "5")
        self.assertEqual(len(contexto), 0)

    def test_chave_desconhecida_sem_linha_devolve_default_do_chamador(self):
        self.assertIsNone(servico.obter("CHAVE_INEXISTENTE"))
        self.assertEqual(servico.obter("CHAVE_INEXISTENTE", "fallback"), "fallback")

        # Ausência também é cacheada: leitura repetida não reconsulta e
        # continua devolvendo o default de quem chamou.
        with CaptureQueriesContext(connection) as contexto:
            self.assertEqual(servico.obter("CHAVE_INEXISTENTE", "fallback"), "fallback")
        self.assertEqual(len(contexto), 0)

    def test_definir_invalida_o_cache_na_leitura_seguinte(self):
        self.assertEqual(servico.obter(CHAVE_LIMIAR), "5")

        servico.definir(CHAVE_LIMIAR, "9", None)

        self.assertEqual(servico.obter(CHAVE_LIMIAR), "9")

    def test_salvar_pelo_orm_invalida_o_cache_via_signal(self):
        # Lê primeiro: ausência da chave fica cacheada.
        self.assertIsNone(servico.obter("CHAVE_NOVA"))

        ConfiguracaoAplicacao.objects.create(chave="CHAVE_NOVA", valor="ativo", descricao="d")

        self.assertEqual(servico.obter("CHAVE_NOVA"), "ativo")

    def test_excluir_volta_ao_padrao_da_chave_conhecida(self):
        linha = servico.definir(CHAVE_LIMIAR, "9", None)
        self.assertEqual(servico.obter(CHAVE_LIMIAR), "9")

        linha.delete()

        self.assertEqual(servico.obter(CHAVE_LIMIAR), "5")

    def test_valor_do_banco_prevalece_sobre_o_padrao_conhecido(self):
        servico.definir(CHAVE_LIMIAR, "30", None)

        self.assertEqual(servico.obter(CHAVE_LIMIAR), "30")
        self.assertEqual(servico.obter(CHAVE_LIMIAR, "5"), "30")

    def test_obter_rejeita_chave_com_padrao_de_segredo(self):
        # Decisão datada do sênior: o guard não é só da escrita — linha
        # plantada por shell/migração não é servida pela leitura.
        ConfiguracaoAplicacao.objects.create(
            chave="API_TOKEN_WMS", valor="abc123", descricao="plantada fora da tela"
        )
        servico.limpar_cache()

        with self.assertRaises(ValidationError):
            servico.obter("API_TOKEN_WMS")

    def test_obter_normaliza_a_chave_como_definir(self):
        ConfiguracaoAplicacao.objects.create(chave="FILA_X", valor="1", descricao="d")
        servico.limpar_cache()

        self.assertEqual(servico.obter("fila_x"), "1")


class ConfiguracaoServiceDefinirTests(TestCase):
    """Gravação rastreada, guard anti-segredo e validador como segunda barreira."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user(username="operador", password="senha")

    def setUp(self):
        servico.limpar_cache()

    def test_definir_grava_rastreio(self):
        linha = servico.definir(CHAVE_LIMIAR, "9", self.usuario, descricao="Limiar")

        self.assertEqual(linha.valor, "9")
        self.assertEqual(linha.atualizado_por, self.usuario)
        self.assertIsNotNone(linha.atualizado_em)
        self.assertEqual(linha.descricao, "Limiar")

    def test_definir_registra_auditoria_sem_o_valor(self):
        with self.assertLogs("accounts.services.configuracoes", level="INFO") as capturado:
            servico.definir(CHAVE_LIMIAR, "9", self.usuario)

        saida = "\n".join(capturado.output)
        self.assertIn(CHAVE_LIMIAR, saida)
        self.assertIn("operador", saida)
        # O valor não vai para o log: a trilha registra quem e o quê,
        # não o conteúdo (defesa da política da tela).
        self.assertNotIn("9", saida)

    def test_definir_rejeita_chave_com_padrao_de_segredo(self):
        for chave in ("X_PASSWORD", "API_SECRET", "MEU_TOKEN", "SMTP_CREDENTIAL", "SENHA_WMS"):
            with self.subTest(chave=chave):
                with self.assertRaises(ValidationError):
                    servico.definir(chave, "qualquer", self.usuario)

    def test_definir_normaliza_a_chave_para_a_forma_canonica(self):
        # Mesma normalização do formulário: minúsculas e espaços das pontas
        # viram a chave canônica, e a chave conhecida continua caindo no
        # validador dela (e não vira linha nova ao lado da original).
        linha = servico.definir(CHAVE_HORARIOS.lower(), " 07:00 ", self.usuario)

        self.assertEqual(linha.chave, CHAVE_HORARIOS)
        self.assertEqual(linha.valor, "07:00")
        self.assertEqual(servico.obter(CHAVE_HORARIOS), "07:00")

    def test_definir_rejeita_chave_com_formato_invalido(self):
        for chave in ("X'Y", "chave minuscula", "1_COMECA_POR_DIGITO", "COM ESPACO", ""):
            with self.subTest(chave=chave):
                with self.assertRaises(ValidationError):
                    servico.definir(chave, "x", self.usuario)

    def test_definir_aplica_validador_da_chave_conhecida(self):
        with self.assertRaises(ValidationError):
            servico.definir(CHAVE_LIMIAR, "abc", self.usuario)

        linha = servico.definir(CHAVE_LIMIAR, "07", self.usuario)
        self.assertEqual(linha.valor, "7")

    def test_definir_chave_desconhecida_aceita_valor_livre(self):
        linha = servico.definir("PORTAL_AVISO_OPERACAO", "texto livre", self.usuario)

        self.assertEqual(linha.valor, "texto livre")

    def test_definir_com_valor_que_parece_credencial_aceita_e_avisa(self):
        # Política: a tela é não sensível; valor suspeito é aviso em log,
        # não adivinhação — quem decide é o revisor da política.
        with self.assertLogs("accounts.services.configuracoes", level="WARNING") as capturado:
            servico.definir("PORTAL_AVISO_OPERACAO", "password=x", self.usuario)

        saida = "\n".join(capturado.output)
        self.assertIn("credencial", saida)
        self.assertNotIn("password=x", saida)


class ValidadoresConhecidosTests(TestCase):
    def test_destinatarios_normaliza_um_por_linha(self):
        normalizado = servico.CHAVES_CONHECIDAS[CHAVE_DESTINATARIOS].validador(
            "Ana@Ex.com \n bob@ex.com\nAna@ex.com"
        )

        self.assertEqual(normalizado, "ana@ex.com\nbob@ex.com")

    def test_destinatario_invalido_rejeitado(self):
        with self.assertRaises(ValidationError):
            servico.CHAVES_CONHECIDAS[CHAVE_DESTINATARIOS].validador("ana@ex.com\nsem-arroba")

    def test_destinatarios_vazios_rejeitados(self):
        with self.assertRaises(ValidationError):
            servico.CHAVES_CONHECIDAS[CHAVE_DESTINATARIOS].validador("  \n ")

    def test_horarios_dedupe_ordenacao_normalizados(self):
        normalizado = servico.CHAVES_CONHECIDAS[CHAVE_HORARIOS].validador("16:00, 07:00;16:00")

        self.assertEqual(normalizado, "07:00,16:00")

    def test_horario_invalido_rejeitado(self):
        for valor in ("24:00", "7:00", "0700", "25:00,07:00"):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    servico.CHAVES_CONHECIDAS[CHAVE_HORARIOS].validador(valor)

    def test_horario_com_virgula_final_e_tolerado(self):
        # Separador sobrando no fim é descarte, não horário inválido.
        self.assertEqual(servico.CHAVES_CONHECIDAS[CHAVE_HORARIOS].validador("07:00,"), "07:00")

    def test_limiar_fora_da_faixa_rejeitado(self):
        for valor in ("0", "1441", "-5"):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    servico.CHAVES_CONHECIDAS[CHAVE_LIMIAR].validador(valor)

    def test_limiar_valido_normalizado(self):
        self.assertEqual(servico.CHAVES_CONHECIDAS[CHAVE_LIMIAR].validador(" 05 "), "5")
        self.assertEqual(servico.CHAVES_CONHECIDAS[CHAVE_LIMIAR].validador("1440"), "1440")


class ConfiguracaoServiceVoltarAoPadraoTests(TestCase):
    """Ação "Voltar ao padrão": exclui a linha e o default do código volta a valer."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user(username="restaurador", password="senha")

    def setUp(self):
        servico.limpar_cache()

    def test_voltar_ao_padrao_exclui_a_linha_e_restaura_o_default(self):
        servico.definir(CHAVE_LIMIAR, "9", self.usuario, descricao="ajuste manual")
        self.assertEqual(servico.obter(CHAVE_LIMIAR), "9")

        voltou = servico.voltar_ao_padrao(CHAVE_LIMIAR, self.usuario)

        self.assertTrue(voltou)
        self.assertFalse(ConfiguracaoAplicacao.objects.filter(chave=CHAVE_LIMIAR).exists())
        # Logo após o voltar-ao-padrão, sem limpar cache na mão: o signal
        # post_delete da exclusão por instância esqueceu a chave, e `obter()`
        # já serve o default — é a invalidação que a ação da tela depende.
        self.assertEqual(servico.obter(CHAVE_LIMIAR), "5")

    def test_voltar_ao_padrao_normaliza_a_chave_como_definir(self):
        servico.definir(CHAVE_LIMIAR, "9", self.usuario)

        self.assertTrue(servico.voltar_ao_padrao(CHAVE_LIMIAR.lower(), self.usuario))
        self.assertEqual(servico.obter(CHAVE_LIMIAR), "5")

    def test_voltar_ao_padrao_sem_linha_devolve_false_sem_erro(self):
        self.assertFalse(ConfiguracaoAplicacao.objects.filter(chave=CHAVE_LIMIAR).exists())

        self.assertFalse(servico.voltar_ao_padrao(CHAVE_LIMIAR, self.usuario))
        self.assertEqual(servico.obter(CHAVE_LIMIAR), "5")

    def test_voltar_ao_padrao_preserva_as_outras_chaves(self):
        # Exclusão por instância da chave pedida: vizinhas ficam intactas.
        servico.definir(CHAVE_LIMIAR, "9", self.usuario)
        servico.definir(CHAVE_HORARIOS, "07:00", self.usuario)

        servico.voltar_ao_padrao(CHAVE_LIMIAR, self.usuario)

        self.assertEqual(servico.obter(CHAVE_HORARIOS), "07:00")
        self.assertTrue(ConfiguracaoAplicacao.objects.filter(chave=CHAVE_HORARIOS).exists())

    def test_voltar_ao_padrao_registra_auditoria_sem_o_valor(self):
        servico.definir(CHAVE_LIMIAR, "9", self.usuario)

        with self.assertLogs("accounts.services.configuracoes", level="INFO") as capturado:
            servico.voltar_ao_padrao(CHAVE_LIMIAR, self.usuario)

        saida = "\n".join(capturado.output)
        self.assertIn(CHAVE_LIMIAR, saida)
        self.assertIn("restaurador", saida)
        # O valor que a linha tinha não vai para o log (mesma política de
        # `definir`): registra quem voltou o quê, não o conteúdo.
        self.assertNotIn("9", saida)


class ConfiguracaoModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user(username="rastreio", password="senha")

    def test_chave_e_unica(self):
        ConfiguracaoAplicacao.objects.create(chave="UNICA", valor="a", descricao="d")

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                ConfiguracaoAplicacao.objects.create(chave="UNICA", valor="b", descricao="d")

    def test_rastreio_registrado_na_gravacao(self):
        linha = ConfiguracaoAplicacao.objects.create(
            chave="RASTREIO", valor="v", descricao="d", atualizado_por=self.usuario
        )

        self.assertEqual(linha.atualizado_por, self.usuario)
        self.assertIsNotNone(linha.atualizado_em)
        self.assertEqual(str(linha), "RASTREIO")


class TelaConfiguracoesTests(TestCase):
    """Autorização da tela e o desenho novo: só chaves declaradas em código
    são listadas, agrupadas por tópico, e editadas por NOME (sem criar/remover).

    A chave é parte do código: a tela edita descrição e valor; linha
    excluída por qualquer via volta a mostrar o default na listagem.
    """

    @classmethod
    def setUpTestData(cls):
        criar_permissao_configurar_aplicacao()
        cls.sem_permissao = User.objects.create_user(username="tela_sem_acesso", password="senha")

    def setUp(self):
        servico.limpar_cache()
        self.usuario = User.objects.create_user(username="tela_operador", password="senha")
        self.usuario.user_permissions.add(
            # A permissão nasce por função pós-migrate; no banco de teste
            # ela precisa existir antes de ser concedida.
            Permission.objects.get(
                content_type__app_label="accounts", codename="configurar_aplicacao"
            )
        )
        self.client.force_login(self.usuario)

    def test_anonimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        resposta = self.client.get(reverse("lista_configuracoes"))

        self.assertEqual(resposta.status_code, 302)

    def test_autenticado_sem_permissao_recebe_403(self):
        self.client.force_login(self.sem_permissao)

        resposta = self.client.get(reverse("lista_configuracoes"))
        self.assertEqual(resposta.status_code, 403)

        resposta = self.client.get(reverse("editar_configuracao", kwargs={"chave": CHAVE_LIMIAR}))
        self.assertEqual(resposta.status_code, 403)

        resposta = self.client.post(reverse("editar_configuracao", kwargs={"chave": CHAVE_LIMIAR}))
        self.assertEqual(resposta.status_code, 403)

    def test_staff_sem_permissao_passa_pelo_gate(self):
        # O decorator permite staff/superusuário por desenho (bypass do
        # papel); o teste dedicado existe para essa escolha não mudar
        # silenciosamente.
        staff = User.objects.create_user(
            username="tela_staff_sem_permissao", password="senha", is_staff=True
        )
        self.client.force_login(staff)

        resposta = self.client.get(reverse("lista_configuracoes"))
        self.assertEqual(resposta.status_code, 200)

        resposta = self.client.get(reverse("editar_configuracao", kwargs={"chave": CHAVE_LIMIAR}))
        self.assertEqual(resposta.status_code, 200)

    def test_listagem_agrupa_as_chaves_por_topico(self):
        resposta = self.client.get(reverse("lista_configuracoes"))

        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode()
        # As três chaves de e-mail vivem num único grupo "E-mail — Relatórios".
        self.assertEqual(conteudo.count(TOPICO_EMAIL), 1)
        for chave in (CHAVE_DESTINATARIOS, CHAVE_HORARIOS, CHAVE_LIMIAR):
            self.assertIn(chave, conteudo)
        # Chaves em ordem alfabética dentro do tópico.
        self.assertLess(
            conteudo.index(CHAVE_DESTINATARIOS),
            conteudo.index(CHAVE_HORARIOS),
        )
        self.assertLess(conteudo.index(CHAVE_HORARIOS), conteudo.index(CHAVE_LIMIAR))

    def test_celula_densa_sem_valor_mostra_hifen_curto(self):
        """Faixa 1 do marcador de valor vazio: célula densa de tabela usa `-`
        (hífen curto) — nunca `—`, que se lê como traço do desenho, e nunca
        célula em branco."""
        # Linha gravada sem autor (via shell/comando): atualizado_por é null.
        ConfiguracaoAplicacao.objects.create(
            chave=CHAVE_LIMIAR, valor="7", descricao="Ajuste manual"
        )

        resposta = self.client.get(reverse("lista_configuracoes"))
        conteudo = resposta.content.decode()

        self.assertEqual(resposta.status_code, 200)
        # A célula "Atualizado" renderiza o hífen curto (só ele na célula)
        # seguido da quebra de linha do rastreio.
        self.assertRegex(conteudo, r">\s*-\s*<br>")
        # O travessão só existe no nome do tópico ("E-mail — Relatórios"),
        # nunca como marcador de valor vazio.
        self.assertEqual(conteudo.count("—"), 1)

    def test_chave_conhecida_sem_linha_mostra_o_padrao(self):
        resposta = self.client.get(reverse("lista_configuracoes"))

        item = _item_da_listagem(resposta, CHAVE_LIMIAR)
        self.assertEqual(item["valor"], "5")
        self.assertTrue(item["usa_padrao"])
        self.assertTrue(item["descricao_e_padrao"])
        self.assertFalse(item["tem_linha"])
        # A indicação de padrão é da tela de edição; a listagem fica limpa,
        # sem etiqueta na linha — a célula "Atualizado" cai na faixa 3 do
        # marcador de valor vazio: "Sem configuração salva" é a resposta.
        self.assertNotContains(resposta, ">Padrão</span>")
        self.assertContains(resposta, "Sem configuração salva")

    def test_descricao_padrao_quando_nunca_editada(self):
        resposta = self.client.get(reverse("lista_configuracoes"))

        item = _item_da_listagem(resposta, CHAVE_LIMIAR)
        # A descrição exibida é a default declarada em código.
        self.assertIn("Pendência envelhecida do relatório de falhas", item["descricao"])

    def test_linha_do_banco_fora_do_registro_nao_e_listada(self):
        ConfiguracaoAplicacao.objects.create(
            chave="PORTAL_AVISO_OPERACAO", valor="ativo", descricao="aviso"
        )

        conteudo = self.client.get(reverse("lista_configuracoes")).content.decode()

        self.assertNotIn("PORTAL_AVISO_OPERACAO", conteudo)
        self.assertNotIn("ativo", conteudo)

    def test_linha_plantada_com_nome_de_segredo_nao_aparece_na_tela(self):
        # Linha plantada por outra via (ORM/shell/migração) escapou da guard
        # da gravação; como não é chave conhecida, a tela não a lista — nem
        # o nome, nem o valor. A defesa do consumidor é o guard de leitura.
        ConfiguracaoAplicacao.objects.create(
            chave="API_TOKEN_WMS", valor="abc123", descricao="plantada fora da tela"
        )

        conteudo = self.client.get(reverse("lista_configuracoes")).content.decode()

        self.assertNotIn("API_TOKEN_WMS", conteudo)
        self.assertNotIn("abc123", conteudo)

    def test_editar_por_chave_get_mostra_valores_vigentes(self):
        # Sem linha: o form abre com o default do código.
        resposta = self.client.get(reverse("editar_configuracao", kwargs={"chave": CHAVE_LIMIAR}))

        self.assertEqual(resposta.status_code, 200)
        inicial = resposta.context["form"].initial
        self.assertEqual(inicial["valor"], "5")
        self.assertIn("Pendência envelhecida do relatório de falhas", inicial["descricao"])

    def test_editar_por_chave_get_mostra_valores_gravados(self):
        servico.definir(CHAVE_LIMIAR, "9", None, descricao="Limiar do time")

        resposta = self.client.get(reverse("editar_configuracao", kwargs={"chave": CHAVE_LIMIAR}))

        self.assertEqual(resposta.status_code, 200)
        inicial = resposta.context["form"].initial
        self.assertEqual(inicial["valor"], "9")
        self.assertEqual(inicial["descricao"], "Limiar do time")

    def test_editar_por_chave_post_salva_via_service_e_grava_rastreio(self):
        resposta = self.client.post(
            reverse("editar_configuracao", kwargs={"chave": CHAVE_LIMIAR}),
            {"descricao": "Limiar atualizado", "valor": "15"},
        )

        self.assertRedirects(resposta, reverse("lista_configuracoes"))
        linha = ConfiguracaoAplicacao.objects.get(chave=CHAVE_LIMIAR)
        self.assertEqual(linha.valor, "15")
        self.assertEqual(linha.descricao, "Limiar atualizado")
        self.assertEqual(linha.atualizado_por, self.usuario)

    def test_editar_aplica_validador_da_chave_conhecida_no_post(self):
        resposta = self.client.post(
            reverse("editar_configuracao", kwargs={"chave": CHAVE_LIMIAR}),
            {"descricao": "d", "valor": "abc"},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(ConfiguracaoAplicacao.objects.filter(chave=CHAVE_LIMIAR).exists())

    def test_editar_aceita_chave_em_minusculas_na_url(self):
        # Mesma normalização de `definir`: a caixa da URL não divide a tela.
        resposta = self.client.get(
            reverse("editar_configuracao", kwargs={"chave": CHAVE_LIMIAR.lower()})
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn(CHAVE_LIMIAR, resposta.content.decode())

    def test_editar_chave_desconhecida_retorna_404(self):
        # A tela não cria configuração: o que o código não declara não é
        # endereço de edição. A view levanta Http404 no GET e no POST.
        #
        # O contrato é provado no nível da view porque o handler404 do
        # projeto (SIGMA/urls.py) converte Http404 no redirect ao portal —
        # decisão global de navegação, aplicada a toda a aplicação; o teste
        # de rota abaixo documenta o efeito final (302), não o repete como
        # expectativa desta tela.
        requisicao = RequestFactory().get("/configuracoes/editar/CHAVE_QUE_NAO_EXISTE/")
        requisicao.user = self.usuario
        with self.assertRaises(Http404):
            editar_configuracao(requisicao, chave="CHAVE_QUE_NAO_EXISTE")

        requisicao = RequestFactory().post(
            "/configuracoes/editar/CHAVE_QUE_NAO_EXISTE/",
            {"descricao": "d", "valor": "x"},
        )
        requisicao.user = self.usuario
        with self.assertRaises(Http404):
            editar_configuracao(requisicao, chave="CHAVE_QUE_NAO_EXISTE")

        resposta = self.client.get(
            reverse("editar_configuracao", kwargs={"chave": "CHAVE_QUE_NAO_EXISTE"})
        )
        self.assertEqual(resposta.status_code, 302)

    def test_linha_excluida_do_banco_volta_mostrar_o_padrao(self):
        linha = servico.definir(CHAVE_LIMIAR, "9", self.usuario)

        linha.delete()

        resposta = self.client.get(reverse("lista_configuracoes"))
        item = _item_da_listagem(resposta, CHAVE_LIMIAR)
        self.assertEqual(item["valor"], "5")
        self.assertTrue(item["usa_padrao"])
        self.assertFalse(item["tem_linha"])
        self.assertEqual(servico.obter(CHAVE_LIMIAR), "5")

    def test_descricao_editada_sobrescreve_a_padrao(self):
        self.client.post(
            reverse("editar_configuracao", kwargs={"chave": CHAVE_LIMIAR}),
            {"descricao": "Minha descrição do limiar", "valor": "9"},
        )

        conteudo = self.client.get(reverse("lista_configuracoes")).content.decode()
        self.assertIn("Minha descrição do limiar", conteudo)
        self.assertNotIn("Pendência envelhecida do relatório de falhas", conteudo)


class TelaVoltarAoPadraoTests(TestCase):
    """Ação "Voltar ao padrão" da tela de edição: POST próprio, por NOME de
    chave, excluindo a linha salva (o default do código volta a valer).

    Desenho do dono do produto: é a única remoção que a tela oferece, e só
    de chaves declaradas — a declaração em código é quem define a chave.
    """

    @classmethod
    def setUpTestData(cls):
        criar_permissao_configurar_aplicacao()
        cls.sem_permissao = User.objects.create_user(username="padrao_sem_acesso", password="senha")

    def setUp(self):
        servico.limpar_cache()
        self.usuario = User.objects.create_user(username="padrao_operador", password="senha")
        self.usuario.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="accounts", codename="configurar_aplicacao"
            )
        )
        self.client.force_login(self.usuario)

    def test_anonimo_e_redirecionado_para_o_login(self):
        self.client.logout()

        resposta = self.client.post(
            reverse("voltar_padrao_configuracao", kwargs={"chave": CHAVE_LIMIAR})
        )

        self.assertEqual(resposta.status_code, 302)

    def test_sem_permissao_recebe_403(self):
        servico.definir(CHAVE_LIMIAR, "9", self.usuario)
        self.client.force_login(self.sem_permissao)

        resposta = self.client.post(
            reverse("voltar_padrao_configuracao", kwargs={"chave": CHAVE_LIMIAR})
        )

        self.assertEqual(resposta.status_code, 403)
        # O gate barra antes da exclusão: a linha continua no banco.
        self.assertTrue(ConfiguracaoAplicacao.objects.filter(chave=CHAVE_LIMIAR).exists())

    def test_post_restaura_o_default_e_confirma_na_listagem(self):
        servico.definir(CHAVE_LIMIAR, "9", self.usuario, descricao="ajuste manual")
        self.assertEqual(servico.obter(CHAVE_LIMIAR), "9")

        resposta = self.client.post(
            reverse("voltar_padrao_configuracao", kwargs={"chave": CHAVE_LIMIAR})
        )

        self.assertRedirects(resposta, reverse("lista_configuracoes"))
        self.assertFalse(ConfiguracaoAplicacao.objects.filter(chave=CHAVE_LIMIAR).exists())
        # A listagem já mostra o default e a marca "Padrão" — e o `obter()`
        # serve o default sem nenhuma limpeza de cache extra (signal de
        # delete da exclusão por instância).
        item = _item_da_listagem(self.client.get(reverse("lista_configuracoes")), CHAVE_LIMIAR)
        self.assertEqual(item["valor"], "5")
        self.assertTrue(item["usa_padrao"])
        self.assertFalse(item["tem_linha"])

    def test_post_confirma_a_mensagem_de_padrao_restaurado(self):
        servico.definir(CHAVE_LIMIAR, "9", self.usuario)

        resposta = self.client.post(
            reverse("voltar_padrao_configuracao", kwargs={"chave": CHAVE_LIMIAR}),
            follow=True,
        )

        messages = [str(m) for m in resposta.context["messages"]]
        self.assertTrue(any("voltou ao padrão do código" in m for m in messages))

    def test_chave_sem_linha_nao_falha_e_informa(self):
        # Estado desejado já vale: nada a excluir é resposta normal, não erro.
        resposta = self.client.post(
            reverse("voltar_padrao_configuracao", kwargs={"chave": CHAVE_LIMIAR}),
            follow=True,
        )

        self.assertRedirects(resposta, reverse("lista_configuracoes"))
        messages = [str(m) for m in resposta.context["messages"]]
        self.assertTrue(any("Nada a voltar" in m for m in messages))

    def test_get_nao_executa_a_acao(self):
        # Efeito persistente não dispara por link: GET redireciona e a linha
        # continua no banco.
        servico.definir(CHAVE_LIMIAR, "9", self.usuario)

        resposta = self.client.get(
            reverse("voltar_padrao_configuracao", kwargs={"chave": CHAVE_LIMIAR})
        )

        self.assertRedirects(resposta, reverse("lista_configuracoes"))
        self.assertTrue(ConfiguracaoAplicacao.objects.filter(chave=CHAVE_LIMIAR).exists())

    def test_chave_desconhecida_retorna_404(self):
        # Mesma regra da edição: handler404 do projeto converte Http404 no
        # redirect ao portal, então o contrato é provado no nível da view.
        requisicao = RequestFactory().post("/configuracoes/padrao/CHAVE_QUE_NAO_EXISTE/")
        requisicao.user = self.usuario
        with self.assertRaises(Http404):
            voltar_ao_padrao_configuracao(requisicao, chave="CHAVE_QUE_NAO_EXISTE")

        resposta = self.client.get(
            reverse("voltar_padrao_configuracao", kwargs={"chave": "CHAVE_QUE_NAO_EXISTE"})
        )
        self.assertEqual(resposta.status_code, 302)

    def test_form_mostra_o_botao_somente_com_linha_no_banco(self):
        # Sem linha não há nada a voltar: o botão não renderiza.
        resposta = self.client.get(reverse("editar_configuracao", kwargs={"chave": CHAVE_LIMIAR}))
        self.assertNotContains(resposta, "Voltar ao padrão")

        servico.definir(CHAVE_LIMIAR, "9", self.usuario)

        resposta = self.client.get(reverse("editar_configuracao", kwargs={"chave": CHAVE_LIMIAR}))
        self.assertContains(resposta, "Voltar ao padrão")
        self.assertContains(
            resposta, reverse("voltar_padrao_configuracao", kwargs={"chave": CHAVE_LIMIAR})
        )
