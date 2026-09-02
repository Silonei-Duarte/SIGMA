/*
Regra agendadora para baixa e estorno de componentes ERP.

Fluxo (baixa - USU_TBXACMP):
1) Busca o nivel de paralelismo em E000PDV.
2) Conta registros da USU_TBXACMP em processamento.
3) Seleciona pendencias com USU_SitPen = 1.
4) Marca as pendencias como USU_SitPen = 2.
5) Envia USU_IdeUni para o webservice CUSTOM.SENIOR.MAN.PRODUCAO.BAIXACOMPONENTEERP.

Fluxo (estorno - USU_TESTCMP):
1) Busca o nivel de paralelismo em E000PDV.
2) Conta registros da USU_TESTCMP em processamento.
3) Seleciona pendencias com USU_SitPen = 1.
4) Marca as pendencias como USU_SitPen = 2.
5) Envia USU_IdeUni para o webservice CUSTOM.SENIOR.MAN.PRODUCAO.ESTORNACOMP.

Fun_BuscaNivelParalelismo/Fun_RegistrosEmProcessamento sao compartilhadas pelos dois fluxos;
a linguagem nao suporta parametros em Funcao, entao aChaPdvSel/aTabelaSel selecionam o alvo
antes de cada chamada.
*/

Definir Funcao Fun_BuscaNivelParalelismo();
Definir Funcao Fun_RegistrosEmProcessamento();

Definir Alfa aCodEmp;
Definir Alfa aCurPar;
Definir Alfa aCurPen;
Definir Alfa aNivPar;
Definir Alfa aQtdPrc;
Definir Alfa aCmdSql;
Definir Alfa aIdeUni;
Definir Alfa aChaPdvSel;
Definir Alfa aTabelaSel;

Definir Numero nCodEmp;
Definir Numero nNivPar;
Definir Numero nQtdReg;
Definir Numero nQtdPrc;
Definir Numero nTemPen;

nCodEmp = CodEmp;
IntParaAlfa(nCodEmp, aCodEmp);

@ ========================================================================== @
@ Baixa de componentes (USU_TBXACMP)                                         @
@ ========================================================================== @
aChaPdvSel = "CUSTOM.SENIOR.MAN.PRODUCAO.BAIXACOMPONENTEERP";
aTabelaSel = "USU_TBXACMP";
Fun_BuscaNivelParalelismo();
Fun_RegistrosEmProcessamento();

nQtdPrc = nNivPar - nQtdReg;
IntParaAlfa(nQtdPrc, aQtdPrc);
nTemPen = 0;

Se (nQtdPrc > 0)
  {
    SQL_Criar(aCurPen);
    SQL_UsarSqlSenior2(aCurPen,0);
    SQL_UsarAbrangencia(aCurPen,0);

    aCmdSql = "Select USU_IdeUni \
                 From "+aTabelaSel+" \
                Where USU_CodEmp = "+aCodEmp+" \
                  And USU_SitPen = 1 \
             Order By USU_DatMov, USU_HorMov, USU_IdeUni \
          FETCH FIRST "+aQtdPrc+" ROWS ONLY";

    SQL_DefinirComando(aCurPen, aCmdSql);
    SQL_AbrirCursor(aCurPen);

    Enquanto (SQL_EOF(aCurPen) = 0)
      {
        SQL_RetornarAlfa(aCurPen, "USU_IdeUni", aIdeUni);

        ExecSql "Update "+aTabelaSel+" \
                    Set USU_SitPen = 2 \
                  Where USU_IdeUni = :aIdeUni \
                    And USU_SitPen = 1";

        Definir interno.custom.senior.man.producao.BaixaComponenteERP sBxaCmp;
        sBxaCmp.pendencias.criarLinha();
        sBxaCmp.pendencias.ideUni = aIdeUni;

        nTemPen = 1;

        SQL_Proximo(aCurPen);
      }

    SQL_FecharCursor(aCurPen);
    SQL_Destruir(aCurPen);
  }

Se (nTemPen = 1)
  {
    sBxaCmp.ModoExecucao = 3; @ 3-Assincrono @
    sBxaCmp.Executar();
  }

