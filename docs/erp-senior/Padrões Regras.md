
# Padrão para Regras

---

## Introdução

Este documento define a **padronização de código-fonte** para customizações realizadas na plataforma **Senior**. O objetivo é unificar padrões e orientar o desenvolvimento de **regras, serviços, telas, tabelas e relatórios**, garantindo consistência, qualidade e facilidade de manutenção.

Abrange as seguintes áreas:

- Editor de Regras
- WebServices
- Telas SGI
- CBDS
- Gerador de Relatório

---

## 1. Editor de Regras

### Variáveis Alfanuméricas

- Prefixo: `a`
- Formato: `a<NomeVariavel>`

```text
Definir Alfa aNomFun;
Definir Alfa aNomCli;
```

### Variáveis Numéricas

- Prefixo: `n`
- Formato: `n<NomeVariavel>`

```text
Definir Numero nNumCad;
Definir Numero nCodCli;
```

### Variáveis de Data

- Prefixo: `d`
- Formato: `d<NomeVariavel>`

```text
Definir Data dDatRef;
Definir Data dDatEmi;
```

### Variáveis de Serviço

- Prefixo: `s`
- Formato: `s<NomeVariavel>`

```text
Definir interno.com.senior.g5.rh.fp.calculoFolha.Calcular sCalFol;
Definir interno.com.senior.g5.co.mfi.cpa.titulos.GerarBaixaAproveitamentoCP sBaiTit;
```

### Cursores

- Prefixo: `Cur_`
- Formato: `Cur_<Identificacao>`

```text
Definir Cursor Cur_E085CLI;
```

### Cursores SQL Data

```text
Definir Alfa aE075PRO;
Definir Alfa aSqlPro;
```

```sql
Cur_E075PRO.Sql "SELECT CodStr  FROM E075PRO  WHERE CodEmp = :nCodEmp  AND CodPro = :aCodPro";
```

```text
aSqlPro = "SELECT CodStr" +
          " FROM E075Pro" +
          " WHERE CodEmp = " + aCodEmp +
          " AND CodPro = '" + aCodPro + "'";
```

---

## 2. Editor de WebServices

### Nome do Serviço

Formato:

```text
custom.senior.modulo.nomeServico
```

Exemplos de módulos:

- `cad` – Cadastro
- `cpr` – Compras
- `ven` – Vendas

> Em nomes compostos, a segunda palavra deve iniciar com letra maiúscula.

### Nome da Porta

```text
NomePorta
```

> Em nomes compostos, todas as palavras iniciam com letra maiúscula.

### Parâmetros

- Prefira o tipo **Tabela** para entrada de dados em lote.
- O tipo inteiro possui limite máximo de **9 dígitos**.

---

## 3. Telas SGI

### Interface

- Prefixo: `I`
- Formato: `I<Identificacao>`

### Formulário

- Prefixo: `F`
- Formato: `F<Identificacao>`

---

## 4. CBDS

### Criação de Tabelas

- Prefixo obrigatório: `USU_T`
- Padrão: 3 letras para **processo** + 3 letras para **funcionalidade**

```text
USU_T<PRO><FUN>
```

#### Exemplo – Integração com Cielo

```text
USU_TCIEPAR – Parâmetros
USU_TCIEMOV – Movimentação
USU_TCIELOG – Log
USU_TCIECAR – Cartão de Crédito
```

--- 

### Convenção de Variáveis

- 3 letras para a primeira palavra
- 3 letras para a segunda palavra
- Ambas iniciando com letra maiúscula

