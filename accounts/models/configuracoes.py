from django.conf import settings
from django.db import models


class ConfiguracaoAplicacao(models.Model):
    """Variável de configuração não sensível da aplicação, editável em runtime.

    POLÍTICA: nada de segredo aqui — nem na chave, nem no valor. Credencial
    (senha, token, chave de API) continua exclusivamente no `.env` (dev) ou
    `/etc/sigma/sigma.env` (produção), lida por `os.getenv()` apenas em
    `SIGMA/settings.py`. O service de leitura rejeita chaves cujo nome
    carrega padrão de segredo (PASSWORD, SECRET, TOKEN, KEY, CREDENTIAL)
    para que a tabela não vire um `.env` paralelo.

    O rastreio (`atualizado_por`/`atualizado_em`) é a trilha consultável
    desta tela: quem alterou e quando ficam no próprio registro; o log
    operacional registra o fato sem repetir o valor (a chave é genérica e
    o valor, embora não sensível por política, não precisa viver em log).

    Toda gravação passa por `definir()` (accounts/services/configuracoes.py)
    ou por save/exclusão por instância: são os signals `post_save`/
    `post_delete` que mantêm o cache in-process do service fresco. Gravação
    por `queryset.update()`, `bulk_update()` ou SQL cru NÃO dispara signal —
    grava deixando o cache servindo valor velho, sem aviso. Proibido nestes
    caminhos nesta tabela.

    DESENHO DA TELA (dono do produto, 2026-08): a chave é parte do código,
    não da tela. A tela só edita descrição e valor das chaves declaradas em
    `CHAVES_CONHECIDAS` (accounts/services/configuracoes.py); chave nova de
    configuração = nova declaração lá (código versionado), nunca criação em
    runtime. A tabela é espelho do registro declarado: linha excluída por
    qualquer via → a listagem volta a mostrar o default do código e a chave
    é reconfigurada pela edição. Linha com chave fora do registro não é
    gerida pela tela — o guard de leitura do service é quem a protege.
    """

    chave = models.CharField(max_length=100, unique=True, verbose_name="Chave")
    valor = models.TextField(verbose_name="Valor")
    descricao = models.TextField(verbose_name="Descrição")
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configuracoes_alteradas",
        verbose_name="Atualizado por",
    )
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        db_table = "configuracoes_aplicacao"
        verbose_name = "Configuração da aplicação"
        verbose_name_plural = "Configurações da aplicação"
        ordering = ["chave"]
        # O projeto desliga as permissões padrão do Django (manage.py
        # desconecta create_permissions); a permissão desta tela nasce por
        # função pós-migrate em accounts/models/permissoes.py.
        default_permissions = ()

    def __str__(self):
        return self.chave
