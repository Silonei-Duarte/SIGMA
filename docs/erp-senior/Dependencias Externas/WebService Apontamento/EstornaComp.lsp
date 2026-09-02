/*
Processa pendencias de estorno gravadas na USU_TESTCMP via webservice.

Fluxo baseado na regra anterior (recebida por wacao=ESTORNAR-COMPONENTES), agora disparada
pela agendadora (AgendadoraBaixarComponentes.lsp) via CUSTOM.SENIOR.MAN.PRODUCAO.ESTORNACOMP:
1) Recebe USU_IdeUni pela tabela de pendencias do webservice.
2) Busca deposito/lote do ultimo consumo do componente (CodTns 90251) para reaproveitar na baixa.
3) Libera o componente na OP (BXAORP='S') com o lote/deposito encontrado.
4) Chama EstornaComponentes.
5) Atualiza a USU_TESTCMP com sucesso ou erro e grava log de processamento.

USU_SITPEN:
1 = pendente
2 = em processamento
3 = processado
4 = erro
*/

Definir Funcao Fun_GravaLog();

Definir Alfa CCurEst;
Definir Alfa CCurSeq;
Definir Alfa TClaSql;
Definir Alfa aMsgStr;
Definir Alfa aRetorno;
Definir Alfa aCodOri;
Definir Alfa aNumOrp;
Definir Alfa aCodPro;
Definir Alfa aCodDer;
Definir Alfa aCodCmp;
Definir Alfa aDerCmp;
Definir Alfa aCodTns;
Definir Alfa aCodDep;
Definir Alfa aCodLot;
Definir Alfa aQtdEstAlfa;
Definir Alfa aIdeUni;
Definir Alfa aDesRet;
Definir Alfa aInfAdc;
Definir Alfa aInfLog;
Definir Alfa aJsoEnv;

Definir Numero nCodEmp;
Definir Numero nNumOrp;
Definir Numero nCodEtg;
Definir Numero nQtdEst;
Definir Numero nQtdReg;
Definir Numero nCtdReg;
Definir Numero nHorSis;
Definir Numero nUsuPrc;
Definir Numero nErro;
Definir Numero nPos;
Definir Numero nStaInt;

Definir Data dDatFim;
Definir Data dDatSis;

nQtdReg = EstornaComp.pendencias.qtdLinhas;
nCtdReg = 0;

