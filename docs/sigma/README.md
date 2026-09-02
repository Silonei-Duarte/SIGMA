---
titulo: Visão geral
ordem: 0
---

# Documentação do SIGMA

Registro do que o SIGMA é e do ambiente em que roda, na parte que é
segura de publicar — arquitetura técnica, sem detalhe de infraestrutura,
regra de negócio interna ou identidade de marca.

---

## Os documentos

| Documento | Assunto |
|---|---|
| [01 — Visão geral](01-visao-geral.md) | o que o sistema é, escopo, objetivos, organização funcional dos módulos |
| [02 — Arquitetura técnica](02-arquitetura-tecnica.md) | stack de backend e frontend, arquitetura lógica |
| [06 — Rotas e navegação](06-rotas-e-navegacao.md) | endereços internos por área do sistema |
| [10 — Parametrizações críticas](10-parametrizacoes.md) | parâmetros hierárquicos (filial → centro → recurso) que a regra de negócio consulta |
| [Sistema de design](Style-Guide-IPEL.md) | a interface do SIGMA: cores, tipografia, espaçamento, formas e componentes |
| [Documentação ERP](../erp-senior/Mapeamento_campos_USU.md) | dicionário de campos `USU_` customizados, índices Oracle e PostgreSQL — pasta `docs/erp-senior/` |

---

## Segredos

**Nenhuma credencial, chave ou senha existe neste repositório**, e nenhum
documento aqui indica onde elas estão guardadas.

- `.env` está no `.gitignore` e nunca deve ser commitado.
- `DJANGO_SECRET_KEY`, senha de banco e demais segredos são fornecidos
  fora do repositório.
- Ao documentar qualquer configuração nova, cite o **nome** da variável,
  nunca o valor.
