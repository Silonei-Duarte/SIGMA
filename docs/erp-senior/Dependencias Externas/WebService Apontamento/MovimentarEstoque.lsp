Definir alfa wacao;
Definir alfa vaDados;
Definir alfa vaRet;
Definir alfa vaRetorno;
Definir alfa vaMsg;
Definir alfa aRetorno;
Definir alfa aRetornoMovimento;
Definir alfa aTipoRetorno;
Definir alfa CCurSaldo;

Definir alfa aCodEmp;
Definir alfa aCodFil;
Definir alfa aCodPro;
Definir alfa aCodDer;
Definir alfa aCodDep;
Definir alfa aCodTns;
Definir alfa aCodLot;
Definir alfa aQtdMov;
Definir alfa aUsuRes;
Definir alfa aDepTrf;
Definir alfa aMotMvp;
Definir alfa aAcaoBotao;
Definir alfa aDatMov;
Definir alfa aNumDoc;
Definir alfa aOriOrp;
Definir alfa aProTrf;
Definir alfa aDerTrf;

Definir numero nCodEmp;
Definir numero nCodFil;
Definir numero nQtdMov;
Definir numero nEntrouAcao;
Definir numero nTipoRetorno;
Definir numero nPos;
Definir numero nWebErr;
Definir numero nMovNec;
Definir numero nMovimentoOk;
Definir numero nSaldoOrigem;
Definir numero nSaldoDestino;
Definir numero VErro;
Definir data dDatMov;
Definir Alfa aMsgStr;

@ ========================================================================== @
@  VARIAVEIS RECEBIDAS                                                       @
@ ========================================================================== @

vaRetorno = "";
wacao = "";
vaMsg = "";
aRetorno = "";
aRetornoMovimento = "";
nTipoRetorno = 0;
nEntrouAcao = 0;
nMovNec = 1;
nMovimentoOk = 0;
nSaldoOrigem = 0;
nSaldoDestino = 0;

@ Captura unico JSON enviado em wdados @
MovimentarEstoque.tabelaEntradas.linhaatual = 0;
vaDados = MovimentarEstoque.tabelaEntradas.valor;
LimpaEspacos(vaDados);

ValorElementoJson(vaDados, "", "wacao", wacao);
ValorElementoJson(vaDados, "", "codEmp", aCodEmp);
ValorElementoJson(vaDados, "", "codFil", aCodFil);
ValorElementoJson(vaDados, "", "codPro", aCodPro);
ValorElementoJson(vaDados, "", "codDer", aCodDer);
ValorElementoJson(vaDados, "", "codDep", acodDep);
ValorElementoJson(vaDados, "", "codTns", aCodTns);
ValorElementoJson(vaDados, "", "codLot", aCodLot);
ValorElementoJson(vaDados, "", "qtdMov", aQtdMov);
ValorElementoJson(vaDados, "", "usuRes", aUsuRes);
ValorElementoJson(vaDados, "", "depTrf", aDepTrf);
ValorElementoJson(vaDados, "", "motMvp", aMotMvp);
ValorElementoJson(vaDados, "", "acaoBotao", aAcaoBotao);
ValorElementoJson(vaDados, "", "numDoc", aNumDoc);
ValorElementoJson(vaDados, "", "oriOrp", aOriOrp);
ValorElementoJson(vaDados, "", "proTrf", aProTrf);
ValorElementoJson(vaDados, "", "derTrf", aDerTrf);

AlfaParaInt(aCodEmp,nCodEmp);
AlfaParaInt(aCodFil,nCodFil);

TrocaEmpresaFilial(nCodEmp,nCodFil);

@ ========================================================================== @
@  MOVIMENTAR ESTOQUE                                                              @
@ ========================================================================== @

