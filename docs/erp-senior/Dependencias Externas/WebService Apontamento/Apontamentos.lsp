Definir alfa aCodOri;
Definir alfa aNumOrp;
Definir alfa aNumCad;
Definir alfa aCodEtg;
Definir alfa aSeqRot;
Definir alfa aQtdRe1;
Definir alfa aTurTrb;
Definir alfa aQtdRfg;
Definir alfa aNumBob;
Definir alfa aNumMaq;
Definir alfa aParametros;
Definir alfa aRetorno;
Definir alfa wacao;

Definir alfa vaRetorno;    
Definir alfa vaRet;
Definir alfa vaMsg;        
Definir alfa vaDados;
Definir alfa aChave;
Definir alfa aValor;
Definir alfa aEmpresa;
Definir Numero nEmpresa;

Definir Alfa xCurLot;
Definir Numero nCodLot;
Definir Alfa aCodLot;

Definir numero nNumOrp;
Definir numero nNumCad;
Definir numero nTurTrb;

Definir numero nQtdMov;
Definir Alfa aCodPro;
Definir Alfa aCodDer;
Definir numero nQtdRe1;
Definir Alfa aLogPrc;
Definir Alfa aIdeUni;
Definir Numero nPrvCmo;
Definir Numero nPrvOop;
Definir Alfa aTipQtd;
Definir Numero nQtdUti;

Definir Alfa CCurCmp;
Definir Alfa TClaSql;
Definir numero VErro;
Definir Numero nErroGeral;
Definir Numero npos;
Definir Alfa aMsgStr;
Definir alfa aHorMov;
Definir Alfa aDatMov;

Definir Data dDatMov;
Definir Lista lstExp;
lstExp.DefinirCampos();
lstExp.AdicionarCampo("CodPro", alfa);
lstExp.AdicionarCampo("CodDer", alfa);
lstExp.AdicionarCampo("QtdMov", numero);
lstExp.EfetivarCampos();


nCodEmp = CodEmp;

@ ========================================================================== @
@  VARIAVEIS RECEBIDAS SOAB                                                     @
@ ========================================================================== @

vaRetorno = "";
wacao = "";
vaMsg = "";
aCodLot = "";
nTipoRetorno = 0;
nErroGeral = 0;
npos = 0;

@ Captura Unico JSON enviado em wdados @
Apontamentos.tabelaEntradas.linhaatual = 0;
vaDados = Apontamentos.tabelaEntradas.valor;
LimpaEspacos(vaDados);

ValorElementoJson(vaDados, "", "wacao", wacao);
ValorElementoJson(vaDados, "", "empresa", aEmpresa);
ValorElementoJson(vaDados, "", "CodOri", aCodOri);
ValorElementoJson(vaDados, "", "NumOrp", aNumOrp);
ValorElementoJson(vaDados, "", "NumCad", aNumCad);
ValorElementoJson(vaDados, "", "CodEtg", aCodEtg);
ValorElementoJson(vaDados, "", "SeqRot", aSeqRot);
ValorElementoJson(vaDados, "", "QtdRe1", aQtdRe1);
ValorElementoJson(vaDados, "", "QtdRfg", aQtdRfg);
ValorElementoJson(vaDados, "", "CodLot", aCodLot);
ValorElementoJson(vaDados, "", "HorMov", aHorMov);
ValorElementoJson(vaDados, "", "DatMov", aDatMov);
ValorElementoJson(vaDados, "", "NumBob", aNumBob);
ValorElementoJson(vaDados, "", "NumMaq", aNumMaq);

@data e hora@
AlfaParaData(aDatMov, dDatMov);

Definir Alfa aHora;
Definir Alfa aMin;
Definir Numero nHora;
Definir Numero nMin;

aHora = aHorMov;
CopiarAlfa(aHora, 1, 2);

aMin = aHorMov;
CopiarAlfa(aMin, 4, 2);

AlfaParaInt(aHora, nHora);
AlfaParaInt(aMin, nMin);

