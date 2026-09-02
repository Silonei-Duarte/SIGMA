Definir alfa wacao;
Definir alfa vaDados;
Definir alfa vaRet;
Definir alfa vaRetorno;
Definir alfa vaMsg;
Definir alfa aRetorno;

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
Definir alfa aAcaoBotao;
Definir alfa aNumDoc;
Definir alfa aOriOrp;
Definir alfa aProTrf;
Definir alfa aDerTrf;
Definir alfa aLotTrf;
Definir alfa aCodDft;
Definir alfa aUsuAtrCcu;
Definir alfa aUsuCcuFix;
Definir alfa aCodCcu;
Definir alfa aSqlCcu;
Definir alfa aOriCcu;
Definir alfa aQtdMovAux;
Definir alfa aVlrMov;
Definir alfa CCurDft;
Definir alfa CCurEoq;
Definir alfa CCurMvp;
Definir alfa CCurLig;
Definir alfa CCurDer;

Definir numero nCodEmp;
Definir numero nCodFil;
Definir numero nNumDoc;
Definir numero nNumDocCcu;
Definir numero nCodLig;
Definir numero nEntrouAcao;
Definir numero nTipoRetorno;
Definir numero nPos;
Definir numero nWebErr;
Definir numero nMovNec;
Definir numero nMovimentoOk;
Definir numero nErroCcu;
Definir numero nQtdMov;
Definir numero nPreMed;
Definir numero nVlrMov;
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
aCodCcu = "";
aOriCcu = "";
nNumDocCcu = 0;
nCodLig = 0;
nTipoRetorno = 0;
nEntrouAcao = 0;
nMovNec = 1;
nMovimentoOk = 0;
nErroCcu = 0;
nQtdMov = 0;
nPreMed = 0;
nVlrMov = 0;
aVlrMov = "";

@ Captura unico JSON enviado em wdados @
TransferenciaProduto.tabelaEntradas.linhaatual = 0;
vaDados = TransferenciaProduto.tabelaEntradas.valor;
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
ValorElementoJson(vaDados, "", "acaoBotao", aAcaoBotao);
ValorElementoJson(vaDados, "", "numDoc", aNumDoc);
ValorElementoJson(vaDados, "", "oriOrp", aOriOrp);
ValorElementoJson(vaDados, "", "proTrf", aProTrf);
ValorElementoJson(vaDados, "", "derTrf", aDerTrf);
ValorElementoJson(vaDados, "", "lotTrf", aLotTrf);
@ Definicao usada para encontrar a regra de atribuicao do centro de custo. @
ValorElementoJson(vaDados, "", "codDft", aCodDft);

AlfaParaInt(aCodEmp,nCodEmp);
AlfaParaInt(aCodFil,nCodFil);
AlfaParaInt(aNumDoc,nNumDoc);
aQtdMovAux = aQtdMov;
SubstAlfa(".", ",", aQtdMovAux);
AlfaParaDecimal(aQtdMovAux,nQtdMov);
aQtdMov = aQtdMovAux;
dDatMov = DatSis;

TrocaEmpresaFilial(nCodEmp,nCodFil);

@ Busca configuracao da definicao fiscal para descobrir como atribuir o centro de custo. @
SQL_Criar(CCurDft);
SQL_UsarSQLSenior2(CCurDft, 0);
SQL_UsarAbrangencia(CCurDft, 0);
SQL_DefinirComando(CCurDft, "SELECT USU_ATRCCU, USU_CCUFIX FROM E011DEF WHERE CODEMP = :nCodEmp AND CODDFT = :aCodDft");
SQL_DefinirInteiro(CCurDft, "nCodEmp", nCodEmp);
SQL_DefinirAlfa(CCurDft, "aCodDft", aCodDft);
SQL_AbrirCursor(CCurDft);
Se (SQL_EOF(CCurDft) = 0)
  {
    SQL_RetornarAlfa(CCurDft, "USU_ATRCCU", aUsuAtrCcu);
    SQL_RetornarAlfa(CCurDft, "USU_CCUFIX", aUsuCcuFix);
    LimpaEspacos(aUsuAtrCcu);
    LimpaEspacos(aUsuCcuFix);
  }
SQL_Destruir(CCurDft);

