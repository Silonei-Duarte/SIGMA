from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import include, path, reverse

urlpatterns = [
    path("__reload__/", include("django_browser_reload.urls")),
    path("select2/", include("django_select2.urls")),
    path("", include("accounts.urls")),
    path("telemetria/", include("telemetria.urls")),
    path("producao/", include("producao.urls")),
    path("setores/", include("setores.urls")),
]


def redirect_root(request, exception=None):
    return redirect(settings.PORTAL_BASE_URL)


def _url_retorno_segura(request):
    """Aceita o Referer apenas quando ele pertence à mesma origem da requisição."""
    referer = request.headers.get("Referer", "")
    if not referer:
        return reverse("home")

    origem_requisicao = urlsplit(request.build_absolute_uri("/"))
    origem_referer = urlsplit(referer)
    if (
        origem_referer.scheme == origem_requisicao.scheme
        and origem_referer.netloc == origem_requisicao.netloc
    ):
        return referer

    return reverse("home")


def acesso_nao_autorizado(request, exception=None):
    """Responde negações de acesso sem revelar a permissão ou a rota protegida."""
    aceita_json = "application/json" in request.headers.get("Accept", "")
    requisicao_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if aceita_json or requisicao_ajax:
        return JsonResponse({"mensagem": "Acesso não autorizado."}, status=403)

    return render(
        request,
        "403.html",
        {"url_retorno": _url_retorno_segura(request)},
        status=403,
    )


handler404 = redirect_root
handler403 = acesso_nao_autorizado
