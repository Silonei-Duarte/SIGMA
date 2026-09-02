import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SIGMA_DOCS_DIR = BASE_DIR / "sigma"
# A documentação foi dividida em arquivos numerados (docs/sigma/README.md
# é o índice); o manual em PDF concatena esses arquivos, nesta ordem, e
# não inclui o índice nem o Style Guide (que tem publicação própria).
MD_FILES = [
    SIGMA_DOCS_DIR / name
    for name in [
        "01-visao-geral.md",
        "02-arquitetura-tecnica.md",
        "03-servidor-e-hospedagem.md",
        "04-aplicativo-mobile.md",
        "05-dados-e-bancos.md",
        "06-rotas-e-navegacao.md",
        "07-integracoes-externas.md",
        "08-operacao-e-workers.md",
        "09-fluxos-de-negocio.md",
        "10-parametrizacoes.md",
        "11-seguranca-e-acessos.md",
    ]
]
PDF_FILE = BASE_DIR / "documento_mestre_sigma_pdflatex.pdf"

TITLE = "Documento Mestre do Sistema SIGMA"
TOC_TITLE = "Sumário"
LANG = "pt-BR"
FONT_SIZE = "10pt"
MARGIN = "1.7cm"


PDF_STYLE = r"""
\usepackage{iftex}
\ifPDFTeX
\else
  \usepackage{fontspec}
  \IfFontExistsTF{Calibri}{
    \setmainfont{Calibri}
    \setsansfont{Calibri}
  }{}
\fi

\usepackage{array}
\usepackage{etoolbox}
\usepackage[table]{xcolor}
\usepackage{titlesec}
\usepackage{titling}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{microtype}
\usepackage{needspace}
\usepackage{enumitem}
\usepackage{fancyvrb}

\definecolor{SigmaNavy}{RGB}{23,43,77}
\definecolor{SigmaBlue}{RGB}{0,91,150}
\definecolor{SigmaTeal}{RGB}{0,126,132}
\definecolor{SigmaText}{RGB}{35,39,47}
\definecolor{SigmaMuted}{RGB}{96,108,124}
\definecolor{SigmaRule}{RGB}{178,190,205}
\definecolor{TableStripe}{RGB}{222,235,249}
\definecolor{TableHeader}{RGB}{55,91,130}
\definecolor{TableRule}{RGB}{86,105,128}
\definecolor{CodeRule}{RGB}{199,209,222}

\AtBeginDocument{
  \hypersetup{
    colorlinks=true,
    linkcolor=SigmaBlue,
    urlcolor=SigmaTeal,
    citecolor=SigmaBlue
  }
}

\renewcommand{\familydefault}{\sfdefault}
\color{SigmaText}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}

\pretitle{
  \begin{center}
  \vspace*{1.2cm}
  {\color{SigmaTeal}\rule{0.18\textwidth}{3pt}}\par
  \vspace{0.8cm}
  \Huge\bfseries\color{SigmaNavy}
}
\posttitle{
  \par\vspace{0.45cm}
  {\Large\color{SigmaMuted}Arquitetura, integrações, infraestrutura e fluxos operacionais}\par
  \vspace{0.8cm}
  {\color{SigmaRule}\rule{0.72\textwidth}{0.7pt}}\par
  \vspace{1.6cm}
  \end{center}
}
\preauthor{\begin{center}\large\color{SigmaMuted}}
\postauthor{\end{center}}
\predate{\begin{center}\small\color{SigmaMuted}}
\postdate{\end{center}\newpage}

\titleformat{\section}
  {\Needspace{8\baselineskip}\Large\bfseries\color{SigmaNavy}}
  {\thesection}{0.8em}{}
  [\vspace{-0.35em}{\color{SigmaTeal}\titlerule[1.2pt]}]

\titleformat{\subsection}
  {\Needspace{6\baselineskip}\large\bfseries\color{SigmaBlue}}
  {\thesubsection}{0.75em}{}

\titleformat{\subsubsection}
  {\Needspace{5\baselineskip}\normalsize\bfseries\color{SigmaTeal}}
  {\thesubsubsection}{0.7em}{}

\titleformat{\paragraph}
  {\Needspace{4\baselineskip}\normalsize\bfseries\color{SigmaNavy}}
  {\theparagraph}{0.7em}{}

\titlespacing*{\section}{0pt}{2.0ex plus .4ex}{1.2ex}
\titlespacing*{\subsection}{0pt}{1.6ex plus .3ex}{0.8ex}
\titlespacing*{\subsubsection}{0pt}{1.3ex plus .2ex}{0.55ex}

\pagestyle{fancy}
\fancyhf{}
\lhead{\small\color{SigmaMuted}Documento Mestre SIGMA}
\rhead{\small\color{SigmaMuted}\leftmark}
\cfoot{\small\color{SigmaMuted}\thepage\ de \pageref{LastPage}}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0pt}
\renewcommand{\headrule}{\hbox to\headwidth{\color{SigmaRule}\leaders\hrule height \headrulewidth\hfill}}

\setlist[itemize]{leftmargin=1.3em,itemsep=2pt,topsep=3pt}
\setlist[enumerate]{leftmargin=1.5em,itemsep=2pt,topsep=3pt}

\renewcommand{\arraystretch}{1.55}
\setlength{\tabcolsep}{8pt}
\arrayrulecolor{TableRule}

\makeatletter
\newcommand{\StopTableStripes}{\global\@rowcolorsfalse\@norowcolor}
\makeatother

\pretocmd{\endlongtable}{\StopTableStripes}{}{}
\pretocmd{\endtabular}{\StopTableStripes}{}{}

\AtBeginEnvironment{longtable}{\small\rowcolors{2}{TableStripe}{white}\arrayrulecolor{TableRule}}
\AtEndEnvironment{longtable}{\rowcolors{2}{}{}}

\AtBeginEnvironment{tabular}{\small\rowcolors{2}{TableStripe}{white}\arrayrulecolor{TableRule}}
\AtEndEnvironment{tabular}{\rowcolors{2}{}{}}

\let\OldTexttt\texttt
\renewcommand{\texttt}[1]{\begingroup\color{SigmaNavy}\OldTexttt{#1}\endgroup}

\fvset{
  fontsize=\small,
  frame=single,
  framesep=4pt,
  rulecolor=\color{CodeRule},
  commandchars=\\\{\}
}
"""


