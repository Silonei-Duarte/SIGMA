Definir Alfa aCodOri;
Definir Alfa aNumOrp;
Definir Alfa aCodEtg;
Definir Alfa aCodLot;
Definir Alfa aCodDep;
Definir Alfa aQtdRe1;
Definir Alfa aEmpresa;
Definir Alfa aDados;
Definir Alfa wacao;
Definir Alfa vaRetorno;
Definir Alfa vaRet;
Definir Alfa aMsgStr;
Definir Alfa aExcluirLote;
Definir Alfa aCodCmp;
Definir Alfa aDerCmp;
Definir Alfa aCodPro;
Definir Alfa aCodDer;
Definir Alfa aTipQtd;
Definir Alfa aIdeUni;
Definir Alfa aLogInc;
Definir Alfa aCodTns;
Definir Alfa CCurSeq;
Definir Alfa CCurCmp;
Definir Alfa TClaSql;
Definir Alfa aMsgRet;
Definir Alfa aErrExe;
Definir Alfa aSeqEoq;

Definir Numero nCodEmp;
Definir Numero nNumOrp;
Definir Numero nCodEtg;
Definir Numero nQtdRe1;
Definir Numero nQtdTotal;
Definir Numero nQtdReduzir;
Definir Numero nQtdAtual;
Definir Numero nQtdNova;
Definir Numero nQtdReduzidaLinha;
Definir Numero nQtdEst;
Definir Numero nPrvCmo;
Definir Numero nPrvOop;
Definir Numero nQtdUti;
Definir Numero nSeqEoq;
Definir Numero nCodRet;
Definir Numero nErroGeral;
Definir Numero nEntrouAcao;
Definir Numero nTemSeq;
Definir Numero VErro;
Definir Numero nUsuPrc;
Definir Numero nHorPrc;
Definir Data dDatFim;
Definir Data dDatPrc;

nCodEmp = CodEmp;
vaRetorno = "";
vaRet = "";
wacao = "";
nErroGeral = 0;
nEntrouAcao = 0;

@ O SIGMA envia uma unica quantidade final; a regra localiza todas as sequencias do lote. @
DiminuirApontamento.tabelaEntradas.linhaatual = 0;
aDados = DiminuirApontamento.tabelaEntradas.valor;
LimpaEspacos(aDados);

ValorElementoJson(aDados, "", "wacao", wacao);
ValorElementoJson(aDados, "", "empresa", aEmpresa);
ValorElementoJson(aDados, "", "CodOri", aCodOri);
ValorElementoJson(aDados, "", "NumOrp", aNumOrp);
ValorElementoJson(aDados, "", "CodEtg", aCodEtg);
ValorElementoJson(aDados, "", "CodLot", aCodLot);
ValorElementoJson(aDados, "", "CodDep", aCodDep);
ValorElementoJson(aDados, "", "QtdRe1", aQtdRe1);
ValorElementoJson(aDados, "", "ExcluirLote", aExcluirLote);

AlfaParaInt(aEmpresa, nCodEmp);
AlfaParaInt(aNumOrp, nNumOrp);
AlfaParaInt(aCodEtg, nCodEtg);
SubstAlfa(".", ",", aQtdRe1);
AlfaParaDecimal(aQtdRe1, nQtdRe1);
TrocaEmpresaFilial(nCodEmp, 1);

