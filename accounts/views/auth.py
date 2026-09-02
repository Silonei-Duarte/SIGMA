from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render


def _normalizar_pagina_inicial(valor):
    pagina = (valor or "").strip()
    if not pagina:
        return ""
    parsed = urlsplit(pagina)
    if (
        parsed.scheme
        or parsed.netloc
        or not pagina.startswith("/")
        or pagina.startswith("//")
        or "\\" in pagina
    ):
        return ""
    return pagina


class PaginaInicialLoginView(LoginView):
    template_name = "accounts/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        redirect_url = self.get_redirect_url()
        if redirect_url:
            return redirect_url
        pagina_inicial = _normalizar_pagina_inicial(getattr(self.request.user, "paginicial", ""))
        return pagina_inicial or super().get_success_url()


@login_required
def home(request):
    pagina_inicial = _normalizar_pagina_inicial(getattr(request.user, "paginicial", ""))
    if pagina_inicial and urlsplit(pagina_inicial).path != request.path:
        return redirect(pagina_inicial)
    return render(request, "accounts/home.html")