Enquanto (nCtdReg < nQtdReg)
  {
    EstornaComp.pendencias.linhaAtual = nCtdReg;
    aIdeUni = EstornaComp.pendencias.ideUni;

    TClaSql = "SELECT USU_CODEMP WWCodEmp, \
                      USU_CODORI WWCodOri, \
                      USU_NUMORP WWNumOrp, \
                      USU_CODETG WWCodEtg, \
                      USU_CODCMP WWCodCmp, \
                      USU_DERCMP WWDerCmp, \
                      USU_CODPRO WWCodPro, \
                      USU_CODDER WWCodDer, \
                      USU_QTDEST WWQtdEst, \
                      USU_DATFIM WWDatFim, \
                      USU_CODTNS WWCodTns \
                 FROM USU_TESTCMP \
                WHERE USU_IdeUni = :aIdeUni \
                  AND USU_SitPen = 2";

    SQL_Criar(CCurEst);
    SQL_UsarSQLSenior2(CCurEst,0);
    SQL_UsarAbrangencia(CCurEst,0);
    SQL_DefinirComando(CCurEst, TClaSql);
    SQL_DefinirAlfa(CCurEst, "aIdeUni", aIdeUni);
    SQL_AbrirCursor(CCurEst);

    Se (SQL_EOF(CCurEst) = 0)
      {
        @ Carrega a pendencia. @
        SQL_RetornarInteiro(CCurEst,"WWCodEmp",nCodEmp);
        SQL_RetornarAlfa(CCurEst,"WWCodOri",aCodOri);
        SQL_RetornarInteiro(CCurEst,"WWNumOrp",nNumOrp);
        SQL_RetornarInteiro(CCurEst,"WWCodEtg",nCodEtg);
        SQL_RetornarAlfa(CCurEst,"WWCodCmp",aCodCmp);
        SQL_RetornarAlfa(CCurEst,"WWDerCmp",aDerCmp);
        SQL_RetornarAlfa(CCurEst,"WWCodPro",aCodPro);
        SQL_RetornarAlfa(CCurEst,"WWCodDer",aCodDer);
        SQL_RetornarFlutuante(CCurEst,"WWQtdEst",nQtdEst);
        SQL_RetornarData(CCurEst,"WWDatFim",dDatFim);
        SQL_RetornarAlfa(CCurEst,"WWCodTns",aCodTns);

        dDatSis = DatSis;
        nHorSis = HorSis;
        nUsuPrc = CodUsu;

        TrocaEmpresaFilial(nCodEmp,1);

        IntParaAlfa(nNumOrp,aNumOrp);
        IntParaStr(nQtdEst,aQtdEstAlfa);
        SubstAlfa(",", ".", aQtdEstAlfa);
        aInfLog = "Origem " + aCodOri + " OP " + aNumOrp + " Comp. " + aCodCmp + "/" + aDerCmp + " Qtd. " + aQtdEstAlfa + " - ";
        aJsoEnv = aInfLog;

        aRetorno = "";
        aCodDep = "";
        aCodLot = "";

        @ Busca deposito/lote do consumo mais recente do componente para reaproveitar na baixa/estorno. @
        TClaSql = "SELECT CodDep, CodLot \
                     FROM E210MVP \
                    WHERE CodEmp = :nCodEmp \
                      AND OriOrp = :aCodOri \
                      AND NumDoc = :nNumOrp \
                      AND CodEtg = :nCodEtg \
                      AND CodPro = :aCodCmp \
                      AND CodDer = :aDerCmp \
                      AND CodTns in ('90251') \
                    ORDER BY DatMov Desc, SeqMov";

        SQL_Criar(CCurSeq);
        SQL_DefinirComando(CCurSeq,TClaSql);
        SQL_DefinirInteiro(CCurSeq,"nCodEmp",nCodEmp);
        SQL_DefinirAlfa(CCurSeq,"aCodOri",aCodOri);
        SQL_DefinirInteiro(CCurSeq,"nNumOrp",nNumOrp);
        SQL_DefinirInteiro(CCurSeq,"nCodEtg",nCodEtg);
        SQL_DefinirAlfa(CCurSeq,"aCodCmp",aCodCmp);
        SQL_DefinirAlfa(CCurSeq,"aDerCmp",aDerCmp);
        SQL_AbrirCursor(CCurSeq);

        Se (SQL_EOF(CCurSeq) = 0)
          {
            SQL_RetornarAlfa(CCurSeq,"CodDep",aCodDep);
            SQL_RetornarAlfa(CCurSeq,"CodLot",aCodLot);

            @ Seta que o componente baixa em OP, lote e deposito = deposito do que foi consumido anteriormente. @
            IniciarTransacao();
            ExecSQLEx(
            "UPDATE E900CMO \
                SET BXAORP = 'S', CodLot = :aCodLot, CodDep = :aCodDep \
              WHERE CODEMP = :nCodEmp \
                AND CODORI = :aCodOri \
                AND NUMORP = :nNumOrp \
                AND CODCMP = :aCodCmp \
                AND CODDER = :aDerCmp",
            nErro,aMsgStr);

            Se (nErro = 1)
              DesfazerTransacao();
            Senao
              FinalizarTransacao();
          }

        SQL_FecharCursor(CCurSeq);
        SQL_Destruir(CCurSeq);

        EstornaComponentes(aCodOri, nNumOrp, nCodEtg, aCodPro, aCodDer, aCodCmp, aDerCmp, nQtdEst, dDatFim, aCodTns, aRetorno);

        PosicaoAlfa("ERRO", aRetorno, nPos);

        Se (nPos > 0)
          {
            IniciarTransacao();
            ExecSQLEx(
            "UPDATE USU_TESTCMP \
                SET USU_SITPEN = 4, \
                    USU_DATPRC = :dDatSis, \
                    USU_HORPRC = :nHorSis, \
                    USU_USUPRC = :nUsuPrc \
              WHERE USU_IDEUNI = :aIdeUni",
            nErro,aMsgStr);

            Se (nErro = 1)
              DesfazerTransacao();
            Senao
              FinalizarTransacao();

            nStaInt = 4; @ 4 - Erro @
            aDesRet = "Estorno de componente.";
            aInfAdc = aInfLog + aRetorno;
          }
        Senao
          {
            IniciarTransacao();
            ExecSQLEx(
            "UPDATE USU_TESTCMP \
                SET USU_SITPEN = 3, \
                    USU_DATPRC = :dDatSis, \
                    USU_HORPRC = :nHorSis, \
                    USU_USUPRC = :nUsuPrc \
              WHERE USU_IDEUNI = :aIdeUni",
            nErro,aMsgStr);

            Se (nErro = 1)
              {
                DesfazerTransacao();
                nStaInt = 4; @ 4 - Erro @
                aDesRet = "Estorno de componente.";
                aInfAdc = aInfLog + "Erro ao atualizar status da pendencia: " + aMsgStr;
              }
            Senao
              {
                FinalizarTransacao();
                nStaInt = 3; @ 3 - Sucesso @
                aDesRet = "Estorno de componente.";
                aInfAdc = aInfLog + "Processado com sucesso.";
              }
          }

        Fun_GravaLog();
      }

    SQL_FecharCursor(CCurEst);
    SQL_Destruir(CCurEst);
    nCtdReg++;
  }

@ Ao final do lote, remove somente pendencias processadas com sucesso ha mais de 3 meses. @
IniciarTransacao();
ExecSQLEx(
"DELETE FROM USU_TESTCMP \
  WHERE USU_SITPEN = 3 \
    AND USU_DATPRC < ADD_MONTHS(TRUNC(SYSDATE), -3)",
nErro,aMsgStr);

Se (nErro = 1)
  DesfazerTransacao();
Senao
  FinalizarTransacao();

Funcao Fun_GravaLog();
Inicio
  Definir interno.custom.senior.logs.GravarLog sGrvLog;
  sGrvLog.CodPrc = 3;
  sGrvLog.IdePrc = "EST";
  sGrvLog.CodEmp = nCodEmp;
  sGrvLog.StaInt = nStaInt; @ 3-Processado, 4-Erro @
  sGrvLog.DesRet = aDesRet;
  sGrvLog.InfAdc = aInfAdc;
  sGrvLog.IdeUni = aIdeUni;
  sGrvLog.JsoEnv = aJsoEnv;
  sGrvLog.Executar();
Fim;