def sem_frontmatter(texto: str) -> str:
    """Remove o bloco YAML (titulo/ordem) do início do arquivo.

    Necessário porque, ao concatenar vários arquivos, só o primeiro bloco
    `---` do documento combinado pode ser metadado do pandoc — os demais
    apareceriam no PDF como texto solto entre dois filetes horizontais.
    """
    linhas = texto.splitlines()
    if linhas and linhas[0].strip() == "---":
        for i, linha in enumerate(linhas[1:], start=1):
            if linha.strip() == "---":
                return "\n".join(linhas[i + 1 :]).lstrip("\n")
    return texto


def find_executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found

    candidates = [
        Path.home() / "AppData/Local/Programs/MiKTeX/miktex/bin/x64" / name,
        Path("C:/Program Files/MiKTeX/miktex/bin/x64") / name,
        Path("C:/Program Files (x86)/MiKTeX/miktex/bin/x64") / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def run(command: list[str]) -> None:
    print("Executando:")
    print(" ".join(f'"{part}"' if " " in part else part for part in command))
    try:
        subprocess.run(command, cwd=BASE_DIR.parent, check=True)
    except subprocess.CalledProcessError as exc:
        if PDF_FILE.exists():
            print(
                "\nFalha ao gerar o PDF. Se o arquivo estiver aberto em outro programa, "
                "feche o PDF e rode o script novamente.",
                file=sys.stderr,
            )
        raise exc


def main() -> int:
    faltando = [str(f) for f in MD_FILES if not f.exists()]
    if faltando:
        print("Arquivo(s) Markdown não encontrado(s):", file=sys.stderr)
        for f in faltando:
            print(f"  {f}", file=sys.stderr)
        return 1

    pandoc = find_executable("pandoc.exe") or find_executable("pandoc")
    pdf_engine = (
        find_executable("pdflatex.exe")
        or find_executable("pdflatex")
        or find_executable("xelatex.exe")
        or find_executable("xelatex")
    )

    if not pandoc:
        print("Pandoc não encontrado no PATH.", file=sys.stderr)
        return 1
    if not pdf_engine:
        print("XeLaTeX/pdflatex não encontrado. Verifique a instalação do MiKTeX.", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="manual_pdf_") as temp_dir:
        style_file = Path(temp_dir) / "pdf_style.tex"
        style_file.write_text(PDF_STYLE.strip() + "\n", encoding="utf-8")

        combinado = Path(temp_dir) / "documento_combinado.md"
        partes = [sem_frontmatter(f.read_text(encoding="utf-8")) for f in MD_FILES]
        combinado.write_text("\n\n\\newpage\n\n".join(partes) + "\n", encoding="utf-8")

        command = [
            pandoc,
            str(combinado),
            "-o",
            str(PDF_FILE),
            f"--pdf-engine={pdf_engine}",
            "--pdf-engine-opt=-interaction=nonstopmode",
            "--toc",
            "-V",
            f"toc-title={TOC_TITLE}",
            "-V",
            f"lang={LANG}",
            "-V",
            f"geometry:margin={MARGIN}",
            "-V",
            f"fontsize={FONT_SIZE}",
            "-V",
            f"title={TITLE}",
            "-H",
            str(style_file),
        ]

        run(command)
    print(f"PDF gerado: {PDF_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