Se (wacao = "DIMINUIR-OP")
  {
    nEntrouAcao = 1;

    Se ((nCodEmp <= 0) ou (nNumOrp <= 0) ou (nCodEtg <= 0) ou (aCodOri = "") ou (aCodLot = "") ou (nQtdRe1 < 0) ou ((aExcluirLote = "S") e (aCodDep = "")))
      {
        nErroGeral = 1;
        aMsgStr = "Dados invalidos para diminuir o apontamento.";
      }
    Senao
      {
        @ Leitura inicial tambem torna reenvio da mesma quantidade um OK sem nova pendencia. @
        nTemSeq = 0;
        nQtdTotal = 0;
        TClaSql = "SELECT SEQEOQ WWSeqEoq, QTDRE1 WWQtdRe1 \
                     FROM E900EOQ \
                    WHERE CODEMP = :nCodEmp \
                      AND CODORI = :aCodOri \
                      AND NUMORP = :nNumOrp \
                      AND CODETG = :nCodEtg \
                      AND CODLOT = :aCodLot \
                    ORDER BY SEQEOQ DESC";
        SQL_Criar(CCurSeq);
        SQL_UsarSQLSenior2(CCurSeq, 0);
        SQL_UsarAbrangencia(CCurSeq, 0);
        SQL_DefinirComando(CCurSeq, TClaSql);
        SQL_DefinirInteiro(CCurSeq, "nCodEmp", nCodEmp);
        SQL_DefinirAlfa(CCurSeq, "aCodOri", aCodOri);
        SQL_DefinirInteiro(CCurSeq, "nNumOrp", nNumOrp);
        SQL_DefinirInteiro(CCurSeq, "nCodEtg", nCodEtg);
        SQL_DefinirAlfa(CCurSeq, "aCodLot", aCodLot);
        SQL_AbrirCursor(CCurSeq);
        Enquanto (SQL_EOF(CCurSeq) = 0)
          {
            SQL_RetornarFlutuante(CCurSeq, "WWQtdRe1", nQtdAtual);
            nQtdTotal = nQtdTotal + nQtdAtual;
            nTemSeq = 1;
            SQL_Proximo(CCurSeq);
          }
        SQL_FecharCursor(CCurSeq);
        SQL_Destruir(CCurSeq);

        Se (nTemSeq = 0)
          {
            nErroGeral = 1;
            aMsgStr = "Nenhuma sequencia foi encontrada para o lote informado.";
          }
        Senao
          {
            nQtdReduzir = nQtdTotal - nQtdRe1;
            Se (nQtdReduzir < 0)
              {
                nErroGeral = 1;
                aMsgStr = "A quantidade final informada e maior que a quantidade apontada do lote.";
              }
          }
      }

    Se (nErroGeral = 0)
      {
        @ Toda escrita fica na mesma transacao: Acertar, pendencias e exclusao do lote. @
        dDatFim = DatSis;
        dDatPrc = DatSis;
        nHorPrc = HorSis;
        nUsuPrc = CodUsu;
        aCodTns = "";
        aLogInc = "Gerado por DIMINUIR-OP para o lote " + aCodLot;
        IniciarTransacao();

        @ O lote pode ter varias sequencias; reduz primeiro a mais nova. @
        TClaSql = "SELECT SEQEOQ WWSeqEoq, QTDRE1 WWQtdRe1 \
                     FROM E900EOQ \
                    WHERE CODEMP = :nCodEmp \
                      AND CODORI = :aCodOri \
                      AND NUMORP = :nNumOrp \
                      AND CODETG = :nCodEtg \
                      AND CODLOT = :aCodLot \
                    ORDER BY SEQEOQ DESC";
        SQL_Criar(CCurSeq);
        SQL_UsarSQLSenior2(CCurSeq, 0);
        SQL_UsarAbrangencia(CCurSeq, 0);
        SQL_DefinirComando(CCurSeq, TClaSql);
        SQL_DefinirInteiro(CCurSeq, "nCodEmp", nCodEmp);
        SQL_DefinirAlfa(CCurSeq, "aCodOri", aCodOri);
        SQL_DefinirInteiro(CCurSeq, "nNumOrp", nNumOrp);
        SQL_DefinirInteiro(CCurSeq, "nCodEtg", nCodEtg);
        SQL_DefinirAlfa(CCurSeq, "aCodLot", aCodLot);
        SQL_AbrirCursor(CCurSeq);

        Enquanto ((SQL_EOF(CCurSeq) = 0) e (nErroGeral = 0))
          {
            SQL_RetornarInteiro(CCurSeq, "WWSeqEoq", nSeqEoq);
            SQL_RetornarFlutuante(CCurSeq, "WWQtdRe1", nQtdAtual);
            nQtdReduzidaLinha = 0;

            Se ((nQtdReduzir > 0) e (nQtdAtual > 0))
              {
                nQtdReduzidaLinha = nQtdReduzir;
                Se (nQtdReduzidaLinha > nQtdAtual)
                  nQtdReduzidaLinha = nQtdAtual;
                nQtdNova = nQtdAtual - nQtdReduzidaLinha;

                Definir interno.com.senior.g5.co.mpr.cha.movimentoop.Acertar WSAcertar;
                WSAcertar.codEmp = nCodEmp;
                WSAcertar.codOri = aCodOri;
                WSAcertar.numOrp = nNumOrp;
                WSAcertar.codEtg = nCodEtg;
                WSAcertar.seqEoq = nSeqEoq;
                WSAcertar.qtdRe1 = nQtdNova;
                WSAcertar.ModoExecucao = 1;
                WSAcertar.Executar();

                nCodRet = WSAcertar.codigoResultado;
                aMsgRet = WSAcertar.mensagemErro;
                aErrExe = WSAcertar.erroExecucao;

                Se ((nCodRet <> 0) ou (aErrExe <> ""))
                  {
                    nErroGeral = 1;
                    IntParaAlfa(nSeqEoq, aSeqEoq);
                    aMsgStr = "Erro no Acertar da sequencia " + aSeqEoq + ": " + aMsgRet + " " + aErrExe;
                  }
                Senao
                  {
                    @ Repete o calculo legado: proporcional; fixa so quando a linha inteira foi zerada. @
                    TClaSql = "SELECT a.CODCMP WWCodCmp, \
                                      a.CODDER WWDerCmp, \
                                      a.QTDPRV WWPrvCmo, \
                                      c.QTDPRV WWPrvOop, \
                                      o.CODPRO WWCodPro, \
                                      o.CODDER WWCodDer, \
                                      m.TIPQTD WWTipQtd, \
                                      ctm.QTDUTI WWQtdUti \
                                 FROM E900CMO a \
                                 JOIN E900OOP c \
                                   ON a.CODEMP = c.CODEMP \
                                  AND a.CODORI = c.CODORI \
                                  AND a.NUMORP = c.NUMORP \
                                 JOIN E900QDO o \
                                   ON a.CODEMP = o.CODEMP \
                                  AND a.CODORI = o.CODORI \
                                  AND a.NUMORP = o.NUMORP \
                                 LEFT JOIN E700CMM m \
                                   ON o.CODEMP = m.CODEMP \
                                  AND a.CODETG = m.CODETG \
                                  AND o.CODMOD = m.CODMOD \
                                  AND a.CODCMP = m.CODCMP \
                                 LEFT JOIN E700CTM ctm \
                                   ON o.CODEMP = ctm.CODEMP \
                                  AND a.CODETG = ctm.CODETG \
                                  AND o.CODMOD = ctm.CODMOD \
                                  AND a.CODCMP = ctm.CODCMP \
                                  AND m.SEQMOD = ctm.SEQMOD \
                                  AND o.CODDER = ctm.CODDER \
                                WHERE a.CODEMP = :nCodEmp \
                                  AND a.CODORI = :aCodOri \
                                  AND a.NUMORP = :nNumOrp \
                                  AND a.BXAORP = 'S' \
                                  AND NOT EXISTS (SELECT 1 \
                                                    FROM E075PRO p \
                                                   WHERE p.CODEMP = a.CODEMP \
                                                     AND p.CODPRO = a.CODCMP \
                                                     AND p.USU_CONREL = 'S')";
                    SQL_Criar(CCurCmp);
                    SQL_UsarSQLSenior2(CCurCmp, 0);
                    SQL_UsarAbrangencia(CCurCmp, 0);
                    SQL_DefinirComando(CCurCmp, TClaSql);
                    SQL_DefinirInteiro(CCurCmp, "nCodEmp", nCodEmp);
                    SQL_DefinirAlfa(CCurCmp, "aCodOri", aCodOri);
                    SQL_DefinirInteiro(CCurCmp, "nNumOrp", nNumOrp);
                    SQL_AbrirCursor(CCurCmp);

                    Enquanto ((SQL_EOF(CCurCmp) = 0) e (nErroGeral = 0))
                      {
                        SQL_RetornarAlfa(CCurCmp, "WWCodCmp", aCodCmp);
                        SQL_RetornarAlfa(CCurCmp, "WWDerCmp", aDerCmp);
                        SQL_RetornarAlfa(CCurCmp, "WWCodPro", aCodPro);
                        SQL_RetornarAlfa(CCurCmp, "WWCodDer", aCodDer);
                        SQL_RetornarAlfa(CCurCmp, "WWTipQtd", aTipQtd);
                        SQL_RetornarFlutuante(CCurCmp, "WWPrvCmo", nPrvCmo);
                        SQL_RetornarFlutuante(CCurCmp, "WWPrvOop", nPrvOop);
                        SQL_RetornarFlutuante(CCurCmp, "WWQtdUti", nQtdUti);
                        nQtdEst = 0;

                        Se (aTipQtd = "F")
                          {
                            Se (nQtdNova = 0)
                              nQtdEst = nQtdUti;
                          }
                        Senao
                          {
                            Se (nPrvOop <> 0)
                              {
                                nQtdEst = (nQtdReduzidaLinha * nPrvCmo) / nPrvOop;
                                Arredonda(nQtdEst, 4);
                              }
                          }

                        Se (nQtdEst > 0)
                          {
                            ObterGuid(aIdeUni);
                            VErro = 0;
                            ExecSqlEx(
                            "INSERT INTO USU_TESTCMP (USU_IDEUNI, USU_CODEMP, USU_CODORI, USU_NUMORP, USU_CODETG, \
                                                       USU_CODCMP, USU_QTDEST, USU_CODPRO, USU_CODDER, USU_DERCMP, \
                                                       USU_DATFIM, USU_CODTNS, USU_LOGINC, USU_USUPRC, USU_DATPRC, \
                                                       USU_HORPRC, USU_SITPEN) \
                             VALUES (:aIdeUni, :nCodEmp, :aCodOri, :nNumOrp, :nCodEtg, \
                                     :aCodCmp, :nQtdEst, :aCodPro, :aCodDer, :aDerCmp, \
                                     :dDatFim, :aCodTns, :aLogInc, :nUsuPrc, :dDatPrc, \
                                     :nHorPrc, 1)",
                            VErro, aMsgStr);

                            Se (VErro = 1)
                              {
                                nErroGeral = 1;
                                aMsgStr = "Erro ao gravar pendencia de estorno: " + aMsgStr;
                              }
                          }

                        SQL_Proximo(CCurCmp);
                      }
                    SQL_FecharCursor(CCurCmp);
                    SQL_Destruir(CCurCmp);
                    nQtdReduzir = nQtdReduzir - nQtdReduzidaLinha;
                  }
              }

            SQL_Proximo(CCurSeq);
          }
        SQL_FecharCursor(CCurSeq);
        SQL_Destruir(CCurSeq);

        Se ((nErroGeral = 0) e (nQtdReduzir > 0))
          {
            nErroGeral = 1;
            aMsgStr = "Nao foi possivel aplicar toda a reducao solicitada.";
          }

        @ Mesmo em reenvio idempotente, a exclusao solicitada permanece na transacao. @
        Se ((nErroGeral = 0) e (aExcluirLote = "S"))
          {
            VErro = 0;
            ExecSqlEx(
            "UPDATE E210DLS \
                SET USU_SITLOT = 'E' \
              WHERE CODEMP = :nCodEmp \
                AND CODLOT = :aCodLot \
                AND CODDEP = :aCodDep",
            VErro, aMsgStr);

            Se (VErro = 1)
              {
                nErroGeral = 1;
                aMsgStr = "Erro ao marcar lote como excluido: " + aMsgStr;
              }
          }

        Se (nErroGeral = 1)
          DesfazerTransacao();
        Senao
          FinalizarTransacao();
      }

    Se (nErroGeral = 1)
      vaRet = "{|status|:|ERRO|,|message|:|Erro ao diminuir apontamento: " + aMsgStr + "|}";
    Senao
      vaRet = "{|status|:|OK|,|message|:|Apontamento reduzido.|}";
  }

Se (nEntrouAcao = 0)
  vaRet = "{|status|:|ERRO|,|message|:|Acao inexistente!|}";

vaRetorno = vaRet;
SubstAlfa("|", "\"", vaRetorno);
Definir Alfa ENTER;
Definir Alfa XENTER;
Definir Alfa XXENTER;
CaracterParaAlfa(10, ENTER);
CaracterParaAlfa(13, XENTER);
CaracterParaAlfa(9, XXENTER);
SubstAlfa(ENTER, " ", vaRetorno);
SubstAlfa(XENTER, " ", vaRetorno);
SubstAlfa(XXENTER, " ", vaRetorno);
DiminuirApontamento.waRetorno = vaRetorno;
