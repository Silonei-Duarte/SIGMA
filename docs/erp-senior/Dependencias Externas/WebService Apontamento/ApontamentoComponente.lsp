/*
Webservice para apontar OP a partir de um componente recebido.

Fluxo:
1) Recebe os dados do apontamento e do componente consumido.
2) Calcula a quantidade apontada aplicando PERPRD, igual ao bloco da 929.
3) Aponta a OP com a quantidade liquida.
4) Grava na USU_TBXACMP os componentes proporcionais que baixam na OP.
5) Grava tambem o componente recebido com a quantidade total informada,
   independente dele ser consumo real ou estar marcado para baixar na OP.
*/

Definir alfa aCodOri;
Definir alfa aNumOrp;
Definir alfa aNumCad;
Definir alfa aCodEtg;
Definir alfa aSeqRot;
Definir alfa aQtdRe1;
Definir alfa aQtdRfg;
Definir alfa aNumMaq;
Definir alfa aParametros;
Definir alfa aRetorno;
Definir alfa wacao;

Definir alfa vaRetorno;
Definir alfa vaRet;
Definir alfa vaMsg;
Definir alfa vaDados;
Definir alfa aEmpresa;

@ CodLot e o lote do produto acabado/apontamento; aqui segue o padrao Origem-OP e vai para USU_LOTDES. @
Definir Alfa aCodLot;

@ Dados do componente recebido. CodLotCmp aqui ja e o lote real do componente. @
Definir Alfa aCodCmpRec;
Definir Alfa aDerCmpRec;
Definir Alfa aCodLotCmp;
Definir Alfa aQtdCmp;

Definir numero nNumOrp;
Definir numero nNumCad;
Definir numero nTurTrb;
Definir numero nQtdMov;
Definir numero nQtdCmp;
Definir numero nQtdDls;
Definir numero nQtdRe1;
Definir Numero nPerPrd;
Definir Numero nPrvCmo;
Definir Numero nPrvOop;
Definir Numero nQtdUti;
Definir Numero nCodEtg;
Definir Numero nSeqRot;
Definir Numero nCodCre;
Definir Numero nJaApt;
Definir Numero nTemDadosCmp;
Definir Numero nTemSaldoDls;
Definir Numero nErroSaldo;
Definir Numero nTemRea;
Definir Numero nCodEmp;
Definir Numero npos;
Definir Numero nErroGeral;
Definir Numero Tem;
Definir numero VErro;

Definir Alfa aCodPro;
Definir Alfa aCodDer;
Definir Alfa aTipQtd;
Definir Alfa aLogPrc;
Definir Alfa aIdeUni;
Definir Alfa aMsgStr;
Definir Alfa aMsgSaldo;
Definir Alfa aHorMov;
Definir Alfa aDatMov;
Definir Alfa aTurTrb;
Definir Alfa CCurCmp;
Definir Alfa TClaSql;

Definir Data dDatMov;
Definir Numero nHorMov;

Definir Lista lstExp;
lstExp.DefinirCampos();
lstExp.AdicionarCampo("CodPro", alfa);
lstExp.AdicionarCampo("CodDer", alfa);
lstExp.AdicionarCampo("QtdMov", numero);
lstExp.EfetivarCampos();

nCodEmp = CodEmp;

vaRetorno = "";
wacao = "";
vaMsg = "";
aCodLot = "";
aCodLotCmp = "";
aCodCmpRec = "";
aDerCmpRec = " ";
aQtdCmp = "";
aMsgSaldo = "";
nTipoRetorno = 0;
nEntrouAcao = 0;
nTemDadosCmp = 0;
nTemSaldoDls = 0;
nErroSaldo = 0;
nErroGeral = 0;
npos = 0;

@ Captura unico JSON enviado em wdados. @
ApontamentoComponente.tabelaEntradas.linhaatual = 0;
vaDados = ApontamentoComponente.tabelaEntradas.valor;
LimpaEspacos(vaDados);

