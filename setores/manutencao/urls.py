from django.urls import path

from setores.manutencao.views import chamados, ordens_servico

urlpatterns = [
    path("", chamados.listar_chamados, name="listar_chamados"),
    path("chamados/novo/", chamados.abrir_chamado, name="abrir_chamado"),
    path("<int:pk>/", chamados.detalhar_chamado, name="detalhar_chamado"),
    path("<int:pk>/excluir/", chamados.excluir_chamado, name="excluir_chamado"),
    path("recurso/<int:pk>/qrcode/", chamados.qrcode_recurso_pdf, name="qrcode_recurso_pdf"),
    path("recurso/qrcodes/", chamados.qrcode_recurso_pdf, name="qrcode_todos_recursos"),
    # --- Ordens de Serviço ---
    path("os/", ordens_servico.listar_os, name="listar_os"),
    path("os/abrir/", ordens_servico.abrir_os, name="abrir_os"),
    path("os/<int:pk>/", ordens_servico.detalhar_os, name="detalhar_os"),
    path("os/<int:pk>/excluir/", ordens_servico.excluir_os, name="excluir_os"),
    # --- rota AJAX ---
    path(
        "ajax_recursos_por_centro/",
        chamados.ajax_recursos_por_centro,
        name="ajax_recursos_por_centro",
    ),
]