nHorMov = (nHora * 60) + nMin;


@empresa@
nEntrouAcao = 0;
AlfaParaInt(aEmpresa, nCodEmp);
TrocaEmpresaFilial(nCodEmp, 1);

@ Busca o turno do operador, pois TurTrb nao e mais recebido no JSON. @
Definir Alfa xCurOpe;
Definir Alfa xSqlOpe;

AlfaParaInt(aNumCad, nNumCad);
nTurTrb = 9;
aTurTrb = "9";

xSqlOpe = "SELECT TURTRB WWTurTrb \
             FROM E906OPE \
            WHERE CODEMP = :nCodEmp \
              AND NUMCAD = :nNumCad";

SQL_Criar(xCurOpe);
SQL_DefinirComando(xCurOpe, xSqlOpe);
SQL_DefinirInteiro(xCurOpe,"nCodEmp",nCodEmp);
SQL_DefinirInteiro(xCurOpe,"nNumCad",nNumCad);
SQL_AbrirCursor(xCurOpe);

Se (SQL_EOF(xCurOpe) = 0)
  {
    SQL_RetornarInteiro(xCurOpe,"WWTurTrb",nTurTrb);
    IntParaAlfa(nTurTrb,aTurTrb);
  }

SQL_FecharCursor(xCurOpe);
SQL_Destruir(xCurOpe);


