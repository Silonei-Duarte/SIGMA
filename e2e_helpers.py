"""Utilitário compartilhado dos testes E2E de composição visual.

Vive na raiz, ao lado do `conftest.py`, porque é usado por testes de
apps diferentes (`producao`, `setores.qualidade`, `accounts`) — não pode
morar no pacote de testes de um app só.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops


def pixels_iguais(imagem: bytes, baseline: Path) -> bool:
    """Equivalência VISUAL com tolerância: o antialiasing de fonte do
    Chromium varia por processo (deltas pequenos espalhados no texto), então
    comparação exata falha a cada execução. Ruído = deltas baixos em poucos
    pontos; regressão real (layout/cor/elemento) estoura a tolerância.
    """
    atual = Image.open(BytesIO(imagem)).convert("RGB")
    referencia = Image.open(baseline).convert("RGB")
    if atual.size != referencia.size:
        return False
    histograma = ImageChops.difference(atual, referencia).convert("L").histogram()
    criticos = sum(histograma[25:])  # delta por pixel acima de 24
    return criticos <= 0.005 * atual.size[0] * atual.size[1]
