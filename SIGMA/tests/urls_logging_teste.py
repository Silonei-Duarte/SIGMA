"""URLconf mínimo usado só por `SIGMA/tests/test_logging.py`.

Existe uma única rota, que levanta uma exceção de propósito, para provar
que o `LOGGING` de `SIGMA/settings.py` recebe o traceback de um erro 500
real — sem depender de nenhuma view de produção nem alterar `SIGMA/urls.py`.
"""

from django.urls import path


def vista_que_gera_erro_500(request):
    """Levanta uma exceção não tratada de propósito, só para o teste de logging."""
    raise RuntimeError("erro sintético do teste de logging")


urlpatterns = [
    path("erro-sintetico-teste-logging/", vista_que_gera_erro_500),
]