Se (wacao = "MOVIMENTAR-ESTOQUE")
  {
    nEntrouAcao = 1;

    Definir Alfa aMsgRet;
    Definir Alfa aErrExe;

    aMsgRet = "";
    aErrExe = "";

    @ A porta recebe quantidade como texto com virgula decimal. @
    SubstAlfa(".", ",", aQtdMov);
    AlfaParaDecimal(aQtdMov, nQtdMov);

    @ Reconhece reenvio quando a transferencia anterior ja levou toda a quantidade ao destino. @
    SQL_Criar(CCurSaldo);
    SQL_UsarSQLSenior2(CCurSaldo, 0);
    SQL_UsarAbrangencia(CCurSaldo, 0);
    SQL_DefinirComando(CCurSaldo, "SELECT NVL(SUM(CASE WHEN CODDEP = :aCodDep THEN QTDEST ELSE 0 END), 0) WWSALOR, \
                                      NVL(SUM(CASE WHEN CODDEP = :aDepTrf THEN QTDEST ELSE 0 END), 0) WWSALDES \
                                 FROM E210DLS \
                                WHERE CODEMP = :nCodEmp \
                                  AND CODPRO = :aCodPro \
                                  AND CODDER = :aCodDer \
                                  AND CODLOT = :aCodLot");
    SQL_DefinirAlfa(CCurSaldo, "aCodDep", aCodDep);
    SQL_DefinirAlfa(CCurSaldo, "aDepTrf", aDepTrf);
    SQL_DefinirInteiro(CCurSaldo, "nCodEmp", nCodEmp);
    SQL_DefinirAlfa(CCurSaldo, "aCodPro", aCodPro);
    SQL_DefinirAlfa(CCurSaldo, "aCodDer", aCodDer);
    SQL_DefinirAlfa(CCurSaldo, "aCodLot", aCodLot);
    SQL_AbrirCursor(CCurSaldo);
    Se (SQL_EOF(CCurSaldo) = 0)
      {
        SQL_RetornarFlutuante(CCurSaldo, "WWSALOR", nSaldoOrigem);
        SQL_RetornarFlutuante(CCurSaldo, "WWSALDES", nSaldoDestino);
      }
    SQL_Destruir(CCurSaldo);

    Se ((aCodDep <> aDepTrf) e (nSaldoOrigem <= 0) e (nSaldoDestino >= nQtdMov))
      {
        nMovNec = 0;
        nWebErr = 0;
        aRetorno = "Transferencia ja realizada. Saldo ja se encontra no deposito " + aDepTrf + ".";
        aRetornoMovimento = aRetorno;
        nMovimentoOk = 1;
      }

    Se ((nMovNec = 1) e (aCodDep = aDepTrf) e (((aCodPro = aProTrf) e (aCodDer = aDerTrf)) ou ((aProTrf = "") e (aDerTrf = ""))))
      {
        nMovNec = 0;
        nWebErr = 0;
        aRetorno = "Nenhum movimento necessario";
        aRetornoMovimento = aRetorno;
        nMovimentoOk = 1;
      }

    Se (nMovNec = 1)
      {
        Definir interno.com.senior.g5.co.mcm.est.estoques.MovimentarEstoque VMovEst;

        VMovEst.dadosGerais.CodEmp = aCodEmp;
        VMovEst.dadosGerais.CodFil = aCodFil;
        VMovEst.dadosGerais.CodPro = aCodPro;
        VMovEst.dadosGerais.CodDer = aCodDer;
        VMovEst.dadosGerais.CodDep = aCodDep;
        VMovEst.dadosGerais.CodTns = aCodTns;
        VMovEst.dadosGerais.QtdMov = aQtdMov;
        VMovEst.dadosGerais.MotMvp = aMotMvp;
        VMovEst.dadosGerais.CodLot = aCodLot;
        VMovEst.dadosGerais.DepTrf = aDepTrf;
        VMovEst.dadosGerais.NumDoc = aNumDoc;
        VMovEst.dadosGerais.OriOrp = aOriOrp;
        VMovEst.dadosGerais.ProTrf = aProTrf;
        VMovEst.dadosGerais.DerTrf = aDerTrf;

        VMovEst.ModoExecucao = 1;   
        VMovEst.Executar();
        aRetornoMovimento = VMovEst.retornoMovimento.retorno;
        aRetorno = aRetornoMovimento;
        aMsgRet = VMovEst.mensagemRetorno;
        aErrExe = VMovEst.erroExecucao;
        nWebErr = VMovEst.tipoRetorno;

        @ A API interna pode retornar tipo 1 mesmo quando o movimento foi confirmado. @
        Se (((nWebErr = 0) ou (nWebErr = 1)) e (aErrExe = "") e (aRetorno = "OK"))
          {
            nMovimentoOk = 1;
          }
      }

    @ A transferencia so e concluida com retorno interno OK, sem erro de execucao. @
    Se (nMovimentoOk = 0)
      {
        Se (aRetorno = "")
          {
            aRetorno = aMsgRet;
          }

        Se ((aRetorno = "") e (aErrExe <> ""))
          {
            aRetorno = aErrExe;
          }

        aRetorno = "ERRO: " + aRetorno;
      }

    Se (nMovimentoOk = 1)
      {
        IniciarTransacao();

        ExecSQLEx(
        "UPDATE E210DLS \
            SET USU_SITLOT = :aAcaoBotao \
          WHERE CODEMP = :nCodEmp \
            AND CODLOT = :aCodLot \
            AND (CODDEP = :aCodDep OR CODDEP = :aDepTrf)",
        VErro, aMsgStr);

        Se (VErro = 1)
          {
            DesfazerTransacao();
            aRetorno = "ERRO: " + aMsgStr;
          }
        Senao
          {
            FinalizarTransacao();
          }
      }

    PosicaoAlfa("ERRO", aRetorno, nPos);
    IntParaAlfa(nWebErr, aTipoRetorno);
    SubstAlfa("\"", "'", aRetorno);
    SubstAlfa("\"", "'", aRetornoMovimento);
    SubstAlfa("\"", "'", aMsgRet);
    SubstAlfa("\"", "'", aErrExe);

    Se (nPos > 0)
      {
        vaRet = "{|status|:|ERRO|,|message|:|" + aRetorno + "|,|result|:{|retornoMovimento|:{|retorno|:|" + aRetornoMovimento + "|},|tipoRetorno|:|" + aTipoRetorno + "|,|mensagemRetorno|:|" + aMsgRet + "|,|erroExecucao|:|" + aErrExe + "|}}";
      }
    Senao
      {
        vaRet = "{|status|:|OK|,|message|:|" + aRetorno + "|,|result|:{|retornoMovimento|:{|retorno|:|" + aRetornoMovimento + "|},|tipoRetorno|:|" + aTipoRetorno + "|,|mensagemRetorno|:|" + aMsgRet + "|,|erroExecucao|:|" + aErrExe + "|}}";
      }
  }

@ ========================================================================== @
@  RETORNO                                                                   @
@ ========================================================================== @

Se (nTipoRetorno = 0)
  {
    Se (nEntrouAcao = 0)
      {
        nEntrouAcao = 1;
        vaMsg = "Acao inexistente!";
        SubstAlfa("\"", "'", vaMsg);
        vaRet = "{|status|:|ERRO|,|message|:|" + vaMsg + "|}";
      }

    vaRetorno = vaRet;
    SubstAlfa("|", "\"", vaRetorno);

    Definir alfa ENTER;
    Definir alfa XENTER;
    Definir alfa XXENTER;
    CaracterParaAlfa(10, ENTER);
    CaracterParaAlfa(13, XENTER);
    CaracterParaAlfa(9, XXENTER);
    SubstAlfa(Enter, " ", vaRetorno);
    SubstAlfa(XEnter, " ", vaRetorno);
    SubstAlfa(XXEnter, " ", vaRetorno);

    MovimentarEstoque.waRetorno = vaRetorno;
  }
