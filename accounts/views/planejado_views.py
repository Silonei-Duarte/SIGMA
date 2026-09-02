from datetime import datetime

from django.contrib import messages
from django.shortcuts import render

from SIGMA.autorizacao import permissao_requerida

from ..utils.planejado import consolidar_planejado_periodo


@permissao_requerida("accounts.manipular_cadastros")
def reprocessar_planejado(request):

    if request.method == "POST":
        data_inicio_str = request.POST.get("data_inicio")
        data_fim_str = request.POST.get("data_fim")

        try:
            data_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d").date()
            data_fim = datetime.strptime(data_fim_str, "%Y-%m-%d").date()

            if data_fim < data_inicio:
                messages.error(request, "A data final não pode ser anterior à data inicial.")
            else:
                consolidar_planejado_periodo(data_inicio, data_fim)
                messages.success(
                    request, f"Processamento de {data_inicio} até {data_fim} concluído com sucesso!"
                )
        except ValueError, TypeError:
            messages.error(request, "Formato de data inválido.")

    return render(request, "accounts/reprocessar_planejado.html")
