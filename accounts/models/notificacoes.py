from django.conf import settings
from django.db import models


class DispositivoNotificacao(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dispositivos_notificacao",
    )
    token = models.TextField(unique=True)
    plataforma = models.CharField(max_length=20, default="android")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dispositivos_notificacao"
        default_permissions = ()
        verbose_name = "Dispositivo de notificação"
        verbose_name_plural = "Dispositivos de notificação"

    def __str__(self):
        return f"{self.usuario} - {self.plataforma}"