@ ========================================================================== @
@ Estorno de componentes (USU_TESTCMP)                                       @
@ ========================================================================== @
aChaPdvSel = "CUSTOM.SENIOR.MAN.PRODUCAO.ESTORNACOMP";
aTabelaSel = "USU_TESTCMP";
Fun_BuscaNivelParalelismo();
Fun_RegistrosEmProcessamento();

nQtdPrc = nNivPar - nQtdReg;
IntParaAlfa(nQtdPrc, aQtdPrc);
nTemPen = 0;

Se (nQtdPrc > 0)
  {
    SQL_Criar(aCurPen);
    SQL_UsarSqlSenior2(aCurPen,0);
    SQL_UsarAbrangencia(aCurPen,0);

    aCmdSql = "Select USU_IdeUni \
                 From "+aTabelaSel+" \
                Where USU_CodEmp = "+aCodEmp+" \
                  And USU_SitPen = 1 \
             Order By USU_DatPrc, USU_HorPrc, USU_IdeUni \
          FETCH FIRST "+aQtdPrc+" ROWS ONLY";

    SQL_DefinirComando(aCurPen, aCmdSql);
    SQL_AbrirCursor(aCurPen);

    Enquanto (SQL_EOF(aCurPen) = 0)
      {
        SQL_RetornarAlfa(aCurPen, "USU_IdeUni", aIdeUni);

        ExecSql "Update "+aTabelaSel+" \
                    Set USU_SitPen = 2 \
                  Where USU_IdeUni = :aIdeUni \
                    And USU_SitPen = 1";

        Definir interno.custom.senior.man.producao.EstornaComp sEstCmp;
        sEstCmp.pendencias.criarLinha();
        sEstCmp.pendencias.ideUni = aIdeUni;

        nTemPen = 1;

        SQL_Proximo(aCurPen);
      }

    SQL_FecharCursor(aCurPen);
    SQL_Destruir(aCurPen);
  }

Se (nTemPen = 1)
  {
    sEstCmp.ModoExecucao = 3; @ 3-Assincrono @
    sEstCmp.Executar();
  }

Funcao Fun_BuscaNivelParalelismo();
Inicio
  nNivPar = 0;

  SQL_Criar(aCurPar);
  SQL_UsarSqlSenior2(aCurPar,0);
  SQL_UsarAbrangencia(aCurPar,0);
  SQL_DefinirComando(aCurPar, "Select VlrPdv \
                                 From E000PDV \
                                Where ChaPdv = :aChaPdvSel \
                                  And IdeReg = :aCodEmp");
  SQL_DefinirAlfa(aCurPar, "aChaPdvSel", aChaPdvSel);
  SQL_DefinirAlfa(aCurPar, "aCodEmp", aCodEmp);
  SQL_AbrirCursor(aCurPar);

  Se (SQL_EOF(aCurPar) = 0)
    {
      SQL_RetornarAlfa(aCurPar, "VlrPdv", aNivPar);
      AlfaParaInt(aNivPar, nNivPar);
    }

  SQL_FecharCursor(aCurPar);
  SQL_Destruir(aCurPar);
Fim;

Funcao Fun_RegistrosEmProcessamento();
Inicio
  nQtdReg = 0;

  SQL_Criar(aCurPen);
  SQL_UsarSqlSenior2(aCurPen,0);
  SQL_UsarAbrangencia(aCurPen,0);
  aCmdSql = "Select Count(USU_CodEmp) QtdReg \
               From "+aTabelaSel+" \
              Where USU_CodEmp = :aCodEmp \
                And USU_SitPen = 2";
  SQL_DefinirComando(aCurPen, aCmdSql);
  SQL_DefinirAlfa(aCurPen, "aCodEmp", aCodEmp);
  SQL_AbrirCursor(aCurPen);

  Se (SQL_EOF(aCurPen) = 0)
    {
      SQL_RetornarInteiro(aCurPen, "QtdReg", nQtdReg);
    }

  SQL_FecharCursor(aCurPen);
  SQL_Destruir(aCurPen);
Fim;
