from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "estudos" / "estudo-viabilidade-cmms-sigma.pdf"
FONT_DIR = Path(r"C:\Windows\Fonts")


def paragraph(text, style):
    return Paragraph(text, style)


def bullet(text, styles):
    return Paragraph(f"<bullet>&bull;</bullet>{text}", styles["sigma-bullet"])


def page_number(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D7DED9"))
    canvas.line(1.7 * cm, 1.35 * cm, 19.3 * cm, 1.35 * cm)
    canvas.setFont("Arial", 8)
    canvas.setFillColor(colors.HexColor("#607066"))
    canvas.drawString(1.7 * cm, 0.85 * cm, "SIGMA | Estudo de viabilidade CMMS")
    canvas.drawRightString(19.3 * cm, 0.85 * cm, f"Página {document.page}")
    canvas.restoreState()


def heading(text, styles):
    return [Paragraph(text, styles["sigma-h1"]), Spacer(1, 0.18 * cm)]


def table(data, widths):
    result = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEFE5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#102019")),
                ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Arial"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.2),
                ("LEADING", (0, 0), (-1, -1), 10.3),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CFD9D3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6F3")]),
            ]
        )
    )
    return result


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "arialbd.ttf")))

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="sigma-title", fontName="Arial-Bold", fontSize=27, leading=32, textColor=colors.HexColor("#102019"), alignment=TA_LEFT, spaceAfter=10))
    styles.add(ParagraphStyle(name="sigma-subtitle", fontName="Arial", fontSize=13, leading=18, textColor=colors.HexColor("#34483C"), spaceAfter=16))
    styles.add(ParagraphStyle(name="sigma-h1", fontName="Arial-Bold", fontSize=17, leading=21, textColor=colors.HexColor("#102019"), spaceBefore=1, spaceAfter=4))
    styles.add(ParagraphStyle(name="sigma-h2", fontName="Arial-Bold", fontSize=11.5, leading=15, textColor=colors.HexColor("#102019"), spaceBefore=8, spaceAfter=4))
    styles.add(ParagraphStyle(name="sigma-body", fontName="Arial", fontSize=10, leading=14, textColor=colors.HexColor("#1D2922"), spaceAfter=7))
    styles.add(ParagraphStyle(name="sigma-bullet", fontName="Arial", fontSize=9.8, leading=14, leftIndent=13, firstLineIndent=-8, textColor=colors.HexColor("#1D2922"), spaceAfter=4))
    styles.add(ParagraphStyle(name="sigma-callout", fontName="Arial-Bold", fontSize=13, leading=18, textColor=colors.white, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="sigma-small", fontName="Arial", fontSize=8.4, leading=11, textColor=colors.HexColor("#4C5B51")))
    for legacy, current in {
        "h1": "sigma-h1", "h2": "sigma-h2", "body": "sigma-body",
        "bullet": "sigma-bullet", "small": "sigma-small",
    }.items():
        styles.byName[legacy] = styles.byName[current]

    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4, rightMargin=1.7 * cm, leftMargin=1.7 * cm,
        topMargin=1.6 * cm, bottomMargin=1.8 * cm, title="Estudo de viabilidade: CMMS no SIGMA",
        author="IPEL",
    )
    story = []

    story.extend([
        Spacer(1, 2.3 * cm),
        Paragraph("ESTUDO DE VIABILIDADE", styles["sigma-small"]),
        Spacer(1, 0.2 * cm),
        Paragraph("SIGMA pode incorporar o CMMS hoje atendido pelo Sadege?", styles["sigma-title"]),
        Paragraph("Análise de aderência funcional, base técnica existente, lacunas e decisão estratégica.", styles["sigma-subtitle"]),
        Spacer(1, 1.2 * cm),
        Table([[Paragraph("Conclusão", styles["sigma-callout"])]], colWidths=[17.6 * cm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0D5C3B")),
            ("BOX", (0, 0), (-1, -1), 0, colors.white),
            ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 16), ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ])),
        Spacer(1, 0.35 * cm),
        Paragraph("Faz sentido estratégico e técnico, desde que seja uma migração progressiva de capacidade e dados. O SIGMA já contém parte importante do domínio; não possui ainda paridade CMMS para substituir o Sadege integralmente.", styles["sigma-body"]),
        Spacer(1, 4.1 * cm),
        Paragraph("Base: cenário atual do SIGMA e informações públicas dos portais Sadege, consultadas em 31/08/2026.", styles["sigma-small"]),
        PageBreak(),
    ])

    story += heading("1. Pergunta que este estudo responde", styles)
    story.append(Paragraph("A IPEL deve concentrar dentro do SIGMA as capacidades de gestão da manutenção hoje atendidas pelo Sadege?", styles["h2"]))
    story.append(Paragraph("Não é proposta de escopo, prazo ou substituição imediata. É avaliação de sentido estratégico: aderência, vantagens, riscos, dependências e condição mínima para decidir.", styles["body"]))
    story.append(Paragraph("Tese", styles["h2"]))
    for text in [
        "O SIGMA é o ponto natural de convergência operacional porque já conhece usuários, filiais, recursos, turnos, OPs, paradas, telemetria e integrações industriais.",
        "O Sadege é especializado em CMMS e possui recursos que ainda não estão presentes no SIGMA: preventiva estruturada, custos, estoque de manutenção, checklists, metrologia e indicadores de manutenção completos.",
        "Portanto: incorporar faz sentido; substituir agora não. A decisão deve ser por migração progressiva, com operação paralela e aceite do PCM, manutenção e qualidade.",
    ]:
        story.append(bullet(text, styles))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("O que o Sadege declara publicamente", styles["h2"]))
    for text in [
        "CMMS para ativos, OS, planejamento, execução, indicadores, custos e histórico técnico; inclui portal de solicitações para funcionários, fornecedores e clientes.",
        "Registro de defeitos, ações, materiais, peças, funcionários, horas e tempo de máquina parada.",
        "Preventiva, controle de estoque, checklists, calendário, mobile, QR Code e Web API para ERP, MES e demais plataformas corporativas.",
        "Módulo de metrologia com instrumentos, calibração, certificados, prazos e alertas; referência a ISO 9001 e ISO/IEC 17025.",
        "Sensores IoT e discurso de manutenção preditiva; este ponto exige validação técnica contratual, não apenas material comercial.",
    ]:
        story.append(bullet(text, styles))
    story.append(PageBreak())

    story += heading("2. Base já existente no SIGMA", styles)
    story.append(Paragraph("O SIGMA não começa do zero. Seu domínio industrial já oferece fundações que um CMMS isolado precisa integrar ou replicar.", styles["body"]))
    data = [
        ["Base SIGMA", "Uso potencial no CMMS interno", "Leitura estratégica"],
        ["Recurso, centro, setor, filial", "Cadastro mestre de ativos e escopo operacional", "Evita duplicidade de equipamentos e responsabilidade."],
        ["Chamado, OS e interações", "Solicitação, execução e histórico", "Núcleo CMMS já modelado; precisa amadurecer processo e dados."],
        ["QR Code por recurso", "Abertura e consulta no chão de fábrica", "Reduz atrito e replica prática típica de CMMS."],
        ["Paradas e justificativas", "Gatilho, impacto e causa da manutenção", "Conecta falha física a impacto produtivo real."],
        ["Telemetria HTTP e regras", "Manutenção baseada em condição", "Base para alertas; não equivale ainda a predição validada."],
        ["Calendários, turnos, horas extras", "Planejamento e agenda", "Já existe contexto de disponibilidade da fábrica."],
        ["LDAP, permissões, e-mail, mobile", "Acesso, responsabilização e comunicação", "Infraestrutura transversal já resolvida."],
        ["ERP, Oracle e WMS", "Materiais, custos e contexto de produção", "Integrações internas já têm padrão de filas e reprocessamento."],
    ]
    story.append(table([[paragraph(cell, styles["small"]) for cell in row] for row in data], [4.1 * cm, 6.4 * cm, 7.1 * cm]))
    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Vantagem estrutural", styles["h2"]))
    story.append(Paragraph("Em um CMMS dentro do SIGMA, uma OS pode nascer de chamado, QR Code, calendário, parada ou telemetria e carregar automaticamente ativo, área, turno e impacto na produção. Essa conexão é a principal razão para internalizar.", styles["body"]))
    story.append(PageBreak())

    story += heading("3. Aderência: Sadege x SIGMA", styles)
    data = [
        ["Capacidade", "Sadege público", "SIGMA atual", "Situação"],
        ["Chamados e OS", "Completo", "Chamados, OS e interações", "Base existente"],
        ["Ativos", "Gestão de ativos", "Recursos produtivos", "Parcial"],
        ["Histórico técnico", "Defeitos, ações, equipe, horas", "Interações e histórico básico", "Parcial"],
        ["Paradas e disponibilidade", "Indicadores e horas paradas", "Paradas, tempos, OEE em evolução", "Base existente"],
        ["Preventiva", "Planejamento e controle preventivo", "Calendários e workers; plano preventivo ainda não estruturado", "Lacuna"],
        ["Checklists", "Checklists", "Ainda não disponível", "Lacuna"],
        ["Materiais, peças e estoque", "Controle e custo", "Integração ERP/WMS, sem CMMS próprio", "Lacuna"],
        ["Custos e orçamento", "Por ativo, equipe e material", "Ainda não disponível", "Lacuna"],
        ["Indicadores CMMS", "Confiabilidade, defeitos, custos", "OEE/paradas; MTBF e MTTR ainda não calculados", "Parcial"],
        ["Mobile e QR Code", "Mobile e QR Code", "Capacitor, push e QR por recurso", "Base existente"],
        ["Metrologia", "Calibração, certificados e alertas", "Ainda não disponível", "Lacuna relevante"],
        ["Sensores e predição", "IoT e predição comercial", "Telemetria HTTP e regra de parada", "Base inicial"],
    ]
    story.append(table([[paragraph(cell, styles["small"]) for cell in row] for row in data], [3.2 * cm, 4.4 * cm, 5.8 * cm, 4.2 * cm]))
    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Leitura", styles["h2"]))
    story.append(Paragraph("SIGMA já cobre a borda operacional de manutenção. Sadege ainda é mais maduro no núcleo de PCM: planejamento preventivo, execução padronizada, custo, materiais, indicadores e metrologia.", styles["body"]))
    story.append(PageBreak())

    story += heading("4. Benefícios de incorporar ao SIGMA", styles)
    benefits = [
        ["Benefício", "Efeito para IPEL"],
        ["Fonte única de operação", "Produção, qualidade, manutenção, paradas e ativos passam a usar mesmas referências e mesmas regras de filial."],
        ["Menos duplicidade", "Reduz cadastros, sincronizações e divergências entre recurso no SIGMA e ativo no CMMS externo."],
        ["Decisão baseada em contexto", "Manutenção deixa de analisar apenas OS: passa a cruzar OP, turno, perda de produção, parada, qualidade e telemetria."],
        ["Evolução alinhada à fábrica", "Fluxos podem ser modelados pela realidade IPEL, sem depender de customização externa para cada particularidade."],
        ["Integração governada", "Uso dos padrões existentes de autenticação, permissões, filas, log e tratamento de falha."],
        ["Continuidade de conhecimento", "Dados e regras críticas permanecem no ecossistema interno, com dependência menor de contrato e roadmap de fornecedor."],
    ]
    story.append(table([[paragraph(cell, styles["small"]) for cell in row] for row in benefits], [5.1 * cm, 12.5 * cm]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Benefício que não deve ser prometido sem medição", styles["h2"]))
    story.append(Paragraph("Economia, ganho de produtividade ou redução de paradas só podem compor caso de negócio após linha de base: custo atual do Sadege, horas administrativas, taxa de OS no prazo, disponibilidade, backlog e custo de falha. Números comerciais do fornecedor não são prova de resultado para a IPEL.", styles["body"]))
    story.append(PageBreak())

    story += heading("5. Riscos e condições para decisão", styles)
    risks = [
        ["Risco", "Como controlar"],
        ["Substituir antes da paridade", "Definir capacidades mínimas e aceite formal; Sadege permanece até conclusão comprovada."],
        ["Perda de histórico", "Inventariar exportações, anexos, certificados, OS abertas, planos, ativos e vínculos antes de migrar."],
        ["Copiar software, não processo", "Mapear processo IPEL com PCM, técnicos e produção; desenhar somente necessidades reais."],
        ["Dados de manutenção pouco confiáveis", "Normalizar ativos, tipos de falha, causas, tempos, materiais e responsáveis antes de usar KPI ou predição."],
        ["Telemetria virar promessa de IA", "Usar primeiro alertas e manutenção por condição; validar dados e taxa de acerto antes de qualquer predição."],
        ["Metrologia subestimada", "Tratar como domínio auditável próprio: instrumento, padrão, certificado, validade, tolerância e evidência."],
        ["Dependência operacional durante transição", "Operação paralela, reconciliação periódica e plano de reversão por processo."],
    ]
    story.append(table([[paragraph(cell, styles["small"]) for cell in row] for row in risks], [5.2 * cm, 12.4 * cm]))
    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Perguntas que precisam de resposta antes da decisão final", styles["h2"]))
    for text in [
        "Quais módulos Sadege a IPEL usa de fato, com quais volumes, usuários, integrações e relatórios?",
        "Qual custo total atual: licenças, implantação, customizações, suporte e esforço interno?",
        "O contrato permite exportar integralmente dados, anexos, certificados e histórico em formato utilizável?",
        "Quais fluxos são obrigatórios por auditoria, qualidade, segurança e metrologia?",
        "Quais indicadores realmente orientam decisão hoje e qual sua fonte de verdade?",
    ]:
        story.append(bullet(text, styles))
    story.append(PageBreak())

    story += heading("6. Parecer final", styles)
    story.append(Paragraph("Decisão recomendada: aprovar estudo de transição e validação de paridade; não aprovar desligamento imediato do Sadege.", styles["h2"]))
    for text in [
        "Faz sentido incorporar CMMS ao SIGMA porque a plataforma já detém o contexto operacional que dá valor à manutenção: recurso, parada, turno, OP, telemetria, usuários e integrações.",
        "A internalização pode eliminar duplicidade e melhorar decisões, especialmente ao relacionar manutenção e impacto produtivo real.",
        "O SIGMA ainda não tem paridade total com o Sadege. Preventiva, checklists, materiais/custos, indicadores CMMS, metrologia e migração de histórico são condições críticas.",
        "A rota racional é migrar capacidades em ondas, mantendo Sadege como referência operacional até cada capacidade e seus dados serem aceitos pelos donos do processo.",
    ]:
        story.append(bullet(text, styles))
    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Critério objetivo de sucesso", styles["h2"]))
    story.append(Paragraph("A decisão de desligar Sadege só é defensável quando SIGMA executar todos os fluxos usados pela IPEL, preservar o histórico necessário, atender requisitos de auditoria/metrologia e produzir indicadores conciliados durante período de operação paralela.", styles["body"]))
    story.append(Spacer(1, 0.45 * cm))
    story.append(Paragraph("Fontes", styles["h2"]))
    sources = [
        "Referências internas do SIGMA: visão geral, dados, integrações, operação, fluxos de negócio e acessos.",
        "Sadege. Portal institucional e CMMS: https://sadege.com.br/ e https://sadege.com.br/sobre. Consulta em 31/08/2026.",
        "Sadege/Maximiza. Portal institucional anterior: https://site.sadege.com.br/. Consulta em 31/08/2026.",
        "Sadege. Gestão Inteligente de Calibração e Metrologia: https://sadege.com.br/metrologia. Consulta em 31/08/2026.",
        "As capacidades Sadege foram extraídas de material público de fornecedor; a validação final requer demonstração contratada, inventário de uso IPEL e prova de exportação de dados.",
    ]
    for source in sources:
        story.append(bullet(source, styles))

    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)
    print(OUTPUT)


if __name__ == "__main__":
    main()