@ ========================================================================= @
Se (wacao = "APONTAR-OP")
  {
    @Variavel Alfa Virgula para Decimal e Ponto para ApontarOps @
    nEntrouAcao = 1;
    Definir Alfa adQtdRe1;
    adQtdRe1 = aQtdRe1;
    AlfaParaInt (aNumOrp,nNumOrp);
    SubstAlfa(".", ",", adQtdRe1);
    AlfaParaDecimal (adQtdRe1,nQtdRe1);
    aLogPrc = "Inserido por APONTAR-OP";

    @VALIDAR SE REGISTRO JA FOI APONTADO@
    Definir Alfa CCurDup;
    Definir Alfa aSqlDup;
    Definir Numero nJaApt;
    Definir Numero nCodEtg;
    Definir Numero nSeqRot;
    Definir Numero nCodCre;
    AlfaParaInt(aCodEtg, nCodEtg);
    AlfaParaInt(aSeqRot, nSeqRot);
    AlfaParaInt(aNumMaq, nCodCre);

    nJaApt = 0;

    aSqlDup = "SELECT 1 WWAchou \
                 FROM E900EOQ \
                WHERE CodEmp = :nCodEmp \
                  AND CodOri = :aCodOri \
                  AND NumOrp = :nNumOrp \
                  AND CodEtg = :nCodEtg \
                  AND SeqRot = :nSeqRot \
                  AND QtdRe1 = :nQtdRe1 \
                  AND CodLot = :aCodLot \
                  AND CodCre = :nCodCre \
                  AND HorRea = :nHorMov \
                  AND Usu_NumBob = :aNumBob";

    SQL_Criar(CCurDup);
    SQL_DefinirComando(CCurDup, aSqlDup);
    SQL_DefinirInteiro(CCurDup, "nCodEmp", nCodEmp);
    SQL_DefinirAlfa(CCurDup, "aCodOri", aCodOri);
    SQL_DefinirInteiro(CCurDup, "nNumOrp", nNumOrp);
    SQL_DefinirInteiro(CCurDup, "nCodEtg", nCodEtg);
    SQL_DefinirInteiro(CCurDup, "nSeqRot", nSeqRot);
    SQL_DefinirFlutuante(CCurDup, "nQtdRe1", nQtdRe1);
    SQL_DefinirAlfa(CCurDup, "aCodLot", aCodLot);
    SQL_DefinirInteiro(CCurDup, "nCodCre", nCodCre);
    SQL_DefinirInteiro(CCurDup, "nHorMov", nHorMov);
    SQL_DefinirAlfa(CCurDup, "aNumBob", aNumBob);

    SQL_AbrirCursor(CCurDup);

    Se (SQL_EOF(CCurDup) = 0)
      {
        nJaApt = 1;
        vaRet = "{|status|:|OK|,|message|:|Apontamento ja realizado|}";
      }

    SQL_FecharCursor(CCurDup);
    SQL_Destruir(CCurDup);

    @ Primeiro apontamento da OP: cria backup do BxaOrp original quando ainda nao existe. @
    Se ((nQtdRe1 > 0) e (nJaApt = 0))
      {
        IniciarTransacao();

        ExecSqlEx(
        "UPDATE E900CMO SET USU_BXAORP = BXAORP \
          WHERE CODEMP = :nCodEmp \
            AND CODORI = :aCodOri \
            AND NUMORP = :nNumOrp \
            AND (USU_BXAORP IS NULL OR USU_BXAORP = ' ')",
        VErro, aMsgStr);

        Se (VErro = 1)
          DesfazerTransacao();
        Senao
          FinalizarTransacao();
      }

    @INICIO PROCESSO DE APONTAMENTO@
    Se ((nQtdRe1 > 0) e (nJaApt = 0))
      {
        @ Busca os componentes da OP que estavam configurados para baixa automatica. @
        @ Usa SQL nativo para permitir Join/Left Join e ler o modelo tecnico. @
        @ TipQtd/QtdUti vem do modelo; se nao existir, o calculo cai no proporcional. @
        TClaSql = "Select a.CodCmp WWCodCmp, \
                          a.CodDer WWCodDer, \
                          a.QtdPrv WWPrvCmo, \
                          c.QtdPrv WWPrvOop, \
                          m.TipQtd WWTipQtd, \
                          ctm.QtdUti WWQtdUti \
                   From E900CMO a \
                   Join E900OOP c \
                     On a.CodEmp = c.CodEmp \
                    And a.CodOri = c.CodOri \
                    And a.NumOrp = c.NumOrp \
                   Join E900QDO o \
                     On a.CodEmp = o.CodEmp \
                    And a.CodOri = o.CodOri \
                    And a.NumOrp = o.NumOrp \
                   Left Join E700CMM m \
                     On o.CodEmp = m.CodEmp \
                    And a.CodEtg = m.CodEtg \
                    And o.CodMod = m.CodMod \
                    And a.CodCmp = m.CodCmp \
                   Left Join E700CTM ctm \
                     On o.CodEmp = ctm.CodEmp \
                    And a.CodEtg = ctm.CodEtg \
                    And o.CodMod = ctm.CodMod \
                    And a.CodCmp = ctm.CodCmp \
                    And m.SeqMod = ctm.SeqMod \
                    And o.CodDer = ctm.CodDer \
                  Where a.CodEmp = :nCodEmp \
                    And a.CodOri = :aCodOri \
                    And a.NumOrp = :nNumOrp \
                    And a.USU_BxaOrp = 'S' \
                    And Not Exists (Select 1 \
                                      From E075PRO p \
                                     Where p.CodEmp = a.CodEmp \
                                       And p.CodPro = a.CodCmp \
                                       And p.USU_CONREL = 'S')";

        SQL_Criar(CCurCmp);
        SQL_UsarSQLSenior2(CCurCmp,0);
        SQL_UsarAbrangencia(CCurCmp, 0);
        SQL_DefinirComando(CCurCmp, TClaSql);
        SQL_DefinirInteiro(CCurCmp,"nCodEmp",nCodEmp);
        SQL_DefinirAlfa(CCurCmp,"aCodOri",aCodOri);
        SQL_DefinirInteiro(CCurCmp,"nNumOrp",nNumOrp);
        SQL_AbrirCursor(CCurCmp);
        @ Monta uma lista temporaria antes do ApontarOPs, pois o BxaOrp sera alterado. @
        Enquanto (SQL_EOF(CCurCmp) = 0)
          {
             SQL_RetornarAlfa(CCurCmp,"WWCodCmp",aCodPro);
             SQL_RetornarAlfa(CCurCmp,"WWCodDer",aCodDer);
             SQL_RetornarFlutuante(CCurCmp,"WWPrvCmo",nPrvCmo);
             SQL_RetornarFlutuante(CCurCmp,"WWPrvOop",nPrvOop);
             SQL_RetornarAlfa(CCurCmp,"WWTipQtd",aTipQtd);
             SQL_RetornarFlutuante(CCurCmp,"WWQtdUti",nQtdUti);
             @ Se o modelo define quantidade fixa, usa QtdUti; senao proporcionaliza pela OP. @
             Se (aTipQtd = "F")
               {
                 nQtdMov = nQtdUti;
               }
             Senao
               {
                 Se (nPrvOop <> 0)
                   {
                     nQtdMov = (nQtdRe1 * nPrvCmo) / nPrvOop;
                     Arredonda(nQtdMov,2);
                   }
                 Senao
                   {
                     nQtdMov = 0;
                   }
               }

           @ Guarda apenas os dados necessarios para restaurar BxaOrp e gerar pendencia. @
             lstExp.Adicionar();
             lstExp.CodPro = aCodPro;
             lstExp.CodDer = aCodDer;
             lstExp.QtdMov = nQtdMov;
             lstExp.Gravar();

             SQL_Proximo(CCurCmp);
          }
        SQL_FecharCursor(CCurCmp);

      @ Verifica se ja existe apontamento de inicio para o mesmo operador. @
      Definir Alfa xCurEOQ;
      Definir Alfa xSql;
      Definir Data dDatIni;
      Definir Data dBase;
      Definir Numero nTemRea;

      AlfaParaInt(aCodEtg, nCodEtg);

      MontaData(31,12,1900,dBase);
      nTemRea = 0;

      xSql = "SELECT DatIni \
              FROM E900EOQ \
            WHERE CODEMP = :nCodEmp \
              AND CODORI = :aCodOri \
              AND NUMORP = :nNumOrp \
              AND CODETG = :nCodEtg \
              AND NUMCAD = :nNumCad \
              AND SEQEOQ = (SELECT MAX(SEQEOQ) \
                              FROM E900EOQ \
                              WHERE CODEMP = :nCodEmp \
                                AND CODORI = :aCodOri \
                                AND NUMORP = :nNumOrp \
                                AND CODETG = :nCodEtg \
                                AND NUMCAD = :nNumCad)";

      SQL_Criar(xCurEOQ);
      SQL_DefinirComando(xCurEOQ, xSql);
      SQL_DefinirInteiro(xCurEOQ,"nCodEmp",nCodEmp);
      SQL_DefinirAlfa(xCurEOQ,"aCodOri",aCodOri);
      SQL_DefinirInteiro(xCurEOQ,"nNumOrp",nNumOrp);
      SQL_DefinirInteiro(xCurEOQ,"nCodEtg",nCodEtg);
      SQL_DefinirInteiro(xCurEOQ,"nNumCad",nNumCad);

      SQL_AbrirCursor(xCurEOQ);

      Se (SQL_EOF(xCurEOQ) = 0)
        {
          SQL_RetornarData(xCurEOQ,"DatIni",dDatIni);

          Se (dDatIni > dBase)
              nTemRea = 1;
        }

      SQL_FecharCursor(xCurEOQ);
      SQL_Destruir(xCurEOQ);

      @ Parametros base do ApontarOPs; as quantidades sao montadas separadamente. @
      Definir Alfa aBaseParam;

      aBaseParam = "CodOri=" + aCodOri +
                  ",NumOrp=" + aNumOrp +
                  ",CodEtg=" + aCodEtg +
                  ",SeqRot=" + aSeqRot +
                  ",NumCad=" + aNumCad +
                  ",CodLot=" + aCodLot +
                  ",Datmov=" + aDatMov +
                  ",HorMov=" + aHorMov +
                  ",TurTrb=" + aTurTrb +
                  ",Usu_NumBob=" + aNumBob +
                  ",Usu_NumMaq=" + aNumMaq;

      @ Parametros do apontamento real informado pela tela. @
      aParametros = aBaseParam +
                    ",QtdRe1=" + aQtdRe1 +
                    ",QtdRfg=" + aQtdRfg;

      @ Mantem esta transacao aberta somente ate apontar/restaurar, segurando o lock do BxaOrp. @
      @ As pendencias e demais atualizacoes rodam depois, fora deste lock. @
      nErroGeral = 0;
      npos = 0;
      IniciarTransacao();

      ExecSqlEx(
      "UPDATE E900CMO SET BXAORP = 'N' \
      WHERE CODEMP = :nCodEmp \
        AND CODORI = :aCodOri \
        AND NUMORP = :nNumOrp \
        AND USU_BXAORP = 'S'",
      VErro, aMsgStr);

      Se (VErro = 1)
        {
          nErroGeral = 1;
          aRetorno = "ERRO ao desligar baixa automatica: " + aMsgStr;
        }

      Se (nErroGeral = 0)
        {
          @ Se ja havia inicio, envia apenas o fim; senao cria inicio zerado e depois fim. @
          Se (nTemRea = 1)
            {
              ApontarOPs(aParametros, aRetorno);
            }
          Senao
            {
              Definir Alfa aParamZero;

              aParamZero = aBaseParam +
                            ",QtdRe1=0" +
                            ",QtdRfg=0";

              ApontarOPs(aParamZero, aRetorno);
              ApontarOPs(aParametros, aRetorno);
            }

          PosicaoAlfa("ERRO", aRetorno, npos);
          Se (npos > 0)
            nErroGeral = 1;
        }

      @ Restaura a baixa automatica original da OP inteira antes de encerrar a transacao. @
      ExecSQLEx(
      "Update E900CMO Set BxaOrp = USU_BxaOrp \
        Where CodEmp = :nCodEmp \
          And CodOri = :aCodOri \
          And NumOrp = :nNumOrp \
          And USU_BxaOrp Is Not Null \
          And USU_BxaOrp <> ' '",
      VErro, aMsgStr);

      Se (VErro = 1)
        {
          Se (nErroGeral = 0)
            aRetorno = "ERRO ao restaurar baixa automatica: " + aMsgStr;
          nErroGeral = 1;
        }

      PosicaoAlfa("ERRO", aRetorno, npos);

      Se ((npos > 0) ou (nErroGeral = 1))
        {
          DesfazerTransacao();

          Se (aRetorno = "")
            aRetorno = "ERRO no apontamento";
        }
      Senao
        {
          FinalizarTransacao();
        }

      @ Registra pendencias de baixa somente depois de encerrar a transacao do apontamento. @
      Se ((npos = 0) e (nErroGeral = 0))
        {
          Tem = lstExp.Primeiro();
          Enquanto (Tem = 1)
            {
              aCodPro = lstExp.CodPro;
              aCodDer = lstExp.CodDer;
              nQtdMov = lstExp.QtdMov;

              Se (nQtdMov > 0)
                {
                  ObterGuid(aIdeUni);

                  IniciarTransacao();

                  ExecSqlEx(
                  "Insert Into USU_TBXACMP (USU_CODEMP, USU_CODORI, USU_NUMORP, USU_CODETG, \
                      USU_CODCMP, USU_DERCMP, USU_LOTDES, USU_QTDUTI, USU_LOGINC, \
                      USU_CODCRE, USU_CODLOT, USU_DATMOV, USU_HORMOV, USU_SITPEN, USU_IDEUNI) \
                    Values (:nCodEmp, :aCodOri, :nNumOrp, :nCodEtg, \
                      :aCodPro, :aCodDer, :aCodLot, :nQtdMov, :aLogPrc, \
                      :aNumMaq, '', :dDatMov, :nHorMov, 1, :aIdeUni)",
                  VErro, aMsgStr);

                  Se (VErro = 1)
                    {
                      DesfazerTransacao();
                      aRetorno = "ERRO ao gravar pendencia de baixa: " + aMsgStr;
                      nErroGeral = 1;
                    }
                  Senao
                    FinalizarTransacao();
                }

              Tem = lstExp.Proximo();
            }
        }

      Se ((npos = 0) e (nErroGeral = 0))
        {
          @ Localiza o deposito do lote apontado para marcar o saldo como pendente. @
          Definir Alfa CCurDep;
          Definir Alfa aSqlDep;
          Definir Alfa aCodDep;
          Definir Numero nAchouDep;

          nAchouDep = 0;
          aCodDep = "";

          aSqlDep = "SELECT CODDEP WWCodDep \
                        FROM E900EOQ \
                       WHERE CODEMP = :nCodEmp \
                         AND CODLOT = :aCodLot \
                         AND USU_NUMBOB = :aNumBob \
                         AND CODCRE = :nCodCre \
                         AND NUMCAD = :nNumCad \
                         AND CODORI = :aCodOri \
                         AND NUMORP = :nNumOrp \
                         AND CODETG = :nCodEtg \
                         AND SEQROT = :nSeqRot \
                         AND QTDRE1 = :nQtdRe1 \
                         AND DATREA = :dDatMov";

          SQL_Criar(CCurDep);
          SQL_DefinirComando(CCurDep, aSqlDep);
          SQL_DefinirInteiro(CCurDep,"nCodEmp",nCodEmp);
          SQL_DefinirAlfa(CCurDep,"aCodLot",aCodLot);
          SQL_DefinirAlfa(CCurDep,"aNumBob",aNumBob);
          SQL_DefinirInteiro(CCurDep,"nCodCre",nCodCre);
          SQL_DefinirInteiro(CCurDep,"nNumCad",nNumCad);
          SQL_DefinirAlfa(CCurDep,"aCodOri",aCodOri);
          SQL_DefinirInteiro(CCurDep,"nNumOrp",nNumOrp);
          SQL_DefinirInteiro(CCurDep,"nCodEtg",nCodEtg);
          SQL_DefinirInteiro(CCurDep,"nSeqRot",nSeqRot);
          SQL_DefinirFlutuante(CCurDep,"nQtdRe1",nQtdRe1);
          SQL_DefinirData(CCurDep,"dDatMov",dDatMov);
          SQL_AbrirCursor(CCurDep);

          Se (SQL_EOF(CCurDep) = 0)
            {
              SQL_RetornarAlfa(CCurDep,"WWCodDep",aCodDep);
              nAchouDep = 1;
            }

          SQL_FecharCursor(CCurDep);
          SQL_Destruir(CCurDep);

          Se (nAchouDep = 1)
            {
              IniciarTransacao();

              ExecSQLEx(
              "UPDATE E210DLS \
                  SET USU_SITLOT = 'P' \
                WHERE CODEMP = :nCodEmp \
                  AND CODLOT = :aCodLot \
                  AND CODDEP = :aCodDep",
              VErro, aMsgStr);

              Se (VErro = 1)
                {
                  DesfazerTransacao();
                  aRetorno = "ERRO ao marcar lote como pendente: " + aMsgStr;
                  nErroGeral = 1;
                }
              Senao
                FinalizarTransacao();
            }
        }
      @ --- retorno padrÃ£o --- @
      PosicaoAlfa("ERRO", aRetorno, npos);


      Se ((npos > 0) ou (nErroGeral = 1))
        {
          vaRet = "{|status|:|ERRO|,|message|:|" + aRetorno + "|}";
        }
      Senao
        {
          vaRet = "{|status|:|OK|,|message|:|" + aRetorno + "|}";
        }
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
        vaMsg = "AÃ§Ã£o inexistente!";
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
    
    Apontamentos.waRetorno = vaRetorno;
  }
 