@ Quando a regra for por OF, busca o centro de custo pelo recurso da primeira operacao do lote. @
Se (aUsuAtrCcu = "OF")
  {
    aSqlCcu = "SELECT CRE.CODCCU WWCODCCU \
                 FROM E900EOQ EOQ, E725CRE CRE \
                WHERE CRE.CODEMP = EOQ.CODEMP \
                  AND CRE.CODCRE = EOQ.CODCRE \
                  AND EOQ.CODEMP = :nCodEmp \
                  AND EOQ.CODLOT = :aCodLot \
                  AND EOQ.SEQEOQ = (SELECT MIN(EOQ2.SEQEOQ) \
                                      FROM E900EOQ EOQ2 \
                                     WHERE EOQ2.CODEMP = EOQ.CODEMP \
                                       AND EOQ2.CODLOT = EOQ.CODLOT \
                                       AND EOQ2.CODCRE IS NOT NULL)";

    SQL_Criar(CCurEoq);
    SQL_DefinirComando(CCurEoq, aSqlCcu);
    SQL_DefinirInteiro(CCurEoq, "nCodEmp", nCodEmp);
    SQL_DefinirAlfa(CCurEoq, "aCodLot", aCodLot);
    SQL_AbrirCursor(CCurEoq);
    Se (SQL_EOF(CCurEoq) = 0)
      {
        SQL_RetornarAlfa(CCurEoq, "WWCODCCU", aCodCcu);
        LimpaEspacos(aCodCcu);
      }
    SQL_Destruir(CCurEoq);

    Se (aCodCcu = "")
      {
        nErroCcu = 1;
      }
  }
Senao
  {
    @ Quando a regra for OC, busca a OP da ultima movimentacao de consumo do lote. @
    Se (aUsuAtrCcu = "OC")
      {
        aSqlCcu = "SELECT ORIORP WWORIORP, NUMDOC WWNUMDOC, DATMOV WWDATMOV, SEQMOV WWSEQMOV \
                     FROM E210MVP \
                    WHERE CODEMP = :nCodEmp \
                      AND CODLOT = :aCodLot \
                      AND CODTNS = '90251' \
                    ORDER BY DATMOV DESC, SEQMOV DESC";

        SQL_Criar(CCurMvp);
        SQL_DefinirComando(CCurMvp, aSqlCcu);
        SQL_DefinirInteiro(CCurMvp, "nCodEmp", nCodEmp);
        SQL_DefinirAlfa(CCurMvp, "aCodLot", aCodLot);
        SQL_AbrirCursor(CCurMvp);
        Se (SQL_EOF(CCurMvp) = 0)
          {
            SQL_RetornarAlfa(CCurMvp, "WWORIORP", aOriCcu);
            SQL_RetornarInteiro(CCurMvp, "WWNUMDOC", nNumDocCcu);
            LimpaEspacos(aOriCcu);
          }
        SQL_Destruir(CCurMvp);

        @ Com a OP encontrada pelo consumo, busca o centro de custo pelo recurso da primeira operacao. @
        Se ((aOriCcu <> "") e (nNumDocCcu > 0))
          {
            aSqlCcu = "SELECT CRE.CODCCU WWCODCCU \
                         FROM E900EOQ EOQ, E725CRE CRE \
                        WHERE CRE.CODEMP = EOQ.CODEMP \
                          AND CRE.CODCRE = EOQ.CODCRE \
                          AND EOQ.CODEMP = :nCodEmp \
                          AND EOQ.CODORI = :aOriCcu \
                          AND EOQ.NUMORP = :nNumDocCcu \
                          AND EOQ.SEQEOQ = (SELECT MIN(EOQ2.SEQEOQ) \
                                              FROM E900EOQ EOQ2 \
                                             WHERE EOQ2.CODEMP = EOQ.CODEMP \
                                               AND EOQ2.CODORI = EOQ.CODORI \
                                               AND EOQ2.NUMORP = EOQ.NUMORP \
                                               AND EOQ2.CODCRE IS NOT NULL)";

            SQL_Criar(CCurEoq);
            SQL_DefinirComando(CCurEoq, aSqlCcu);
            SQL_DefinirInteiro(CCurEoq, "nCodEmp", nCodEmp);
            SQL_DefinirAlfa(CCurEoq, "aOriCcu", aOriCcu);
            SQL_DefinirInteiro(CCurEoq, "nNumDocCcu", nNumDocCcu);
            SQL_AbrirCursor(CCurEoq);
            Se (SQL_EOF(CCurEoq) = 0)
              {
                SQL_RetornarAlfa(CCurEoq, "WWCODCCU", aCodCcu);
                LimpaEspacos(aCodCcu);
              }
            SQL_Destruir(CCurEoq);
          }

        Se (aCodCcu = "")
          {
            nErroCcu = 1;
          }
      }

    @ Quando a regra for centro de custo fixo, usa o valor cadastrado na definicao fiscal. @
    Se (aUsuAtrCcu = "CF")
      {
        aCodCcu = aUsuCcuFix;
        Se (aCodCcu = "")
          {
            nErroCcu = 1;
          }
      }
  }