ValorElementoJson(vaDados, "", "wacao", wacao);
ValorElementoJson(vaDados, "", "empresa", aEmpresa);
ValorElementoJson(vaDados, "", "CodOri", aCodOri);
ValorElementoJson(vaDados, "", "NumOrp", aNumOrp);
ValorElementoJson(vaDados, "", "NumCad", aNumCad);
ValorElementoJson(vaDados, "", "CodEtg", aCodEtg);
ValorElementoJson(vaDados, "", "SeqRot", aSeqRot);
ValorElementoJson(vaDados, "", "HorMov", aHorMov);
ValorElementoJson(vaDados, "", "DatMov", aDatMov);
ValorElementoJson(vaDados, "", "NumMaq", aNumMaq);

@ Campo especifico do componente recebido. @
ValorElementoJson(vaDados, "", "CodLotCmp", aCodLotCmp);
ValorElementoJson(vaDados, "", "CodCmpRec", aCodCmpRec);
ValorElementoJson(vaDados, "", "DerCmpRec", aDerCmpRec);
ValorElementoJson(vaDados, "", "QtdCmp", aQtdCmp);

@ Data e hora do movimento sao as mesmas usadas para apontar e ordenar a baixa. @
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

@ Empresa e filial do contexto. @
AlfaParaInt(aEmpresa, nCodEmp);
TrocaEmpresaFilial(nCodEmp, 1);

@ Busca o turno do operador, pois o SIGMA nao precisa enviar TurTrb. @
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

