import json
import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from accounts.models import DispositivoNotificacao
from accounts.services.notificacoes import enviar_notificacao_usuario
from SIGMA.autorizacao import PERMISSAO_ADMINISTRAR_ACESSOS, permissao_requerida

logger = logging.getLogger(__name__)


@login_required
@require_GET
def utilitarios(request):
    pode_enviar_email_teste = (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.has_perm(PERMISSAO_ADMINISTRAR_ACESSOS)
    )
    return render(
        request,
        "accounts/utilitarios.html",
        {"pode_enviar_email_teste": pode_enviar_email_teste},
    )


@login_required
@require_GET
def baixar_apk_sigma(request):
    caminho = Path(settings.SIGMA_APK_FILE)
    if not caminho.is_absolute():
        caminho = settings.BASE_DIR / caminho
    if not caminho.is_file():
        raise Http404("APK do SIGMA não disponível.")

    return FileResponse(
        caminho.open("rb"),
        as_attachment=True,
        filename="SIGMA.apk",
        content_type="application/vnd.android.package-archive",
    )


@login_required
@require_POST
def registrar_dispositivo_notificacao(request):
    try:
        dados = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    token = str(dados.get("token", "")).strip()
    if not token or len(token) > 4096:
        return JsonResponse({"erro": "Token inválido."}, status=400)

    dispositivo, criado = DispositivoNotificacao.objects.update_or_create(
        token=token,
        defaults={
            "usuario": request.user,
            "plataforma": "android",
            "ativo": True,
        },
    )
    return JsonResponse({"registrado": True, "criado": criado, "id": dispositivo.pk})


@login_required
@require_POST
def enviar_notificacao_teste(request):
    try:
        resultado = enviar_notificacao_usuario(
            request.user,
            "Teste do SIGMA",
            "As notificações do aplicativo estão funcionando.",
            {"tipo": "teste"},
        )
    except ImproperlyConfigured:
        return JsonResponse({"erro": "Firebase não configurado no servidor."}, status=503)

    if resultado["enviadas"] == 0:
        return JsonResponse(
            {"erro": "Nenhum dispositivo recebeu a notificação.", **resultado},
            status=502,
        )
    return JsonResponse({"enviado": True, **resultado})


@permissao_requerida(PERMISSAO_ADMINISTRAR_ACESSOS)
@require_POST
def enviar_email_teste(request):
    try:
        dados = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    email = str(dados.get("email", "")).strip()
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"erro": "E-mail inválido."}, status=400)

    try:
        enviados = send_mail(
            subject="SIGMA - Teste de envio de e-mail",
            message="Este é um e-mail de teste enviado pelo SIGMA.",
            from_email=None,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        # Detalhe completo (servidor, extensão da exceção SMTP) fica no log do
        # servidor; a resposta expõe apenas mensagem genérica ao operador.
        logger.exception("Falha no envio de e-mail de teste para %s.", email)
        return JsonResponse(
            {
                "enviado": False,
                "erro": "Não foi possível enviar o e-mail. Verifique os registros do servidor.",
            },
            status=502,
        )

    if enviados == 0:
        return JsonResponse({"enviado": False, "erro": "Nenhum e-mail foi enviado."}, status=502)
    return JsonResponse({"enviado": True, "destinatario": email})