@ ========================================================================== @
@  TRANSFERENCIA PRODUTO                                                     @
@ ========================================================================== @

Se (wacao = "TRANSFERENCIA-PRODUTO")
  {
    nEntrouAcao = 1;

    Definir Alfa aMsgRet;
    Definir Alfa aErrExe;

    aMsgRet = "";
    aErrExe = "";

    @ Sem centro de custo pela regra configurada nao deve executar a transferencia. @
    Se (nErroCcu = 1)
      {
        nMovNec = 0;
        nWebErr = 2;
        aErrExe = "Centro de custo nao localizado pela regra configurada no motivo.";
        aMsgRet = "";
      }

    @ Se origem e destino ja forem iguais, nao chama o webservice; apenas atualiza a situacao. @
    Se ((nErroCcu = 0) e (aCodDep = aDepTrf) e (aCodLot = aLotTrf) e (((aCodPro = aProTrf) e (aCodDer = aDerTrf)) ou ((aProTrf = "") e (aDerTrf = ""))))
      {
        nMovNec = 0;
        nWebErr = 0;
        aRetorno = "Nenhum movimento necessario";
        nMovimentoOk = 1;
      }

    Se (nMovNec = 1)
      {
        Definir interno.com.senior.g5.co.mcm.est.estoques.TransferenciaProdutos VTraPro;

        @ Valor do movimento de entrada: preco medio da derivacao de destino x quantidade transferida. @
        @ A saida calcula automaticamente, mas a entrada precisa receber transferenciasEntreProdutosEntrada.vlrMov. @
        nPreMed = 0;
        nVlrMov = 0;
        aVlrMov = "";
        SQL_Criar(CCurDer);
        SQL_UsarSQLSenior2(CCurDer, 0);
        SQL_UsarAbrangencia(CCurDer, 0);
        SQL_DefinirComando(CCurDer, "SELECT PREMED FROM E075DER WHERE CODEMP = :nCodEmp AND CODPRO = :aProTrf AND CODDER = :aDerTrf");
        SQL_DefinirInteiro(CCurDer, "nCodEmp", nCodEmp);
        SQL_DefinirAlfa(CCurDer, "aProTrf", aProTrf);
        SQL_DefinirAlfa(CCurDer, "aDerTrf", aDerTrf);
        SQL_AbrirCursor(CCurDer);
        Se (SQL_EOF(CCurDer) = 0)
          {
            SQL_RetornarFlutuante(CCurDer, "PREMED", nPreMed);
          }
        SQL_Destruir(CCurDer);
        nVlrMov = nPreMed * nQtdMov;
        IntParaStr(nVlrMov,aVlrMov);

        VTraPro.transferenciaEntreProdutosSaida.codEmp = aCodEmp;
        VTraPro.transferenciaEntreProdutosSaida.codFil = aCodFil;
        VTraPro.transferenciaEntreProdutosSaida.codPro = aCodPro;
        VTraPro.transferenciaEntreProdutosSaida.codDer = aCodDer;
        VTraPro.transferenciaEntreProdutosSaida.codTns = aCodTns;
        VTraPro.transferenciaEntreProdutosSaida.codDep = aCodDep;
        VTraPro.transferenciaEntreProdutosSaida.datMov = dDatMov;
        VTraPro.transferenciaEntreProdutosSaida.qtdMov = aQtdMov;
        VTraPro.transferenciaEntreProdutosSaida.codLot.codLot = aCodLot;
        VTraPro.transferenciaEntreProdutosSaida.codLot.qtdEst = aQtdMov;
        VTraPro.transferenciaEntreProdutosSaida.numDoc = nNumDoc;
        @ Centro de custo aplicado no movimento de saida. @
        VTraPro.transferenciaEntreProdutosSaida.codCcu = aCodCcu;

        VTraPro.transferenciasEntreProdutosEntrada.codPro = aProTrf;
        VTraPro.transferenciasEntreProdutosEntrada.codDer = aDerTrf;
        VTraPro.transferenciasEntreProdutosEntrada.codDep = aDepTrf;
        VTraPro.transferenciasEntreProdutosEntrada.qtdMov = aQtdMov;
        VTraPro.transferenciasEntreProdutosEntrada.vlrMov = aVlrMov;
        VTraPro.transferenciasEntreProdutosEntrada.codLot.codLot = aLotTrf;
        VTraPro.transferenciasEntreProdutosEntrada.codLot.qtdEst = aQtdMov;
        VTraPro.transferenciasEntreProdutosEntrada.numDoc = nNumDoc;
        @ Centro de custo aplicado no movimento de entrada. @
        VTraPro.transferenciasEntreProdutosEntrada.codCcu = aCodCcu;

        VTraPro.ModoExecucao = 1;   
        VTraPro.Executar();
        aRetorno = VTraPro.mensagemRetorno;
        aMsgRet = VTraPro.mensagemRetorno;
        aErrExe = VTraPro.erroExecucao;
        nWebErr = VTraPro.tipoRetorno;

        @ A API interna pode retornar tipo 1 mesmo com transferencia concluida. @
        Se (((nWebErr = 0) ou (nWebErr = 1)) e (aErrExe = ""))
          {
            nMovimentoOk = 1;
          }
      }

    Se (nMovimentoOk = 0)
      {
        aRetorno = "ERRO: " + aErrExe + " " + aMsgRet;
      }

    Se (nMovimentoOk = 1)
      {
        Se (nMovNec = 1)
          {
            @ Guarda a ligacao criada pela transferencia em campo personalizado e limpa o campo nativo. @
            SQL_Criar(CCurLig);
            SQL_DefinirComando(CCurLig, "SELECT CODLIG WWCODLIG, DATMOV WWDATMOV, SEQMOV WWSEQMOV \
                                          FROM E210MVP \
                                         WHERE CODEMP = :nCodEmp \
                                           AND CODLOT = :aLotTrf \
                                         ORDER BY DATMOV DESC, SEQMOV DESC");
            SQL_DefinirInteiro(CCurLig, "nCodEmp", nCodEmp);
            SQL_DefinirAlfa(CCurLig, "aLotTrf", aLotTrf);
            SQL_AbrirCursor(CCurLig);
            Se (SQL_EOF(CCurLig) = 0)
              {
                SQL_RetornarInteiro(CCurLig, "WWCODLIG", nCodLig);
              }
            SQL_Destruir(CCurLig);
          }

        IniciarTransacao();
        VErro = 0;

        Se ((nMovNec = 1) e (nCodLig > 0))
          {
            ExecSQLEx(
            "UPDATE E210MVP \
                SET USU_CODLIG = CODLIG, \
                    CODLIG = 0 \
              WHERE CODEMP = :nCodEmp \
                AND CODLIG = :nCodLig",
            VErro, aMsgStr);
          }
        
        Se (VErro <> 1)
          {
            ExecSQLEx(
            "UPDATE E210DLS \
                SET USU_SITLOT = :aAcaoBotao \
              WHERE CODEMP = :nCodEmp \
                AND (CODLOT = :aCodLot OR CODLOT = :aLotTrf)",
            VErro, aMsgStr);
          }
        
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

    Se (nPos > 0)
      {
        vaRet = "{|status|:|ERRO|,|message|:|" + aRetorno + "|}";
      }
    Senao
      {
        vaRet = "{|status|:|OK|,|message|:|" + aRetorno + "|}";
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

    TransferenciaProduto.waRetorno = vaRetorno;
  }