Se (wacao = "APONTAR-COMPONENTE")
  {
    nEntrouAcao = 1;
    aLogPrc = "Inserido por APONTAR-COMPONENTE";
    
    AlfaParaInt(aNumOrp, nNumOrp);
    AlfaParaInt(aCodEtg, nCodEtg);
    AlfaParaInt(aSeqRot, nSeqRot);
    AlfaParaInt(aNumMaq, nCodCre);
    @ O lote do acabado nao vem do JSON neste webservice; usa o padrao Origem-OP. @
    aCodLot = aCodOri + "-" + aNumOrp;
    
    @ Usa os dados do componente recebidos diretamente no JSON. @
    nTemDadosCmp = 1;
    nErroSaldo = 0;
    nTemSaldoDls = 0;
    nQtdCmp = 0;
    nQtdDls = 0;
    
    Se (aDerCmpRec = "")
      aDerCmpRec = " ";
    
    SubstAlfa(".", ",", aQtdCmp);
    AlfaParaDecimal(aQtdCmp, nQtdCmp);
    
    @ Valida o saldo real do mesmo lote/produto/derivacao recebidos. @
    TClaSql = "SELECT COUNT(1) WWQtdReg, \
                      SUM(QTDEST) WWQtdEst \
                 FROM E210DLS \
                WHERE CODEMP = :nCodEmp \
                  AND CODLOT = :aCodLotCmp \
                  AND CODPRO = :aCodCmpRec \
                  AND CODDER = :aDerCmpRec";
    
    SQL_Criar(CCurCmp);
    SQL_UsarSQLSenior2(CCurCmp,0);
    SQL_UsarAbrangencia(CCurCmp,0);
    SQL_DefinirComando(CCurCmp, TClaSql);
    SQL_DefinirInteiro(CCurCmp,"nCodEmp",nCodEmp);
    SQL_DefinirAlfa(CCurCmp,"aCodLotCmp",aCodLotCmp);
    SQL_DefinirAlfa(CCurCmp,"aCodCmpRec",aCodCmpRec);
    SQL_DefinirAlfa(CCurCmp,"aDerCmpRec",aDerCmpRec);
    SQL_AbrirCursor(CCurCmp);
    
    Se (SQL_EOF(CCurCmp) = 0)
      {
        SQL_RetornarInteiro(CCurCmp,"WWQtdReg",nTemSaldoDls);
        SQL_RetornarFlutuante(CCurCmp,"WWQtdEst",nQtdDls);
      }
    
    SQL_FecharCursor(CCurCmp);
    SQL_Destruir(CCurCmp);
    
    Se (nTemSaldoDls = 0)
      {
        nErroSaldo = 1;
        aMsgSaldo = "Lote/produto/derivacao nao encontrado na E210DLS: Lote " + aCodLotCmp + ", Produto " + aCodCmpRec + ", Derivacao " + aDerCmpRec;
        vaRet = "{|status|:|ERRO|,|message|:|" + aMsgSaldo + "|}";
      }
    
    Se ((nTemSaldoDls > 0) e (nQtdDls < nQtdCmp))
      {
        nErroSaldo = 1;
        aMsgSaldo = "Saldo do lote na E210DLS menor que a quantidade informada do componente: Lote " + aCodLotCmp + ", Produto " + aCodCmpRec + ", Derivacao " + aDerCmpRec;
        vaRet = "{|status|:|ERRO|,|message|:|" + aMsgSaldo + "|}";
      }
    
    @ Este apontamento nao recebe refugo; envia QtdRfg zerada ao ApontarOPs. @
    aQtdRfg = "0";

    /*
    Busca PERPRD do componente recebido no modelo da OP.
    Na 929 a origem 510 usa este percentual para reduzir a quantidade que sera apontada.
    */
    nPerPrd = 0;
    TClaSql = "SELECT E700CTM.PERPRD WWPerPrd \
                 FROM E700CTM \
                 JOIN E900QDO \
                   ON E900QDO.CODEMP = E700CTM.CODEMP \
                  AND E900QDO.CODMOD = E700CTM.CODMOD \
                  AND E900QDO.CODDER = E700CTM.CODDER \
                WHERE E900QDO.CODEMP = :nCodEmp \
                  AND E900QDO.CODORI = :aCodOri \
                  AND E900QDO.NUMORP = :nNumOrp \
                  AND E700CTM.CODETG = :nCodEtg \
                  AND E700CTM.CODCMP = :aCodCmpRec \
                  AND E700CTM.DERCMP = :aDerCmpRec";
    SQL_Criar(CCurCmp);
    SQL_UsarSQLSenior2(CCurCmp,0);
    SQL_UsarAbrangencia(CCurCmp,0);
    SQL_DefinirComando(CCurCmp, TClaSql);
    SQL_DefinirInteiro(CCurCmp,"nCodEmp",nCodEmp);
    SQL_DefinirAlfa(CCurCmp,"aCodOri",aCodOri);
    SQL_DefinirInteiro(CCurCmp,"nNumOrp",nNumOrp);
    SQL_DefinirInteiro(CCurCmp,"nCodEtg",nCodEtg);
    SQL_DefinirAlfa(CCurCmp,"aCodCmpRec",aCodCmpRec);
    SQL_DefinirAlfa(CCurCmp,"aDerCmpRec",aDerCmpRec);
    SQL_AbrirCursor(CCurCmp);
    
    Se (SQL_EOF(CCurCmp) = 0)
      SQL_RetornarFlutuante(CCurCmp,"WWPerPrd",nPerPrd);
    
    SQL_FecharCursor(CCurCmp);
    SQL_Destruir(CCurCmp);

    @ Quantidade apontada = quantidade recebida menos perda percentual do modelo. @
    nQtdRe1 = nQtdCmp;
    Se (nPerPrd > 0)
      nQtdRe1 = nQtdRe1 - ((nQtdRe1 * nPerPrd) / 100);
      
    Arredonda(nQtdRe1, 2);
    IntParaStr(nQtdRe1, aQtdRe1);
    SubstAlfa(",", ".", aQtdRe1);

    @ Evita processar duas vezes o mesmo componente recebido. @
    @ A duplicidade aqui e pela fila de baixa, usando OP, recurso e lote do componente. @
    nJaApt = 0;
    
    Definir Alfa CCurDup;
    Definir Alfa aSqlDup;
    
    aSqlDup = "SELECT 1 WWAchou \
                 FROM USU_TBXACMP \
                WHERE USU_CODEMP = :nCodEmp \
                  AND USU_CODORI = :aCodOri \
                  AND USU_NUMORP = :nNumOrp \
                  AND USU_CODETG = :nCodEtg \
                  AND USU_CODCMP = :aCodCmpRec \
                  AND USU_DERCMP = :aDerCmpRec \
                  AND USU_CODCRE = :aNumMaq \
                  AND USU_CODLOT = :aCodLotCmp";
    
    SQL_Criar(CCurDup);
    SQL_DefinirComando(CCurDup, aSqlDup);
    SQL_DefinirInteiro(CCurDup, "nCodEmp", nCodEmp);
    SQL_DefinirAlfa(CCurDup, "aCodOri", aCodOri);
    SQL_DefinirInteiro(CCurDup, "nNumOrp", nNumOrp);
    SQL_DefinirInteiro(CCurDup, "nCodEtg", nCodEtg);
    SQL_DefinirAlfa(CCurDup, "aCodCmpRec", aCodCmpRec);
    SQL_DefinirAlfa(CCurDup, "aDerCmpRec", aDerCmpRec);
    SQL_DefinirAlfa(CCurDup, "aNumMaq", aNumMaq);
    SQL_DefinirAlfa(CCurDup, "aCodLotCmp", aCodLotCmp);
    SQL_AbrirCursor(CCurDup);
    
    Se (SQL_EOF(CCurDup) = 0)
      {
        nJaApt = 1;
        vaRet = "{|status|:|OK|,|message|:|lote do Componente recebido ja esta na fila de baixa|}";
      }
    
    SQL_FecharCursor(CCurDup);
    SQL_Destruir(CCurDup);

    Se (nErroSaldo = 1)
      {
        vaRet = "{|status|:|ERRO|,|message|:|" + aMsgSaldo + "|}";
      }

    Se ((nTemDadosCmp = 1) e (nErroSaldo = 0) e (nQtdRe1 <= 0) e (nJaApt = 0))
      {
        vaRet = "{|status|:|ERRO|,|message|:|Quantidade apontada ficou zerada apos aplicar PERPRD|}";
      }
    
    Se ((nTemDadosCmp = 1) e (nErroSaldo = 0) e (nQtdRe1 > 0) e (nJaApt = 0))
      {
        @ Primeiro apontamento da OP: cria backup do BxaOrp original quando ainda nao existe. @
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

        /*
        Lista somente os componentes que a OP baixaria automaticamente.
        Esta consulta nao decide o componente recebido.
        O recebido sempre sera gravado em bloco separado, mesmo se for consumo real
        ou se nao estiver com USU_BxaOrp = 'S' na OP.
        A lista serve para restaurar BxaOrp depois do apontamento e para gerar a fila proporcional.
        */
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
        SQL_UsarAbrangencia(CCurCmp,0);
        SQL_DefinirComando(CCurCmp, TClaSql);
        SQL_DefinirInteiro(CCurCmp,"nCodEmp",nCodEmp);
        SQL_DefinirAlfa(CCurCmp,"aCodOri",aCodOri);
        SQL_DefinirInteiro(CCurCmp,"nNumOrp",nNumOrp);
        SQL_AbrirCursor(CCurCmp);
        
        Enquanto (SQL_EOF(CCurCmp) = 0)
          {
            SQL_RetornarAlfa(CCurCmp,"WWCodCmp",aCodPro);
            SQL_RetornarAlfa(CCurCmp,"WWCodDer",aCodDer);
            SQL_RetornarFlutuante(CCurCmp,"WWPrvCmo",nPrvCmo);
            SQL_RetornarFlutuante(CCurCmp,"WWPrvOop",nPrvOop);
            SQL_RetornarAlfa(CCurCmp,"WWTipQtd",aTipQtd);
            SQL_RetornarFlutuante(CCurCmp,"WWQtdUti",nQtdUti);
            
            @ Mesmo criterio do Apontamentos.lsp: fixa usa QtdUti; demais proporcionalizam. @
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
            
            lstExp.Adicionar();
            lstExp.CodPro = aCodPro;
            lstExp.CodDer = aCodDer;
            lstExp.QtdMov = nQtdMov;
            lstExp.Gravar();
            
            SQL_Proximo(CCurCmp);
          }
        
        SQL_FecharCursor(CCurCmp);
        SQL_Destruir(CCurCmp);

        @ Desliga a baixa automatica para o ApontarOPs nao consumir direto. @
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
            aRetorno = "Erro ao desligar baixa automatica: " + aMsgStr;
          }

        @ Verifica se ja existe apontamento de inicio para o operador/etapa. @
        Definir Alfa xCurEOQ;
        Definir Alfa xSql;
        Definir Data dDatIni;
        Definir Data dBase;
        
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

        @ Parametros base do apontamento do produto acabado. @
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
                    ",Usu_NumMaq=" + aNumMaq;
        
        aParametros = aBaseParam +
                      ",QtdRe1=" + aQtdRe1 +
                      ",QtdRfg=" + aQtdRfg;
        
        Se (nErroGeral = 0)
          {
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
                PosicaoAlfa("ERRO", aRetorno, npos);
                
                Se (npos = 0)
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
              aRetorno = "Erro ao restaurar baixa automatica: " + aMsgStr;
            
            nErroGeral = 1;
          }

        Se (nErroGeral = 1)
          {
            DesfazerTransacao();
            
            Se (aRetorno = "")
              aRetorno = "Erro ao apontar OP";
          }
        Senao
          {
            FinalizarTransacao();
          }

        @ Grava a fila de baixa somente depois de encerrar a transacao do apontamento. @
        Se ((nErroGeral = 0) e (npos = 0))
          {
            Tem = lstExp.Primeiro();
            Enquanto (Tem = 1)
              {
                aCodPro = lstExp.CodPro;
                aCodDer = lstExp.CodDer;
                nQtdMov = lstExp.QtdMov;

                /*
                Se o componente recebido tambem estiver na lista da OP, nao grava proporcional dele aqui.
                Ele sera gravado abaixo com a quantidade total recebida e com o lote do componente.
                */
                Se ((nQtdMov > 0) e ((aCodPro <> aCodCmpRec) ou (aCodDer <> aDerCmpRec)))
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
                        aRetorno = "Erro ao gravar componente proporcional: " + aMsgStr;
                        nErroGeral = 1;
                      }
                    Senao
                      FinalizarTransacao();
                  }
                
                Tem = lstExp.Proximo();
              }
          }

        /*
        Grava o componente recebido com a quantidade total informada.
        Aqui nao aplica proporcional nem perda, porque esta linha representa o consumo real recebido.
        Tambem nao valida BxaOrp nem USU_CONREL: se veio no webservice, precisa ir para baixa.
        */
        Se ((nErroGeral = 0) e (npos = 0) e (nQtdCmp > 0))
          {
            ObterGuid(aIdeUni);

            IniciarTransacao();

            ExecSqlEx(
            "Insert Into USU_TBXACMP (USU_CODEMP, USU_CODORI, USU_NUMORP, USU_CODETG, \
                USU_CODCMP, USU_DERCMP, USU_LOTDES, USU_QTDUTI, USU_LOGINC, \
                USU_CODCRE, USU_CODLOT, USU_DATMOV, USU_HORMOV, USU_SITPEN, USU_IDEUNI) \
              Values (:nCodEmp, :aCodOri, :nNumOrp, :nCodEtg, \
                :aCodCmpRec, :aDerCmpRec, :aCodLot, :nQtdCmp, :aLogPrc, \
                :aNumMaq, :aCodLotCmp, :dDatMov, :nHorMov, 1, :aIdeUni)",
            VErro, aMsgStr);
            
            Se (VErro = 1)
              {
                DesfazerTransacao();
                aRetorno = "Erro ao gravar componente recebido: " + aMsgStr;
                nErroGeral = 1;
              }
            Senao
              FinalizarTransacao();
          }

        Se (nErroGeral = 1)
          {
            Se (aRetorno = "")
              aRetorno = "Erro ao apontar OP ou gravar componentes";
            
            vaRet = "{|status|:|ERRO|,|message|:|" + aRetorno + "|}";
          }
        Senao
          {
            Se (aRetorno = "")
              aRetorno = "Apontamento realizado e componentes enviados para baixa";
            
            vaRet = "{|status|:|OK|,|message|:|" + aRetorno + "|}";
          }
      }
  }

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
    
    ApontamentoComponente.waRetorno = vaRetorno;
  }
