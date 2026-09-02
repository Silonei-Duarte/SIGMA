/*
Baixa do deposito 02.00 - CDBR470, pois não existe nota de saida de lá para ipel
14/01/2022 - ECC (implementação)
*/
Definir Numero VSCODEMP; @ NÚMERO	Código da empresa	N @
Definir Alfa   VSCODPRO; @ ALFA	Código do produto	N @
Definir Alfa   VSCODDER; @ ALFA	Código da derivação	N @
Definir Alfa   VSCODDEP; @ ALFA	Código do depósito	N @
Definir Data   VSDATMOV; @ DATA	Data do Movimento	N @
Definir Numero VSSEQMOV; @ NÚMERO	Sequência do movimento	N @
Definir Alfa   VSCODTNS; @ ALFA	Código da transação	N @
Definir Alfa   VSESTMOV; @ ALFA	Tipo de estoque movimentado	N @
Definir Alfa   VSESTEOS; @ ALFA	Entrada ou Saída	N @
Definir Alfa   VSCODLOT; @ NÚMERO	Código do Lote de fabricação	N @
Definir Data   VSDATFAB; @ DATA	Data de fabricação	N @
Definir Data   VSDATVLT; @ DATA	Data de validade do lote de fabricação	N @
Definir Alfa   VSNUMSEP; @ ALFA	Número de Série do Produto	N @
Definir Alfa   VSOBSMVP; @ ALFA	Observação para uso exclusivo do processo de fechamento dos estoques	N @
Definir Numero VSQTDMOV; @ NÚMERO	Quantidade do movimento	N @
Definir Numero VSVLRMOV; @ NÚMERO	Valor do movimento	N @
Definir Alfa   VSPROTRF; @ ALFA	Produto transferido	N @
Definir Alfa   VSDERTRF; @ ALFA	Derivação transferida	N @
Definir Alfa   VSDEPTRF; @ ALFA	Depósito transferido	N @
Definir Numero VSQTDANT; @ NÚMERO	Quantidade Anterior - não disponibilizada. Se necessário deve ser obtida na regra.	N @
Definir Numero VSVLRANT; @ NÚMERO	Valor Anterior - não disponibilizada. Se necessário deve ser obtida na regra.	N @
Definir Numero VSCODFIL; @ NÚMERO	Código da filial da nota fiscal de saída	N @
Definir Alfa   VSCODSNF; @ ALFA	Código da série da nota fiscal de saída	N @
Definir Numero VSNUMNFV; @ NÚMERO	Número da nota fiscal de saída	N @
Definir Numero VSSEQIPV; @ NÚMERO	Sequência da nota fiscal de saída	N @
Definir Numero VSCODCLI; @ NÚMERO	Código do Cliente	N @
Definir Numero VSFILNFC; @ ALFA	Código da filial da nota fiscal de entrada	N @
Definir Numero VSNUMNFC; @ NÚMERO	Número da nota fiscal de entrada	N @
Definir Numero VSCODFOR; @ NÚMERO	Código do fornecedor	N @
Definir Numero VSSEQIPC; @ NÚMERO	Sequência da nota fiscal de entrada	N @
Definir Numero VSNUMEME; @ NÚMERO	Número da requisição	N @
Definir Alfa   VSSNFNFC; @ ALFA	Série da Nota Fiscal de Entrada	N @
Definir Numero VSSEQEME; @ NÚMERO	Sequência da requisição	N @
Definir Numero VSUSURES; @ NÚMERO	Usuário responsável	N @
Definir Numero VSCTARED; @ NÚMERO	Conta reduzida	N @
Definir Numero VSCTAFIN; @ NÚMERO	Conta financeira	N @
Definir Alfa   VSLCTFIN; @ ALFA	Indicativo se o movimento foi lançado no plano financeiro	N @
Definir Numero VSNUMLOT; @ NÚMERO	Número do lote contábil	N @
Definir Numero VSUSUDIG; @ NÚMERO	Usuário da digitação	N @
Definir Data   VSDATDIG; @ DATA	Data da digitação	N @
Definir Numero VSHORDIG; @ NÚMERO	Horário da digitação	N @
Definir Numero VSNUMPRJ; @ NÚMERO	Número interno do projeto	N @
Definir Numero VSCODFPJ; @ NÚMERO	Código da fase do projeto	N @
Definir Alfa   VSMOTMVP; @ ALFA	Observação do movimento de estoque (uso geral)	N @
Definir Alfa   VSORIGEM; @ ALFA	Tela origem de chamada da regra	N @
Definir Numero ESTNNUMDOC;@ NÚMERO	Número do Documento	N @ @ NÚMERO DA OP @
Definir Alfa   VSCODORI; @ ALFA	Código da Origem do Produto	N @
Definir Alfa   VSESTADO; @ ALFA	Estado da movimentação(INSERINDO ou EXCLUINDO)	N @
Definir Numero VnCodEmp;
Definir Numero VnCodFil;
Definir Alfa   VaE201MVP;
Definir Alfa   VaBusEst;
Definir Alfa   VaCodpro;
Definir Numero VnNumDoc;
Definir Numero VnQtdMov220;
Definir Numero VnQtdMov257;
Definir Numero VnNumNfc;
Definir Alfa   VaSnfNfc;
Definir Numero VnFilNfc;
Definir Numero VnSeqIpc;
Definir interno.com.senior.g5.co.mcm.est.estoques.MovimentarEstoque VMovEst;
Definir Alfa   VaCodEmp;
Definir Alfa   VaCodFil;
Definir Alfa   VaCodDer; @ String	(Obrigatório) - String(007) - Derivação @
Definir Alfa   VaCodDep; @ String	(Obrigatório) - String(010) - Depósito @
Definir Alfa   VaCodTns; @ String	(Obrigatório) - String(005) - Transação @
Definir Alfa   VaQtdMov; @ String	(Opcional) - Number(014) - Quantidade do Movimento @
Definir Data   VdDatMov; @ String	(Opcional) - Date(DD/MM/AAAA) - Data do Movimento @
Definir Alfa   VaDatMov;
Definir numero VnCodFor; @ String	(Opcional) - Number(009) - Código do Fornecedor @
Definir Alfa   VaCodFor;
Definir numero VnNumDoc; @ String	(Opcional) - Number(009) - Número do Documento @
Definir Alfa   VaNumDoc;
Definir Alfa   VaCodSnf; @ String	(Opcional) - String(003) - Código da série da nota fiscal de saída @
Definir numero VnNumNfc; @ String	(Opcional) - Number(009) - Número da nota fiscal de entrada @
Definir numero VnSeqIpc; @ String	(Opcional) - String(003) - Sequência do item da nota fiscal de entrada @
Definir Alfa   VaSeqIpc;
Definir Alfa   VaCodlot; @ String	(Opcional) - String(050) - Lote de Fabricação @
Definir Alfa   ASql;
Definir Alfa   xSqlDer;
Definir Alfa   VaMgs;
Definir Data   VDatAux;
Definir Data   VdDatMov;
Definir Alfa   VaFinPes;
Definir Alfa   VaCodDep;
Definir Alfa   VaSeqMov;
Definir Numero VSNUMNFC;
Definir Numero VnSeqMov;
Definir Alfa   VSCODTNS;
Definir Alfa   VSCodPro;


/*
 - 05/12/2024 - IVM (implantação) - Adicionando validação de produto em inventário. Chamado 26783.
*/

Definir Alfa   TClaSql;
Definir Alfa   xEstInv;
Definir Numero nIndInv;

Se ((VSCODTNS <> "90205") e (VSCODTNS <> "90255"))
inicio
    TClaSql = "SELECT est.INDINV WWIndInv \
                FROM E210EST est  \
                WHERE est.CODEMP = :VSCODEMP  \
                AND est.CODPRO = :VSCODPRO  \
                AND est.CODDER = :VSCODDER  \
                AND est.CODDEP = :VSCODDEP  \
                AND est.INDINV <> 0";
    SQL_Criar(xEstInv);
    SQL_DefinirComando(xEstInv, TClaSql);
    SQL_DefinirInteiro(xEstInv,"VSCODEMP",VSCODEMP);
    SQL_DefinirAlfa(xEstInv,"VSCODPRO",VSCODPRO);
    SQL_DefinirAlfa(xEstInv,"VSCODDER",VSCODDER);
    SQL_DefinirAlfa(xEstInv,"VSCODDEP",VSCODDEP);

    SQL_AbrirCursor(xEstInv);
    Se (SQL_EOF(xEstInv) = 0) {
        SQL_RetornarInteiro(xEstInv,"WWIndInv",nIndInv);
        Se (nIndInv <> 0) {
            Mensagem(Erro, "Produto em inventário. Operação cancelada!");
        }
    }
    SQL_Destruir(xEstInv);
Fim;



/*
 - 06/06/2025 - DGF (implantação) - Adicionanda consistência de produto em inventário. Chamado 30192.
*/

Definir Alfa aSQL;
Definir Alfa aCursor;
Definir Alfa aEstTei;
Definir Alfa aEstTsi;

@ Busca Transações de inventário parametrizadas na Filial @
aSQL = "SELECT ESTTEI,ESTTSI              \
          FROM E070FIL                    \
         WHERE E070FIL.CODEMP = :VSCODEMP \
           AND E070FIL.CODFIL = :VSCODFIL";
SQL_Criar(aCursor);
SQL_DefinirComando(aCursor, aSQL);
SQL_DefinirInteiro(aCursor,"VSCODEMP",VSCODEMP);
SQL_DefinirInteiro(aCursor,"VSCODFIL",VSCODFIL);
SQL_AbrirCursor(aCursor);
Se (SQL_EOF(aCursor) = 0)
{
  SQL_RetornarAlfa(aCursor,"ESTTEI", aEstTei);
  SQL_RetornarAlfa(aCursor,"ESTTSI", aEstTsi);
}
SQL_Destruir(aCursor);

@ Valida apenas se não for transação de acerto de inventário @
Se ((VSCODTNS <> aEstTei) e (VSCODTNS <> aEstTsi))
{
  Definir Alfa aCodOri;
  Definir Alfa vMsgBlq;

  aSQL = "SELECT PINV.CODORI WWCODORI                              \
            FROM E210EST EST                                       \
      INNER JOIN E075PRO PINV ON PINV.CODEMP = EST.CODEMP          \
                             AND PINV.CODPRO = EST.CODPRO          \
           WHERE EST.CODEMP = :VSCODEMP                            \
             AND PINV.CODORI = (SELECT PRO_MOV.CODORI              \
                                  FROM E075PRO PRO_MOV             \
                                 WHERE PRO_MOV.CODEMP = :VSCODEMP  \
                                   AND PRO_MOV.CODPRO = :VSCODPRO) \
             AND EST.INDINV > 0";

  SQL_Criar(aCursor);
  SQL_UsarAbrangencia(aCursor, 0);
  SQL_UsarSQLSenior2(aCursor, 0);
  SQL_DefinirComando(aCursor, aSQL);
  SQL_DefinirInteiro(aCursor,"VSCODEMP",VSCODEMP);
  SQL_DefinirAlfa(aCursor,"VSCODPRO",VSCODPRO);
  SQL_AbrirCursor(aCursor);
  Se (SQL_EOF(aCursor) = 0) {
      SQL_RetornarAlfa(aCursor,"WWCODORI", aCodOri);
      vMsgBlq = "Movimentação bloqueada, pois existem produtos da mesma Origem "  + aCodOri +  " que estão em inventário";
      Mensagem(Erro, vMsgBlq);
  }
  SQL_Destruir(aCursor);
}
Definir Numero nFilDep;        @ filial do depósito de origem  @
Definir Numero nFilTrf;        @ filial do depósito de transferência (destino) @
Definir Numero nTemNF;         @ 1 = existe NF (entrada ou saída); 0 = sem NF @
Definir Numero nDepTrfNulo;    @ retorno do EstaNulo para VSDepTrf (1 = nulo) @
Definir Alfa   TSql;
Definir Alfa   xCur;
Definir Alfa   aMsg;
Definir Alfa   aFilDep;

/*
SEÇÃO 3: TRANSFERÊNCIAS SEM NF - REGRAS ATUALIZADAS
04/03/2026 - ECC (implementação)
Consistência: depósito em filial ?1 só pode movimentar sem NF quando:
   (a) transação inventário 90205/90255 ou
   (b) transferência para depósito da mesma filial
Caso contrário, bloqueia.
*/

@ 1) NF informada? @
nTemNF = 0;
Se ((VSNUMNFC > 0) ou (VSNUMNFV > 0))
  nTemNF = 1;

@ 2) é inventário? @
nTemInv = 0;
Se ((VSCODTNS = aEstTei) ou (VSCODTNS = aEstTsi))
  nTemInv = 1;

@ 3) filial do depósito de origem @
nFilDep = 0;
TSql = "SELECT CODFIL WWCodFil FROM E205DEP \
         WHERE CODEMP = :VSCODEMP \
           AND CODDEP = :VSCODDEP";
SQL_Criar(xCur);
SQL_DefinirComando(xCur, TSql);
SQL_DefinirInteiro(xCur, "VSCODEMP", VSCODEMP);
SQL_DefinirAlfa   (xCur, "VSCODDEP", VSCODDEP);
SQL_AbrirCursor(xCur);
Se (SQL_EOF(xCur) = 0)
{
    SQL_RetornarInteiro(xCur, "WWCodFil", nFilDep);
}
SQL_Destruir(xCur);

@ 4) Se filial origem ?1 e não há NF... @
Se ((nFilDep <> 1) e (nTemInv = 0) e (nTemNF = 0))
Inicio
    @ 4.1) Checa VSDepTrf e obtém filial destino @
    EstaNulo(VSDepTrf, nDepTrfNulo);
    Se ((nDepTrfNulo = 1) e (VsOrigem = "F210TPA"))
        nFilTrf = nFilDep;

    @ 4.2) obtém filial do depósito de transferência se informado @
    Se (nDepTrfNulo = 0)
    Inicio
        TSql = "SELECT CODFIL WWCodFil FROM E205DEP \
                 WHERE CODEMP = :VSCODEMP  \
                   AND CODDEP = :VSDEPTRF";
        SQL_Criar(xCur);
        SQL_DefinirComando(xCur, TSql);
        SQL_DefinirInteiro(xCur, "VSCODEMP", VSCODEMP);
        SQL_DefinirAlfa   (xCur, "VSDEPTRF", VSDEPTRF);
        SQL_AbrirCursor(xCur);
        Se (SQL_EOF(xCur) = 0)
        {
            SQL_RetornarInteiro(xCur, "WWCodFil", nFilTrf);
        }
        SQL_Destruir(xCur);
    Fim;

    @ 4.3) sem depósito destino ou filial diferente -> bloqueia @
    Se (nFilTrf <> nFilDep)
    Inicio
        IntParaAlfa(nFilDep, aFilDep);
        aMsg = "Movimentação SEM Nota Fiscal não permitida para depósitos da filial " + aFilDep +
           ". Permitido APENAS para inventário (90205/90255) ou transferência entre depósitos da MESMA filial.";
        Mensagem(Erro, aMsg);
    Fim;
Fim;
@------------------------------------------------------------------------------@
@=================================================================================================================================================@
@========== Fazer a movimentação para os depósitos virtuais no momento que é feito uma Nota fiscal de consignado. ds.ronaldo 18/05/2023 ==========@
@ 08/11/2024 - ECC - Inativação colocado processo padrão de transferencia @
@=================================================================================================================================================@
/*
Definir Alfa aEstCoc;
Definir Alfa aCodTns;
Definir Alfa aCodCli;
Definir Alfa aCodFor;
Definir Alfa aCodEmp;
Definir Alfa aCodFil;
Definir Alfa aCodDep;
Definir Alfa aDatMov;
Definir Alfa aQtdMov;
Definir Alfa aVlrMov;
Definir Alfa aNumDoc;
Definir Alfa VSCodTns;
Definir interno.com.senior.g5.co.mcm.est.estoques.MovimentarEstoque VMovEst;
Definir Alfa aMsg;
Definir Numero VSCodEmp;
Definir Numero VSCodCli;
Definir Numero VSCodFor;
Definir Alfa VSCodPro;
Definir Alfa VSCodDer;
Definir Alfa VSCODLOT;
Definir Alfa VaSeqMov;
Definir Alfa VSEstEos;
Definir Cursor CurConsig;
Definir Cursor CurGer;
Definir Numero VSNUMNFC;
Definir Alfa VSSNFNFC;
Definir Numero VSSEQIPC;
Definir Numero VSNumNfv;
Definir Alfa VSCodSnf;
Definir Numero VSSEQIPV;
Definir Data VSDatMov;
Definir Numero VnSeqMov;

CurConsig.SQL "Select EstCoc from E001TNS Where CodEmp = :VSCodEmp AND \
                                                CodTns = :VSCodTns"
CurConsig.AbrirCursor();
Se(CurConsig.Achou)
  aEstCoc = CurConsig.EstCoc;
CurConsig.FecharCursor();

Se ((aEstCoc = "S") e ((VSCodCli = 4419) ou (VSCodCli = 9736)))
Inicio
  IntParaAlfa(VSCodEmp, aCodEmp);
  IntParaAlfa(VSCodFil, aCodFil);
  IntParaAlfa(VSVLRMOV, aVlrMov);
  ConverteMascara(3,VSDATMOV,aDatMov,"DD/MM/YYYY");
  ConverteMascara(2,VSQTDMOV,aQtdMov,"ZZZZZZZZ9,99999");

  aCodDep = "";

  CurGer.SQL "SELECT E205DEP.CODDEP FROM E205DEP, E085CLI WHERE E205DEP.USU_CODROE = E085CLI.CODROE AND        \
                                                                               E205DEP.CODEMP = :VSCODEMP AND  \
                                                                               E205DEP.CODFIL = :VSCODFIL AND  \
                                                                               E085CLI.CODCLI = :VSCodCli";
  CurGer.AbrirCursor();
  Se (CurGer.Achou)
    aCodDep = CurGer.CODDEP;
  CurGer.FecharCursor();

  Se(aCodDep <= " ")
  {
    IntParaStr(VSCodCli,aCodCli);
    IntParaStr(VSCodFor,aCodFor);
    aMsg = "Consignado para Cliente " + aCodCli + "/ Fornecedor " + aCodFor + " sem depósito virtual definido!!!";
    GeraLog(aMsg);
  }

  VMovEst.dadosGerais.codEmp = aCodEmp;
  VMovEst.dadosGerais.codFil = aCodFil;
  VMovEst.dadosGerais.codPro = VSCodPro; @ String	(Obrigatório) - String(014) - Produto @
  VMovEst.dadosGerais.codDer = VSCODDER; @ String	(Obrigatório) - String(007) - Derivação @
  VMovEst.dadosGerais.codDep = aCodDep; @ String	(Obrigatório) - String(010) - Depósito @

  Se(VSEstEos = "S")
  {
    aCodTns = "9020V";
    IntParaStr(VSNumNfv,aNumDoc);
  }
  Se(VSEstEos = "E")
  {
    aCodTns = "9025V";
    IntParaStr(VSNumNfc,aNumDoc);
  }

  VMovEst.dadosGerais.NumDoc = aNumDoc;
  VMovEst.dadosGerais.codTns = aCodTns; @ String	(Obrigatório) - String(005) - Transação @
  VMovEst.dadosGerais.qtdMov = aQtdMov; @ String	(Opcional) - Number(014) - Quantidade do Movimento @
  VMovEst.dadosGerais.vlrMov = aVlrMov;
  VMovEst.dadosGerais.datMov = aDatMov; @ String	(Opcional) - Date(DD/MM/AAAA) - Data do Movimento @
  VMovEst.dadosGerais.codLot = VSCODLOT; @ String	(Opcional) - String(050) - Lote de Fabricação @

  Definir Alfa aRetorno;
  VMovEst.ModoExecucao = 1;
  VMovEst.Executar();
  aRetorno = VMovEst.retornoMovimento.retorno;
  VaSeqMov = VMovEst.retornoMovimento.seqMov;
  AlfaParaInt(VaSeqMov, VnSeqMov);
  Se (aRetorno = "OK")
  inicio
     ExecSql "Update E210MVP          \
              Set FilNfc = :VSCodFil, \
              CodFor = :VsCodFor,     \
              NumNfc = :VSNUMNFC,     \
              SnfNfc = :VSSNFNFC,     \
              SeqIpc = :VSSEQIPC,     \
              NUMNFV = :VSNumNfv,     \
              CODSNF = :VSCodSnf,     \
              SEQIPV = :VSSEQIPV,     \
              CODCLI = :VSCodCli      \
        Where CodEmp = :VSCodEmp      \
          And CodPro = :VSCodPro      \
          And CodDer = :VSCodDer      \
          And CodDep = :aCodDep       \
          And DatMov = :VSDatMov      \
          And SeqMov = :VnSeqMov";
  Fim;
  Senao
    Inicio
      aRetorno = VSCodPro + "-" + VSCodDer + " Dep. " + aCodDep + " - " + aRetorno;
      GeraLog(aRetorno);
    Fim;
Fim;
*/
@=================================================================================================================================================@
@=================================================================================================================================================@



 /*
Se ((VSCODFOR = 10152) e (VSCODTNS = "90216"))
inicio

  IntParaAlfa(1, VaCodEmp);
  IntParaAlfa(1, VaCodFil);
  ConverteMascara(3,VSDATMOV,VaDatMov,"DD/MM/YYYY");
  IntParaAlfa(VsCodFor, VaCodFor);
  IntParaAlfa(VSNUMNFC, VaNumDoc);
  ConverteMascara(2,VSQTDMOV,VaQtdMov,"ZZZZZZZZ9,99999");
  IntParaAlfa(VnSeqIpc, VaSeqIpc);
  VaCodDep = "02.00";
  VaCodFil = "2";
  VMovEst.dadosGerais.codEmp = VaCodEmp;
  VMovEst.dadosGerais.codFil = VaCodFil;
  VMovEst.dadosGerais.codPro = VSCodPro; @ String	(Obrigatório) - String(014) - Produto @
  VMovEst.dadosGerais.codDer = VSCODDER; @ String	(Obrigatório) - String(007) - Derivação @
  VMovEst.dadosGerais.codDep = VaCodDep; @ String	(Obrigatório) - String(010) - Depósito @
  VMovEst.dadosGerais.codTns = "90256"; @ String	(Obrigatório) - String(005) - Transação @
  VMovEst.dadosGerais.qtdMov = VaQtdMov; @ String	(Opcional) - Number(014) - Quantidade do Movimento @
  VMovEst.dadosGerais.datMov = VaDatMov; @ String	(Opcional) - Date(DD/MM/AAAA) - Data do Movimento @
  VMovEst.dadosGerais.codFor = VaCodFor; @ String	(Opcional) - Number(009) - Código do Fornecedor @
  VMovEst.dadosGerais.numDoc = VaNumDoc; @ String	(Opcional) - Number(009) - Número do Documento @
  VMovEst.dadosGerais.CodSnf = VSSNFNFC; @ String	(Opcional) - String(003) - Código da série da nota fiscal de entrada @
  VMovEst.dadosGerais.motMvp = "Ajuste via regra (104) CDBR470";
  VMovEst.dadosGerais.codLot = VSCODLOT; @ String	(Opcional) - String(050) - Lote de Fabricação @

  Definir Alfa aRetorno;
  VMovEst.ModoExecucao = 1;
  VMovEst.Executar();
  aRetorno = VMovEst.retornoMovimento.retorno;
  VaSeqMov = VMovEst.retornoMovimento.seqMov;
  AlfaParaInt(VaSeqMov, VnSeqMov);
  Se (aRetorno = "OK")
  inicio
     ExecSql "Update E210MVP \
              Set FilNfc =  1, \
               CodFor = :VsCodFor, \
               NumNfc = :VSNUMNFC, \
               SnfNfc = :VSSNFNFC, \
               SeqIpc = :VSSEQIPC \
         Where CodEmp = :VSCodEmp \
           And CodPro = :VSCodPro \
           And CodDer = :VSCodDer \
           And CodDep = :VaCodDep \
           And DatMov = :VSDatMov \
           And SeqMov = :VnSeqMov";
  Fim;
  Senao
     GeraLog(aRetorno);

Fim; */


EstaNulo(VSDepTrf,nRet);
/*
 - 21/07/2025 - DGF (manutenção) - Liberado usuario 726 - djonatan.elias - chamado GLPI 37965;
 - 06/08/2025 - IVM (manutenção) - Liberado usuario 1142 - patrique.araujo - chamado GLPI 38411;
*/
Se((VSCodDep = "OP.01") e (nRet = 0) e (VSDepTrf <> "AV.DM") e (CodUsu <> 1058) e (CodUsu <> 1142))
  GeraLog("Transferência permitida apenas para o depósito AV.DM");

Se((VSCodDep = "AV.DM") e (nRet = 0) e (VSDepTrf <> "OP.01") e (CodUsu <> 1142) e (CodUsu <> 1058))
  GeraLog("Transferência permitida apenas para o depósito 01.DM");

Se((VSCodDep = "01.CD") e (nRet = 0) e (VSDepTrf <> "AV.CD") e (CodUsu <> 1142) e (CodUsu <> 1058))
  GeraLog("Transferência permitida apenas para o depósito AV.CD");

Se((VSCodDep = "AV.CD") e (nRet = 0) e (VSDepTrf <> "01.CD") e (CodUsu <> 1142) e (CodUsu <> 1058))
  GeraLog("Transferência permitida apenas para o depósito 01.CD");

/*
Se((VSCodDep = "03.00") e (nRet = 0) e (VSDepTrf <> "AV.SP"))
  GeraLog("Transferência permitida apenas para o depósito AV.SP");
*/

Se((VSCodDep = "AV.SP") e (nRet = 0) e (VSDepTrf <> "03.00"))
  GeraLog("Transferência permitida apenas para o depósito 03.00");

/*
- Consistência na tranferência de quando informado OP, na tela F210TPA - chamado 14384;
- 17/07/2020 - ARF (implantação);
- 04/08/2020 - ARF (liberado);
- 30/08/2024 - ARF (liberação) - Autorizado pela Glaucia o usuário do Pither (404) fazer a movimentação - Chamado 22008;
*/
EstaNulo(VSMotMvp,VRetObs);
Se ((VSCodEmp = 1) e (VSOrigem = "F210TPA") e (ESTNNumDoc = 0) e (VRetObs = 1) e (codusu <> 307) e (codusu <> 308) e (codusu <> 420) e (codusu <> 404) e (codusu <> 1077))
  Geralog("Transferência sem OP, informar observação!");

Definir Cursor CurE001TNS;
Definir Numero VSCODEMP;
Definir Numero vNumOrp;
@Definir Alfa VSNumDoc;@
Definir Alfa VSCODTNS;
Definir Alfa VSCODPRO;
Definir Alfa VSOrigem;
Definir Alfa vMensagem;
Definir Alfa vManual;
Definir Alfa vCodOri;
Definir Alfa VSESTADO;
Definir Alfa   VSOriOrp;
Definir Alfa VSCODDEP;
Definir Numero EstNNumDoc;
Definir Alfa   VSCODLOT; @ ALFA	Código do Lote de fabricação	N @
Definir Data VSDATMOV;
Definir Alfa vMensagem;
LimpaEspacos(VSOriOrp);

Definir cursor CurE075PRO;

/*
- 19/12/2024 0 IVM (liberação) - Liberado usuário do Pither(404) para baixar componente - Chamado 27610;

*/
Se ((VSOriOrp <> "") E (EstNNumDoc > 0) e (VSCODDEP = "01.03") e (Codusu <> 173) e (Codusu <> 404)){
  vMensagem = "Você não tem permisão para baixar o componente " + VSCODPRO + " no deposito 01.03";
  Geralog(vMensagem);
  }

Se ((VSNUMNFV <> 0) e (VSCODDEP = "01.03"))
   GeraLog("Você não pode baixar no 01.03, favor selecionar outro deposito");

Se ((VSOriOrp <> "") E (EstNNumDoc > 0) e (VSOriOrp <> "200") e (codusu <> 307))
{
  @ Checagem para impedir movimentar lote padrão (Claudio e Elisa - 16/09/2019) @
  Definir Alfa aLotPad;
  CurE075PRO.SQL "SELECT E083ORI.LOTPAD FROM E075PRO,E083ORI \
                   WHERE E083ORI.CODEMP = E075PRO.CODEMP AND E083ORI.CODORI = E075PRO.CODORI AND \
                     E075PRO.CodEmp=:VSCODEMP AND E075PRO.CodPro=:VSCODPRO";
  CurE075PRO.ABRIRCURSOR();
  Se (CurE075PRO.ACHOU)
    aLotPad = CurE075PRO.LOTPAD;
  CurE075PRO.FECHARCURSOR();
  Se ((aLotPad <> " ") E (aLotPad = VSCODLOT))
  {
    vMensagem = "Verifique: Lote padrão do produto " + VSCODPRO + " não pode ser baixado do estoque para consumo em OPs.";
    Geralog(vMensagem);
  }


  @ Checagem para impedir baixar componentes fora do período de movimentação da OP (Claudio e Elisa - 16/09/2019) @
  Definir Alfa   TClaSql;
  Definir Alfa  x075PRO;
  Definir Data dDtrIni;
  Definir Data dDtrFim;
  Definir Alfa aDtrFim;
  Definir Alfa aDtrIni;
  Definir Alfa aDATMOV;
  Definir Alfa amsg;
  Definir Alfa vSitOrp;
  Definir Data VdDtrFimOP;

  @-- Buscar a data inicio e fim da OP --@
  Definir Cursor Cur_E900COP;
  Cur_E900COP.Sql "Select DtrIni,DtrFim,SitOrp from E900COP where \
                   CodEmp=:VSCODEMP and \
                   CodOri=:VSOriOrp and \
                   NumOrp=:EstNNumDoc";
  Cur_E900COP.AbrirCursor();
  Se(Cur_E900COP.Achou)
  Inicio
    vSitOrp=Cur_E900COP.SitOrp;
    VdDtrFimOP = Cur_E900COP.DtrFim; @ Data final da OP @
  Fim;
  Cur_E900COP.FecharCursor();

  TClaSql = "Select Max(DatRea) WWDtrFim, Min(DatRea) WWDtrIni from E900EOQ where \
             CODEMP=:VSCODEMP AND CODORI=:VSOriOrp AND NUMORP=:EstNNumDoc and CodTns = '90201'";
  SQL_Criar(x075PRO);
  SQL_DefinirComando(x075PRO, TClaSql);
  SQL_DefinirInteiro(x075PRO,"VSCODEMP",VSCODEMP);
  SQL_DefinirInteiro(x075PRO,"EstNNumDoc",EstNNumDoc);
  SQL_DefinirAlfa(x075PRO,"VSOriOrp",VSOriOrp);
  SQL_AbrirCursor(x075PRO);
  Se (SQL_EOF(x075PRO) = 0)
    {
      SQL_RetornarData(x075PRO,"WWDtrFim",dDtrFim);
      SQL_RetornarData(x075PRO,"WWDtrIni",dDtrIni);
      /*DesMontaData(dDtrIni,vDia, vMes, vAno);
      MontaData(1, vMes, vAno, nDtrIni);  */
      @Se (vSitOrp <> "F")@
       @  dDtrFim = VSDATMOV;@

      UltimoDia(dDtrFim);
      Se (VSOriOrp = "510")
         dDtrFim = VSDATMOV;

      ConverteMascara (3,dDtrFim,aDtrFim,"DD/MM/YYYY");
      ConverteMascara (3,dDtrIni,aDtrIni,"DD/MM/YYYY");
      ConverteMascara (3,VSDATMOV,aDATMOV,"DD/MM/YYYY");

      Se ((VSCodTns <> "90201") e (VSORIORP <> "") e (VSDATMOV > dDtrFim))
        {
          SQL_Destruir(x075PRO);
          amsg = "Verifique: data da baixa dos componentes da OP precisa ser entre a data de início e fim da OP(" + aDtrFim + ")!";
          GeraLog(amsg);
        }
    }
  SQL_Destruir(x075PRO);
  /*CurE075PRO.SQL "Select max(datrea), min(datrea) from E900Eoq where \
                     CODEMP=:VSCODEMP AND CODORI=:VSOriOrp AND NUMORP=:EstNNumDoc and qtdre1 <> 0 and codtns = '90201'";
  CurE075PRO.ABRIRCURSOR();
  Se (CurE075PRO.ACHOU)
  {
    Definir Data dDtrIni;
    Definir Data dDtrFim;
    dDtrIni = CurE075PRO.DtrIni;
    dDtrFim = CurE075PRO.DtrFim;
    UltimoDia (dDtrFim);
    Se ((VSDATMOV < dDtrIni) OU (VSDATMOV > dDtrFim))
    {
      CurE075PRO.FecharCursor();
      GeraLog("Verifique: data da baixa dos componentes da OP precisa ser entre a data de início e fim da OP!");
    }
    CurE075PRO.FecharCursor();
  }
  CurE075PRO.FECHARCURSOR();  */
}

CurE075PRO.SQL "SELECT E075Pro.ClaPro \
                  FROM E075PRO \
                 WHERE E075PRO.CodEmp=:VSCODEMP \
                   AND E075PRO.CodPro=:VSCODPRO \
                   AND E075PRO.ClaPro NOT IN (2)";
CurE075PRO.ABRIRCURSOR();
SE (CurE075PRO.ACHOU)
Inicio
  CurE001TNS.SQL "SELECT E001TNS.AceMan \
                    FROM E001TNS \
                   WHERE E001TNS.CodEmp=:VSCODEMP \
                     AND E001TNS.CodTns=:VSCODTNS \
                     AND E001TNS.AceMan IN ('S')";
  CurE001TNS.AbrirCursor();
  SE (CurE001TNS.Achou)
  Inicio
    vManual = "S";
  Fim;
  CurE001TNS.FecharCursor();

Fim;
CurE075PRO.FECHARCURSOR();

/******** VERIFICA A CONTA CONTABIL QUE ESTA SENDO USADA NO MOVIMENTO DE BAIXA DO PRODUTO ********************/

Definir Numero VSCtaRed; @ NÚMERO Cta. Contabil N @

Se ((VSCtaRed = 1206) ou (VSCtaRed = 1208) ou (VSCtaRed = 1207) ou (VSCtaRed = 1202) ou
    (VSCtaRed = 1223) ou (VSCtaRed = 1202) ou (VSCtaRed = 1223) ou (VSCtaRed = 1223) ou
    (VSCtaRed = 1222) ou (VSCtaRed = 1222) ou (VSCtaRed = 1222) @ou (VSCtaRed = 1222)@ ou
    (VSCtaRed = 1222) ou (VSCtaRed = 1222) ou (VSCtaRed = 1222) ou (VSCtaRed = 1222))

    Inicio
      Se ((VSCodPro <> "80020117") e (VSESTADO <> "EXCLUINDO"))    @ Adicionado exceção para o código 80020117, conforme chamado 4315@
         GeraLog("ATENÇÃO: Favor informar Outra Conta Contábil, de DESPESA!");
    Fim;


@ Parâmetro para apresentar o relatório de Controle de Entrada Expedição, no final do apontamento - 25/09/2012 - Rodrigo Costa@
Se ((GerTabNum[3] = 1) e ((CodUsu = 70) ou (CodUsu = 301) ou (CodUsu = 274)))
  Inicio
    SetaAlfaTelaEntrada("ECodOri",VSOriOrp);
    SetaNumeroTelaEntrada("ENumOrp",EstNNumDoc);
    @ExecutaRelatorio("MCAP105.GER","N","");@
    GerTabNum[3] = 0;
    GerTabAlf[4] = "";
    GerTabNum[2] = 0;
 Fim;
@ Fim - Parâmetro para apresentar o relatório de Controle de Entrada Expedição.@


Definir Cursor CurE001TNS;
Definir Numero VSCODEMP;
Definir Numero VSCODFIL;
Definir Numero vNumOrp;
@Definir Alfa VSNumDoc;@
Definir Alfa VSCODTNS;
Definir Alfa VSCODPRO;
Definir Alfa VSOrigem;
Definir Alfa vMensagem;
Definir Alfa vManual;
Definir Alfa vCodOri;
/*
vNumOrp = GerTabNum[2];
Se (vNumOrp <> 0)
  IntParaAlfa(vNumOrp, VSNumDoc);
*/
Definir cursor CurE075PRO;
CurE075PRO.SQL "SELECT E075Pro.ClaPro \
                  FROM E075PRO \
                 WHERE E075PRO.CodEmp=:VSCODEMP \
                   AND E075PRO.CodPro=:VSCODPRO \
                   AND E075PRO.ClaPro NOT IN (2)";
CurE075PRO.ABRIRCURSOR();
SE (CurE075PRO.ACHOU)
Inicio
  CurE001TNS.SQL "SELECT E001TNS.AceMan \
                    FROM E001TNS \
                   WHERE E001TNS.CodEmp=:VSCODEMP \
                     AND E001TNS.CodTns=:VSCODTNS \
                     AND E001TNS.AceMan IN ('S')";
  CurE001TNS.AbrirCursor();
  SE (CurE001TNS.Achou)
  Inicio
    vManual = "S";
  Fim;
  CurE001TNS.FecharCursor();

Fim;
CurE075PRO.FECHARCURSOR();

/******** VERIFICA A CONTA CONTABIL QUE ESTA SENDO USADA NO MOVIMENTO DE BAIXA DO PRODUTO ********************/

Definir Numero VSCtaRed; @ NÚMERO Cta. Contabil N @

Se ((VSCtaRed = 1206) ou (VSCtaRed = 1208) ou (VSCtaRed = 1207) ou (VSCtaRed = 1202) ou
    (VSCtaRed = 1223) ou (VSCtaRed = 1202) ou (VSCtaRed = 1223) ou (VSCtaRed = 1223) ou
    (VSCtaRed = 1222) ou (VSCtaRed = 1222) ou (VSCtaRed = 1222) @ou (VSCtaRed = 1222)@ ou
    (VSCtaRed = 1222) ou (VSCtaRed = 1222) ou (VSCtaRed = 1222) ou (VSCtaRed = 1222))

    Inicio
      Se (VSCodPro <> "80020117")     @ Adicionado exceção para o código 80020117, conforme chamado 4315@
        x=1;
      @   GeraLog("ATENÇÃO: Favor informar Outra Conta Contábil, de DESPESA!");  @
    Fim;

/*
- Consistência da data do movimento no estoque < que a data inicial do estoque e também consisti a data do movimento no estoque estiver fora do período de início e fim da OP. Regra desenvolvida pelo Fernando - Datasig - Chamado 6032/33545;
- 22/06/2017 - ARF (liberação);
- 03/07/2017 - ARF (manutenção) - Alterado a lógica para consistir apenas pela data do período do estoque, para apontamento em OPs, abertas ou liquidadas - chamado 6270.
- 01/02/2018 - ECC (manutenção) - Não permitir apontamento de produto de terceiro - Chamado 7324;
- 30/03/2023 - ARF (manutenção) - Desativado a consistência sobre o bloqueio no apontamento de produto de terceiros - chamado GLPI 3300;
*/
@-- Consistir movimento de baixa de componentes de OPS - 15/05/2017 --@
Definir Numero VSCODEMP;
Definir Numero VSCODFIL;
Definir Alfa VSORIORP;
Definir Numero ESTNNUMDOC;

Definir Alfa ANumOrp;
Definir Alfa ARetorno;
Definir Data vDtrIni;
Definir Data vDtrFim;
Definir Data vEstPdi;
Definir Alfa aDtrIni;
Definir Alfa aDtrFim;
Definir Alfa aEstPdi;
Definir Alfa vSitOrp;
Definir Alfa xOriOrp;
Definir Alfa ChaACodDer;
Definir Alfa ChaACodCmp;

xCodEmp=VSCODEMP;
xCodFil=VSCODFIL;
xOriOrp=VSORIORP;
xNumOrp=ESTNNUMDOC;
LimpaEspacos(VSORIORP);

Se( (xCodEmp=1) e (VSORIORP <> "") e (codusu <> 307) e (codusu <> 660) e (codusu <> 331))
Inicio
  @-- Buscar a data do período da filial --@
  Definir Cursor Cur_E070FIL;
  Cur_E070FIL.Sql "Select EstPdi from E070FIL where \
                   CodEmp=:VSCODEMP and \
                   CodFil=:VSCODFIL";
  Cur_E070FIL.AbrirCursor();
  Se(Cur_E070FIL.Achou)
  Inicio
    vEstPdi=Cur_E070FIL.EstPdi;
    ConverteMascara(3,vEstPdi,aEstPdi,"DD/MM/YYYY");
  Fim;
  Cur_E070FIL.FecharCursor();

  @-- Buscar a data inicio e fim da OP --@
  Definir Cursor Cur_E900COP;
  Cur_E900COP.Sql "Select DtrIni,DtrFim,SitOrp from E900COP where \
                   CodEmp=:xCodEmp and \
                   CodOri=:xOriOrp and \
                   NumOrp=:xNumOrp";
  Cur_E900COP.AbrirCursor();
  Se(Cur_E900COP.Achou)
  Inicio
    vDtrIni=Cur_E900COP.DtrIni;
    ConverteMascara(3,vDtrIni,aDtrIni,"DD/MM/YYYY");
    vDtrFim=Cur_E900COP.DtrFim;
    UltimoDia(vDtrFim);
    ConverteMascara(3,vDtrFim,aDtrFim,"DD/MM/YYYY");
    vSitOrp=Cur_E900COP.SitOrp;
  Fim;
  Cur_E900COP.FecharCursor();
  /*
  @ Não permite Apontar produtos de terceiros @
  Definir Alfa VaCodFam;
  Definir Alfa TClaSql;
  Definir Alfa CBusPro;
  TClaSql = "SELECT E075PRO.CodFam VaCodFam \
               FROM E075PRO \
              WHERE E075PRO.CodEmp=:VSCODEMP \
                AND E075PRO.CodPro=:VSCODPRO";
  SQL_Criar(CBusPro);
  SQL_DefinirComando(CBusPro, TClaSql);
  SQL_DefinirInteiro(CBusPro,"VSCODEMP",VSCODEMP);
  SQL_DefinirAlfa(CBusPro,"VSCODPRO",VSCODPRO);
  SQL_AbrirCursor(CBusPro);
  Se (SQL_EOF(CBusPro) = 0)
    {
      SQL_RetornarAlfa(CBusPro,"VaCodFam",VaCodFam);
    }
  SQL_Destruir(CBusPro);
  @ Familias de produto de terceiros @
  Se (VaCodFam = "7551") @ Papelão Higienico @
  VLisBol = 1;
   Senao
     Se (VaCodFam = "7552") @ Papelão Rolinho @
       VLisBol = 1;
      Senao
        Se (VaCodFam = "7553") @ Papelão Lencol / Grampo @
          VLisBol = 1;
         Senao
           Se (VaCodFam = "7554") @ Papelão Interfolhado @
             VLisBol = 1;
            Senao
              Se (VaCodFam = "7555") @ Papelão Fardo @
                VLisBol = 1;
               Senao
                 Se (VaCodFam = "7556") @ Saco Tubo @
                   VLisBol = 1;
                  Senao
                    Se (VaCodFam = "7557") @ Saco Fardo @
                      VLisBol = 1;
                     Senao
                       Se (VaCodFam = "7558") @ Fitas Adesivas@
                         VLisBol = 1;
                       Senao
                         Se (VaCodFam = "7559") @ Elasticos e Bobinas Filmes / Pvc @
                           VLisBol = 1;
                           Senao
                             Se (VaCodFam = "7659") @ Elasticos e Bobinas Filmes / Pvc @
                               VLisBol = 1;
                              Senao
                                VLisBol = 0;
  Se (VLisBol = 1)
  inicio
    ARetorno = "Componente " + VSCODPRO + ": Movimentação cancelada. Produto de Terceiro não pode ser apontado!.";
    GeraLog(ARetorno);
  Fim; */

  Se ((VSDatMov < vDtrIni) e (codusu <> 331))
     GeraLog("Data de apontamento inferior a data inicial da OP, verifique!!!");  @ data de apontamento menor que a data inicial da OP, não permitido @

  Se ((VSDatMov > vDtrFim) e (vDtrFim <> 0) e (Codusu <> 660) e (Codusu <> 307) e (codusu <> 331) e (codusu <> 474)){
     ConverteMascara(3,vDtrFim,aDtrFim,"DD/MM/YYYY");
     ConverteMascara(3,VSDATMOV,aDatMov,"DD/MM/YYYY");
     ARetorno = "Data de apontamento:" + aDatMov + " superior a data final ("+ aDtrFim +") da OP, verifique!!!";  @ data de apontamento maior que a data final da OP, não permitido @
     GeraLog(ARetorno); @ data de apontamento maior que a data final da OP, não permitido @
     }

Fim;

Se(((vSitOrp="A") Ou (vSitOrp="F")) e (codusu <> 307) e (codusu <> 660) e (codusu <> 331))
{
  Se(VSDATMOV < vEstPdi) @ Data movimento da OP MENOR que Data inicial do período, então trava. @
  Inicio
    Se((ChaACodDer=" ") ou (ChaACodDer=" "))
    ARetorno = "Componente " + ChaACodCmp + ": Movimentação cancelada. A baixa está dentro de um período fechado.";
    Senao
    ARetorno = "Componente " + ChaACodCmp + "/" + ChaACodDer + ": Movimentação cancelada. A baixa está dentro de um período fechado.";

    GeraLog(ARetorno);
  Fim;
}
/*
Se(vSitOrp="A")   @ INATIVADO conforme acima - chamado 6270 @
{
  Se(VSDATMOV < vEstPdi) @ Data movimento da OP MENOR que Data inicial do período, então trava. @
  Inicio
    Se((ChaACodDer=" ") ou (ChaACodDer=" "))
    ARetorno = "Componente " + ChaACodCmp + ": Movimentação cancelada. A baixa está dentro de um período fechado.";
    Senao
    ARetorno = "Componente " + ChaACodCmp + "/" + ChaACodDer + ": Movimentação cancelada. A baixa está dentro de um período fechado.";

    GeraLog(ARetorno);
  Fim;
};
Se(vSitOrp="F")
{
  Se( (VSDATMOV < vDtrIni) ou (VSDATMOV > vDtrFim) ) @ Data movimento da OP MENOR que Data inicial do período, então trava. @
  Inicio
    Se((ChaACodDer="") ou (ChaACodDer=" "))
    ARetorno = "Componente " + ChaACodCmp + ": Movimentação cancelada. OP " + ANumOrp + " finalizada em " + aDtrFim + " e movimento está dentro de um período fechado.";
    Senao
    ARetorno = "Componente " + ChaACodCmp + "/" + ChaACodDer + ": Movimentação cancelada. OP " + ANumOrp + " finalizada em " + aDtrFim + " e movimento está dentro de um período fechado.";

    GeraLog(ARetorno);
  Fim;
};
*/
@-- Fim --@


/*
- Controle da data de apontamento na OP, somente durante o período "aberta" da mesma - chamado 6617/7168;
- 09/01/2018 - ARF (implantação);
- 20/02/2018 - ARF (liberação) - às 09:35;
- 14/03/2018 - ARF (manutenção) - Consistir o produto apontado X produto acabado da OP, somente permtir apontamento para componentes - chamado 7623;
*/
Definir Numero VSCODEMP; @ NÚMERO	Código da empresa	N @
Definir Alfa   VSCODPRO; @ ALFA	Código do produto	N @
Definir Alfa   VSCODDER; @ ALFA	Código da derivação	N @
Definir Alfa   VSCODDEP; @ ALFA	Código do depósito	N @
Definir Data   VSDATMOV; @ DATA	Data do Movimento	N @
Definir Numero VSSEQMOV; @ NÚMERO	Sequência do movimento	N @
Definir Alfa   VSCODTNS; @ ALFA	Código da transação	N @
Definir Alfa   VSESTMOV; @ ALFA	Tipo de estoque movimentado	N @
Definir Alfa   VSESTEOS; @ ALFA	Entrada ou Saída	N @
Definir Data   VSDATFAB; @ DATA	Data de fabricação	N @
Definir Data   VSDATVLT; @ DATA	Data de validade do lote de fabricação	N @
Definir Alfa   VSNUMSEP; @ ALFA	Número de Série do Produto	N @
@Definir Numero VSNUMDOC;@ @ NÚMERO	Número do Documento	N @
Definir Alfa   VSOBSMVP; @ ALFA	Observação para uso exclusivo do processo de fechamento dos estoques	N @
Definir Numero VSQTDMOV; @ NÚMERO	Quantidade do movimento	N @
Definir Numero VSVLRMOV; @ NÚMERO	Valor do movimento	N @
Definir Alfa   VSPROTRF; @ ALFA	Produto transferido	N @
Definir Alfa   VSDERTRF; @ ALFA	Derivação transferida	N @
Definir Alfa   VSDEPTRF; @ ALFA	Depósito transferido	N @
Definir Numero VSQTDANT; @ NÚMERO	Quantidade anterior	N @
Definir Numero VSVLRANT; @ NÚMERO	Valor anterior	N @
Definir Numero VSCODFIL; @ NÚMERO	Código da filial da nota fiscal de saída	N @
Definir Alfa   VSCODSNF; @ ALFA	Código da série da nota fiscal de saída	N @
Definir Numero VSNUMNFV; @ NÚMERO	Número da nota fiscal de saída	N @
Definir Numero VSSEQIPV; @ NÚMERO	Sequência da nota fiscal de saída	N @
Definir Numero VSCODCLI; @ NÚMERO	Código do Cliente	N @
Definir Numero VSFILNFC; @ NÚMERO	Código da filial da nota fiscal de entrada	N @
Definir Numero VSNUMNFC; @ NÚMERO	Número da nota fiscal de entrada	N @
Definir Numero VSCODFOR; @ NÚMERO	Código do fornecedor	N @
Definir Numero VSSEQIPC; @ NÚMERO	Sequência da nota fiscal de entrada	N @
Definir Numero VSNUMEME; @ NÚMERO	Número da requisição	N @
Definir Alfa   VSSNFNFC; @ ALFA	Série da Nota Fiscal de Entrada	N @
Definir Numero VSSEQEME; @ NÚMERO	Sequência da requisição	N @
Definir Numero VSUSURES; @ NÚMERO	Usuário responsável	N @
Definir Numero VSCTARED; @ NÚMERO	Conta reduzida	N @
Definir Numero VSCTAFIN; @ NÚMERO	Conta financeira	N @
Definir Alfa   VSLCTFIN; @ ALFA	Indicativo se o movimento foi lançado no plano financeiro	N @
Definir Numero VSNUMLOT; @ NÚMERO	Número do lote contábil	N @
Definir Numero VSUSUDIG; @ NÚMERO	Usuário da digitação	N @
Definir Data   VSDATDIG; @ DATA	Data da digitação	N @
Definir Numero VSHORDIG; @ NÚMERO	Horário da digitação	N @
Definir Numero VSNUMPRJ; @ NÚMERO	Número interno do projeto	N @
Definir Numero VSCODFPJ; @ NÚMERO	Código da fase do projeto	N @
Definir Alfa   VSMOTMVP; @ ALFA	Observação do movimento de estoque (uso geral)	N @
Definir Alfa   VSORIGEM; @ ALFA	Tela origem de chamada da regra	N @
Definir Numero ESTNNUMDOC; @ NÚMERO	Número do Documento	N @
Definir Alfa   VSCODORI; @ ALFA	Código da Origem do Produto	N @
Definir Alfa   VSESTADO; @ ALFA	Estado da movimentação(INSERINDO ou EXCLUINDO)	NVSCODEMP	NÚMERO	Código da empresa	N @
Definir Alfa   TClaSql;
Definir Alfa   CCurFil;
Definir Alfa   CCurCop;
Definir Alfa   VSOriOrp;
Definir Alfa   VSitOrp;
Definir Alfa   VProOrp;
Definir Data   VEstPdi;
Definir Data   VDatIni;
Definir Data   VDatFim;
VSNumOrp = EstnNumDoc;
EstaNulo(VSOriOrp,VRetOrp);
/*
liberada e andamento, consiste data inicio
finalizada, somente dentro do mes da ultima data
*/

Se ((VSCodEmp = 1) e (VRetOrp = 0) e (codusu <> 331))
  { @ busca o período inicial do período do estoque - Tela F070FES @
    TClaSql = "Select E070FIL.EstPdi WWEstPdi \
                 From E070FIL \
                Where E070FIL.CodEmp = :VSCodEmp \
                  And E070FIL.CodFil = :VSCodFil";
    SQL_Criar(CCurFil);
    SQL_DefinirComando(CCurFil, TClaSql);
    SQL_DefinirInteiro(CCurFil,"VSCodEmp",VSCodEmp);
    SQL_DefinirInteiro(CCurFil,"VSCodFil",VSCodFil);
    SQL_AbrirCursor(CCurFil);
    Se (SQL_EOF(CCurFil) = 0)
      {
        SQL_RetornarData(CCurFil,"WWEstPdi",VEstPdi);
      }
    SQL_Destruir(CCurFil);

    @ busca o período inicial e situação da OP @
    TClaSql = "Select E900COP.DtrIni WWDtrIni, E900COP.DtrFim WWDtrFim, \
                      E900COP.SitOrp WWSitOrp, E900COP.CodPro WWProOrp \
                 From E900COP \
                Where E900COP.CodEmp = :VSCodEmp \
                  And E900COP.CodOri = :VSOriOrp \
                  And E900COP.NumOrp = :VSNumOrp";
    SQL_Criar(CCurCop);
    SQL_DefinirComando(CCurCop, TClaSql);
    SQL_DefinirInteiro(CCurCop,"VSCodEmp",VSCodEmp);
    SQL_DefinirAlfa(CCurCop,"VSOriOrp",VSOriOrp);
    SQL_DefinirInteiro(CCurCop,"VSNumOrp",VSNumOrp);
    SQL_AbrirCursor(CCurCop);
    Se (SQL_EOF(CCurCop) = 0)
      {
        SQL_RetornarData(CCurCop,"WWDtrIni",VDatIni);
        SQL_RetornarData(CCurCop,"WWDtrFim",VDatFim);
        SQL_RetornarAlfa(CCurCop,"WWSitOrp",VSitOrp);
        SQL_RetornarAlfa(CCurCop,"WWProOrp",VProOrp);
      }
    SQL_Destruir(CCurCop);

    Se (VSDatMov < VEstPdi) @ data de apontamento não pode ser menor que a data inicial do período do estoque @
       Geralog("Data de apontamento inferior a data inicial da período do estoque, verifique!!!");

    /*
    Status da OP:
    - A Em Andamento;
    - L Liberada;
    - R Reabilitada;
    - F Finalizada;
    */

    Se ((VSCodPro <> VProOrp) e (Codusu <> 307) e (codusu <> 660) e (codusu <> 331)) @ verifica o produto apontado é o produto acabado da OP @
      {
        Se ((VSitOrp = 'A') ou (VSitOrp = 'L') ou (VSitOrp = 'R'))  @ data de apontamento não pode ser menor que a data inicial da OP @
          {
            Se (VSDatMov < VDatIni)
              GeraLog("Data de apontamento inferior a data de início da OP, verifique!!!");
          }
         Senao
           Se (VSitOrp = 'F')
             {
               DesMontaData(VDatIni,VDia,VMes,VAno);
               MontaData(1,VMes,VAno,VDatIni);
               UltimoDia(VDatFim);

               Se (VSDatMov < VDatIni)
                 GeraLog("Data de apontamento inferior a data inicial da OP, verifique!!!");  @ data de apontamento menor que a data inicial da OP, não permitido @

               Se (VSDatMov > VDatFim)
                 GeraLog("Data de apontamento superior a data final da OP, verifique!!!"); @ data de apontamento maior que a data final da OP, não permitido @
             }
      }
  }




/*
- Consistência na na movimentação de deposito 01.00 - Almoxarifado, chamado #17061;
- 22/02/2021 - ECC (implantação);
- select * from r910ent where tipent <> 'U';
- 22/03/2022 - ECC (manutenção) - Inclusão do pessoal do faturamento para alterar no deposito 01.00 - chamado = #22165;
- 29/01/2024 - ARF (manutenção) - Incluindo condição para não consistir via ação SID - chamado GLPI 11085;
- 07/01/2025 - Eder             - Liberação do usuário 'glaucia' - 112 (estava fechando inventário nessa data)
- 12/01/2025 - ARF (manutenção) - Liberação do usuário 919 (Marcelo.Fidencio) - chamado 28272 @
- 03/06/2025 - Eder             - Liberação do usuário 998 - eder.venancio - para processamentos relativos ao chamado 28059
- 23/07/2025 - IVM (manutenção) - Reestruturação dos usuários com permissão de acesso ao deposito 01.00 - chamado GLPI 37711;
                                - Usuários permitidos: Alexandre. santos 360; Arthur. Prado 948; Tiago. franca 782; Vicente. Rodrigues 532; Marcio .Sá 343; Leonardo. Bento 1093;
                                                       Nayara. Calixto 1095; Vitoria. Tavares 1092; Orlando palmeiro 954; Fábio pereira 472; Cristopher 717;
                                                       Matheus antunes 1106; Christian Kienen 953; Alessandra teodoro 688; Glaucia 112; Adilson 739; Marcelo 919
                                                       Claudio 1011; Vanderson 776; Daiane Morlo 804
 - 01/09/2025 - IVM (manutenção) - Comentado por causa da nova lógica de liberação de movimentação - chamado GLPI 38248;
*/
/*
Definir Alfa   VSEstado; @ ALFA Indicativo da operação sendo realizada sobre o produto ("INSERINDO", "ALTERANDO" ou "EXCLUINDO") N @
Definir Alfa   VSTela;   @ ALFA Tela de onde partiu a chamada da regra N @
Definir Numero VSCodEmp; @ NÚMERO Código da empresa (chave do produto) N @
Definir Alfa   VSCodPro; @ ALFA Código do produto (chave do produto) N @
Definir Alfa   TClaSql;
Definir Alfa   CCurGrp;
VMemId = CodUsu;
VGrPid = 1073742165; @ Grupo => "Movimentação Deposito" no SGU @
VAchou = 0;

Se ((VSCodEmp = 1) e (VSCodDep = "01.00") e (AmbWeb = 0))
  {
    TClaSql = "Select R900GRP.MemId WWMemId \
                 From R900GRP \
                Where R900GRP.GrPid = :VGrPid \
                  And R900GRP.MemId = :VMemId";
    SQL_Criar(CCurGrp);
    SQL_DefinirComando(CCurGrp, TClaSql);
    SQL_DefinirInteiro(CCurGrp,"VGrPid",VGrPid);
    SQL_DefinirInteiro(CCurGrp,"VMemId",VMemId);
    SQL_AbrirCursor(CCurGrp);
    Se (SQL_EOF(CCurGrp) = 0)
      {
        VAchou = 1;
      }
    SQL_Destruir(CCurGrp);

    VGrPid = 1073742155; @ Usuário - Faturamento @

    TClaSql = "Select R900GRP.MemId WWMemId \
                 From R900GRP \
                Where R900GRP.GrPid = :VGrPid \
                  And R900GRP.MemId = :VMemId";
    SQL_Criar(CCurGrp);
    SQL_DefinirComando(CCurGrp, TClaSql);
    SQL_DefinirInteiro(CCurGrp,"VGrPid",VGrPid);
    SQL_DefinirInteiro(CCurGrp,"VMemId",VMemId);
    SQL_AbrirCursor(CCurGrp);
    Se (SQL_EOF(CCurGrp) = 0)
      {
        VAchou = 1;
      }
    SQL_Destruir(CCurGrp);

    Se ((CodUsu <> 360) Ou (CodUsu <> 948) Ou (CodUsu <> 782) Ou (CodUsu <> 532) Ou (CodUsu <> 343) Ou
        (CodUsu <> 1093) Ou (CodUsu <> 1095) Ou (CodUsu <> 1092) Ou (CodUsu <> 954) Ou (CodUsu <> 472) Ou
        (CodUsu <> 717) Ou (CodUsu <> 1106) Ou (CodUsu <> 953) Ou (CodUsu <> 688) Ou (CodUsu <> 112) Ou
        (CodUsu <> 739) Ou (CodUsu <> 919) Ou (CodUsu <> 1011) Ou (CodUsu <> 776) Ou (CodUsu <> 804))
    {
      VAchou = 1;
    }

    Se (VAchou = 0)
      GeraLog("Usuário não possui permissão para efetuar manutenção no deposito 01.00 - Almoxarifado");
  }
*/

/*
- Consistência na movimentação de deposito 01.25, somente permitido Custos - chamado 22133;
- 22/02/2021 - ARF (implantação);
- 01/09/2022 - ARF (manutenção) - Liberação de movimentação ao usuário 131 da Ceni - chamado 89 (GLPI);
- 27/10/2022 - ARF (manutenção) - Liberação de movimentação do usuário 405 (jose oliveira) e 577 (fernando neto) - chamado GLPI 631;
- 21/11/2022 - DIH (Manutenção) - Bloqueado para todos exceto custos e faturamento - chamado GLPI 986
- 02/02/2023 - ARF (manutenção) - Liberação de movimentação para os usuários 425 (Pedro Xavier) e 630 (Alexandro Goulart) - chamado GLPI 2186;
- 19/05/2023 - ARF (manutenção) - Liberação de movimentação para o usuário 726 (Djonatan) - chamado GLPI 4406;
- 26/05/2023 - ARF (manutenção) - Liberação de movimentação para o usuário 405 (José) e 577 (Fernando)- chamado GLPI 4582;
- 03/01/2024 - ECC (manutenção) - Retirado os usuario 405,577,425,630 e incluido os usuario 681 (igor) e 682 (marcelo) - chamado 11325;
- 27/05/2024 - ECC (manutenção) - Liberação de movimentação para o usuário 637 (Diego Kammer) - chamado GLPI 18029, autorizado pela Glaucia;
- 28/06/2024 - ECC (manutenção) - Liberação de movimentação para o usuário 917 (Thiago Kombat) - chamado GLPI 19476, autorizado pela Glaucia;
- 14/08/2024 - ECC (manutenção) - Liberação de movimentação para o usuário 494 (Rita) - chamado GLPI 21341, autorizado pela Vilmar;
- 07/01/2025 - Eder             - Liberação do usuário 'glaucia' - 112 (estava fechando inventário nessa data)
- 12/01/2025 - Eder             - Liberação do usuário 'daiane.morlo'- 804 (ações de acerto para inventário)
- 04/08/2025 - IVM (manutenção) - Liberação de movimento para usuário 1142 (Patrique) - chamado GLPI 38411;
- 29/08/2025 - ECC (manutenção) - Liberação de mocimento para usuário 1058 (Lucas.Pereira);
- 01/09/2025 - IVM (manutenção) - Comentado por causa da nova lógica de liberação de movimentação - chamado GLPI 38248;
*/
/*
Definir Alfa   TClaSql;
Definir Alfa   CCurGrp;
VMemId = CodUsu;
VGrPid = 1073742166; @ grupo "Usuários - Custos" @
VGrFat = 1073742155; @ grupo "Usuários - Faturamento" @
VAchou = 0;

Se ((VSCodEmp = 1) e (VSCodDep = "01.25") e (codusu <> 307) e (codusu <> 637)) @ Custos, Faturamento e Elisa @
  {
    TClaSql = "Select R900GRP.MemId WWMemId \
                 From R900GRP \
                Where (R900GRP.GrPid = :VGrPid \
                   or R900GRP.GrPid = :VGrFat) \
                  And R900GRP.MemId = :VMemId";
    SQL_Criar(CCurGrp);
    SQL_DefinirComando(CCurGrp, TClaSql);
    SQL_DefinirInteiro(CCurGrp,"VGrPid",VGrPid);
    SQL_DefinirInteiro(CCurGrp,"VGrFat",VGrFat);
    SQL_DefinirInteiro(CCurGrp,"VMemId",VMemId);
    SQL_AbrirCursor(CCurGrp);
    Se (SQL_EOF(CCurGrp) = 0)
      {
        VAchou = 1;
      }
    SQL_Destruir(CCurGrp);

    Se ((CodUsu = 681) Ou (CodUsu = 682) Ou (CodUsu = 726) ou (CodUsu = 682) ou (CodUsu = 917) ou  (CodUsu = 464) ou (CodUsu = 112) ou (CodUsu = 1128) ou
    (CodUsu = 804) Ou (CodUsu = 1142) ou (CodUsu <> 1058))
      VAchou = 1;

    Se (VAchou = 0)
      GeraLog("Usuário não possui permissão para efetuar movimentação no deposito 01.25 - somente Custos, Logística e  Faturamento");
  }
*/

/*
- Consistência na movimentação de deposito 01.03, não permitir usuário 418 - chamado 22004;
- 22/02/2021 - ARF (implantação);
- 07/08/2024 - ARF (manutenção) - Alteração na lista de usuários com permissão de acesso ao deposito 01.03 - chamado GLPI 20885;
                                - Usuário permitidos: 96 - Ceni de Fatima, 195 - Cristina Pinheiro, 302 - Denise Cirico, 341 - Simone Muller, 404 - Pither Arcuri,
                                                     405 - Jose Eduardo, 473 - Ezequiel Lemos, 512 - Janete Antunes, 708 - Juarez Bunger, 721 - Jonathas Silva,
                                                     750 - Ueliton silva pereira, 863 - Robson Daltoe nunes e 891 - Gustavo Salvador;
- 07/08/2024 - ARF (manutenção) - Inclusão de novos usuários: 23 - Vilmar Chiodini, 472 Fabio barbosa Pereira, 717 Cristopher M de pinho, 818 Tauany L rocha e 953 Christian C kienen;
- 16/08/2024 - ARF (manutenção) - Inclusão de novos usuários: 652 - Natanael conforme autorização do Ueliton;
- 09/09/2024 - ARF (manutenção) - Inclusão do usuário '462 - Renate' - Chamado 22463;
- 16/09/2024 - ARF (manutenção) - Inclusão do usuários 'Rita-464 e Irma - 733' - Chamados: 22710 e 22709 - Conforme autorização do Ueliton;
- 07/01/2025 - Eder             - Liberação do usuário 'glaucia' - 112 (estava fechando inventário nessa data)
- 10/01/2025 - IVM (manutenção) - Liberação do usuário 'Claudio Valdameri-1011', chamado 28269;
- 16/05/2025 - DGF (manutenção) - Liberação do usuário 'Matheus Almeida Pires - 1100', chamado 34754;
- 10/06/2025 - Manutenção - Chamado 35941 - Incluido os usuários Fernando Neto e Mateus Antunes;
- 13/06/2025 - Manutenção - Chamado 36149 - Incluido os usuários Saulo Brito Cod 1123;
- 15/07/2025 - IVM (manutenção) - Reestruturação dos usuários com permissão de acesso ao deposito 01.03 - chamado GLPI 37465;
                                - Usuários permitidos: Saulo - 1123; Juarez - 708; Fernando - 577; Ezequiel - 473; Gustavo - 891; Robson - 863;
                                                       Orlando - 954; Fabio - 472; Cristopher - 717; Matheus - 1106; Christian - 953;
                                                       Alessandra - 688; Glaucia - 112; Adilson - 739; Marcelo - 919; Claudio - 1011;
                                                       Vanderson - 776; Daiane - 804
- 05/08/2025 - IVM (manutenção) - Liberação do usuário 'Renate Frehner - 462', chamado GLPI 38392;
- 01/09/2025 - IVM (manutenção) - Comentado por causa da nova lógica de liberação de movimentação - chamado GLPI 38248;
*/
/*
nCodUsu = CodUsu;
Se ((VSCodEmp = 1) e (VSCodDep = "01.03") e ((nCodUsu <> 1123)  e (nCodUsu <> 708) e (nCodUsu <> 577) e
                                             (nCodUsu <> 473) e (nCodUsu <> 891) e (nCodUsu <> 863) e
                                             (nCodUsu <> 954) e (nCodUsu <> 472) e (nCodUsu <> 717) e
                                             (nCodUsu <> 1106) e (nCodUsu <> 953) e (nCodUsu <> 688) e
                                             (nCodUsu <> 112) e (nCodUsu <> 739)  e (nCodUsu <> 919) e
                                             (nCodUsu <> 1011) e (nCodUsu <> 776) e (nCodUsu <> 804) e
                                             (nCodUsu <> 40) e (nCodUsu <> 660) e (nCodUsu <> 331) e (nCodUsu <> 1058) e (nCodUsu <> 462)))
  GeraLog("Usuário não possui permissão para efetuar movimentação no deposito 01.03");
*/

/*
- Consistencia no acesso das depositos de qualidade ('01.14', 'AV.CD', 'AV.DM' e 'AV.SP'), liberado apenas para alguns usuarios - chamado 27425;
- 17/12/2024 - IVM (implantação);
- Usuários permitidos: Jorge - 1006
                       Silvana - 965
                       Ariane - 971
                       Natanael - 652
                       Irma - 733
                       Rita - 464
                       Edenilce - 208
- 07/01/2025 - Eder             - Liberação do usuário 'glaucia' - 112 (estava fechando inventário nessa data)
- 11/01/2025 - Eder             - Liberação do usuário 'djonatan.elias'- 726 (ações de acerto para inventário) - pode ser retirado em 13/01 após inventário
- 05/02/2025 - ECC (manutenção) - Liberado usuario 660 - XC que são as movimentações feito pelo coletor
- 03/06/2025 - Eder             - Liberação do usuário 998 - eder.venancio - para processamentos relativos ao chamado 28059
- 06/08/2025 - IVM (manutenção) - Liberado usuario 1142 - patrique.araujo - chamado GLPI 38411;
- 01/09/2025 - IVM (manutenção) - Comentado por causa da nova lógica de liberação de movimentação - chamado GLPI 38248;
*/
/*
Se ((VSCodEmp = 1) e
    ((VSCodDep = "01.14") Ou (VSCodDep= "AV.CD") Ou (VSCodDep = "AV.DM") Ou (VSCodDep = "AV.SP")) e
    ((nCodUsu <> 1006) e (nCodUsu <> 965) e (nCodUsu <> 971) e (nCodUsu <> 652) e (nCodUsu <> 733) e (nCodUsu <> 464) e
     (nCodUsu <> 208) e (nCodUsu <> 112) e (nCodUsu <> 726) e (nCodUsu <> 660) e (nCodUsu <> 998) e (nCodUsu <> 1058)  Ou (nCodUsu <> 1142)))
    GeraLog("Usuário não possui permissão para efetuar movimentação nos deposito '01.14'/'AV.CD'/'AV.DM'/'AV.SP'");
*/

/*
- Gera e-mail ao movimentar estoque 01.23 - chamado 23752;
- 27/06/2022 - ARF (implantação);
*/
Definir Alfa VMsgStr;
Definir Alfa aQtdMov;
Definir Alfa aCodUsu;
ConverteMascara(1,VSQtdMov,aQtdMov,"ZZZ.ZZZ.ZZ9,99999");
LimpaEspacos(aQtdMov);
IntParaAlfa(VSUSUDIG,aCodUsu);

Se ((VSCodEmp = 1) e (VSCodDep = "01.23"))
  {
    VMsgStr = "Produto: " + VSCodPro + "/" + VSCodDer + ", qtd.: " + aQtdMov + ", usuário: " + aCodUsu;
    EnviarEmail("sapiens@indaialpapel.com.br","Movimentação no depósito 01.23","marcelo.santana@indaialpapel.com.br","alexandre.francisco@indaialpapel.com.br","",vMsgStr,"","T");
  }

/*
- Consistência na transferências em plantas, exigir o número da OP - chamado 25104/358 (GLPI);
- 07/10/2022 - ARF (implantação);
- 24/10/2022 - ARF (manutenção) Inclusão de filtros por família e produto;
*/
Definir Numero VSNUMDOC; @ NÚMERO	Número do Documento	N @
Definir Alfa   aCodOri;
Definir Alfa   aCodFam;
Definir Alfa   TClaSql;
Definir Alfa   CCurFam;
aCodFam = "";
TClaSql = "SELECT CodOri aCodOri, \
                  CodFam aCodFam  \
             FROM E075PRO \
            WHERE CodEmp = :VSCODEMP \
              AND CodPro = :VSCODPRO";
SQL_Criar(CCurFam);
SQL_DefinirComando(CCurFam, TClaSql);
SQL_DefinirInteiro(CCurFam,"VSCODEMP",VSCODEMP);
SQL_DefinirAlfa(CCurFam,"VSCODPRO",VSCODPRO);
SQL_AbrirCursor(CCurFam);
Se (SQL_EOF(CCurFam) = 0)
  {
    SQL_RetornarAlfa(CCurFam,"aCodOri",aCodOri);
    SQL_RetornarAlfa(CCurFam,"aCodFam",aCodFam);
  }
SQL_Destruir(CCurFam);

Se ((VSOrigem = "F210TPA") e ((VSCodDep = "01.03") Ou (VSCodDep = "P01.01") Ou (VSCodDep = "P01.02")) e ((VSNumDoc = 0) Ou (ESTNNumDoc = 0)) e
   ((VSCodPro <> "76090008") e (VSCodPro <> "76090009") e (VSCodPro <> "76090010") e (VSCodPro <> "76090113") e (VSCodPro <> "76090115") e (VSCodPro <> "76090116") e
    (VSCodPro <> "6803")     e (VSCodPro <> "6802")     e (VSCodPro <> "6804")     e (VSCodPro <> "6808")     e (VSCodPro <> "6807")     e (VSCodPro <> "6806")     e
    (aCodFam <> "7506") e (aCodFam <> "7603") e (aCodFam <> "7003") e (aCodFam <> "7602") e (aCodFam <> "7508") e (aCodOri <> "630")))
  {
    GeraLog("Nas Transferências entre plantas, informar o número da OP, no campo Documento!");
  }

/*
- Consistência na tranferência (F210TPA) de bobinas, permitido somente para alguns usuários - chamado GLPI 1448;
- 23/12/2022 - ARF (implantação);
- 30/12/2022 - ARF (manutenção) Inclusão de novos usuários - chamado GLPI 1646;

- Ariane Tortato (não cadastrado);
- João Carlos Miranda - 315;
- Natanael Barbosa da Silva - 652;
- Rosângela Florentino - 209;
- Tatiana Pinheiro - 303;
- apontamento.bobina - 188;
- rita.cruz - 464;
--Denise Ciro - 302
*/

nCodUsu = CodUsu;
Se ((VSCodEmp = 1) e (VSOrigem = "F210TPA") e ((VSCodOri = "200") ou (VSCodOri = "200")) e
   ((nCodUsu <> 188) e (nCodUsu <> 302) e (nCodUsu <> 209) e (nCodUsu <> 303) e (nCodUsu <> 315) e (nCodUsu <> 464) e (nCodUsu <> 637) e (nCodUsu <> 652)e (nCodUsu <> 307) e (nCodUsu <> 660)))
  Geralog("Transferência de Bobina não permitida para este usuário!");

/*
- Consistência na movimentação do deposito 01.26, permitido somente para alguns usuários - chamado GLPI 3265;
- 11/04/2023 - ARF (implantação);
- 12/04/2023 - ARF (manutenção) - Inclusão de novos usuários;
- 21/07/2023 - ARF (manutenção) - Inclusão de novo usuário Layara - chamado GLPI 5937;
- 26/07/2023 - ARF (manutenção) - Inclusão do grupo Faturamento - chamado GLPI 6025;
- 06/12/2023 - ARF (manutenção) - Retirado o grupo faturamento o acesso ao depósito 01.26, mantido apenas para os usuário 360, 397, 782 e 834 - chamado GLPI 10409;
- 07/12/2023 - ARF (manutenção) - Reenincluído os usuários 472, 717 e 743 - chamado GLPI 10409;
- 04/04/224 - ARF (manutenção) - Inclusão de novo usuário  Christian Kienen (953) - chamado GLPI 19757;
- 30/12/2024 - ARF (manutenção) - Inclusão de novo usuário Pihter (404)  - chamado GLPI 27821;
- rafael.bueno - 397;
- tiago.franca - 782;
- Alexandre dos Santos - 360;
- Fabio.pereira - 472
- Cristopher Pinho - 717;
- Adriano Eger - 453;
- Elisa - 307;
- Layara - 743;
- Willian Malosti - 834
- Tauany  Rocha = 818
- Matheus Antunes = 1106 -> Chmamado 35602;
- 03/06/2025 - Eder             - Liberação do usuário 998 - eder.venancio - para processamentos relativos ao chamado 28059
- 27/06/2025 -   ARF (manutenção) - Inclusão de novo usuário Arthur,Prado (948)  - chamado GLPI 36780;

- 11/07/2025 -  ARF (manutenção) - Revisado os usuários com acesso a movimentação no depósito 01.26;
- 31/07/2025 - IVM (manutenção) - Adicionado usuário 945 (Eristark.Araujo) e 581 (Alessandra.Booz)
- 07/08/2025 - ARF (manutenção) - Inclusão do usuário '462 - Renate' - Chamado 38392;
- 29/08/2025 - ARF (manutenção) - Inclusão do usuário '816 - Nathalia.Silva' - Chamado 39606;
- 01/09/2025 - IVM (manutenção) - Comentado por causa da nova lógica de liberação de movimentação - chamado GLPI 38248;
*/
/*
nCodUsu = CodUsu;
VGrFat = 1073742155; @ grupo "Usuários - Faturamento" @
VAchou = 0;

Se ((VSCodEmp = 1) e (VSCodDep = "01.26"))
  { /*
    @ busca o grupo do usuário @
    TClaSql = "Select R900GRP.MemId WWMemId \
                 From R900GRP \
                Where R900GRP.GrPid = :VGrFat \
                  And R900GRP.MemId = :nCodUsu";
    SQL_Criar(CCurGrp);
    SQL_DefinirComando(CCurGrp, TClaSql);
    SQL_DefinirInteiro(CCurGrp,"VGrFat",VGrFat);
    SQL_DefinirInteiro(CCurGrp,"nCodUsu",nCodUsu);
    SQL_AbrirCursor(CCurGrp);
    Se (SQL_EOF(CCurGrp) = 0)
      {
        VAchou = 1;
      }
    SQL_Destruir(CCurGrp);
   *
   @ usuário liberados @
Se ((nCodUsu = 360) ou (nCodUsu = 782) ou (nCodUsu = 717) ou (nCodUsu = 472) ou
    (nCodUsu = 866) ou (nCodUsu = 660) ou (nCodUsu = 953) ou (nCodUsu = 307) ou
    (nCodUsu = 112) ou (nCodUsu = 1106) ou (nCodUsu = 948) ou (nCodUsu = 998) ou
    (nCodUsu = 816) ou (nCodUsu = 462))
   VAchou = 1;

Se (VAchou = 0)
  Geralog("Movimentação no depósito 01.26 não permitida para este usuário!");

  }
*/

@ Consistencia deposito CD Barueri @
@24/10/2024 - Adicionado o usuário Natanael (usu 652) - Chamado: 24971 @

/*
Se ((VSCodDep = "03.00") e (VsCodFil = 1) e (nCodUsu <> 919) e (nCodUsu <> 652))
      Geralog("Filial matriz (Filial 1) não pode movimentar deposito 03.00 - CD Barueri (Filial 3), favor verificar! ");
*/

/*
Se ((VSCodDep <> "03.00") e (VSCodDep <> "AV.SP") e (VsCodFil = 3) e (nCodUsu <> 919) e (nCodUsu <> 652))
      Geralog("Filial CD Barueri (Filial 3) só pode movimentar o deposito 03.00, favor verificar! ");
*/
/*
Se ((VSCodDep = "03.00") e (VsNumNfv = 0) e (VsNumNfc = 0) e (nCodUsu <> 919) e (nCodUsu <> 652) e (VSDepTrf <> "AV.SP"))
    Geralog("Filial CD Barueri (Filial 3),não aceita essa movimentação, só via nota, favor verificar! ");
*/

@ Consistencia para não gerar movimentação de transferencia com lote padrão @
Se ((VsCodLot = "620000") e ((VSCodTns = "90241") ou (VSCodTns = "90242")))
inicio
  Definir Alfa VaCodFam;
  Definir Alfa TClaSql;
  Definir Alfa CBusPro;
  TClaSql = "SELECT E075PRO.CodFam VaCodFam \
             FROM E075PRO \
              WHERE E075PRO.CodEmp=:VSCODEMP \
                AND E075PRO.CodPro=:VSCODPRO";
  SQL_Criar(CBusPro);
  SQL_DefinirComando(CBusPro, TClaSql);
  SQL_DefinirInteiro(CBusPro,"VSCODEMP",VSCODEMP);
  SQL_DefinirAlfa(CBusPro,"VSCODPRO",VSCODPRO);
  SQL_AbrirCursor(CBusPro);
  Se (SQL_EOF(CBusPro) = 0)
    {
      SQL_RetornarAlfa(CBusPro,"VaCodFam",VaCodFam);
    }
  SQL_Destruir(CBusPro);
  Se ((VaCodFam = "626") ou (VaCodFam = "628") ou (VaCodFam = "621") ou (VaCodFam = "622") ou (VaCodFam = "626")
   ou (VaCodFam = "624") ou (VaCodFam = "627") ou (VaCodFam = "628") ou (VaCodFam = "623"))
     Geralog("Não é permitido transferencia do Lote padrão de materia prima!");
Fim;

/*
 - 26/08/2025 - IVM (implantação) - Nova lógica de liberação de movimentação (comentada) - chamado GLPI 38248;
 - 01/09/2025 - IVM (liberação) - liberação da regra;
*/
Definir Alfa VSCodDep;
Definir Alfa TClaSql;
Definir Alfa CCurLib;
Definir Alfa CCurPer;
Definir Alfa aMsgIna;
Definir Alfa aMsgPer;
Definir Alfa aLibMov;
Definir Alfa aCodOri;

nCodEmp = CodEmp;
nCodUsu = CodUsu;
vAchou  = 0;
vTemReg = 0;

Se ((nCodUsu <> 331) e (nCodUsu <> 660) e (nCodUsu <> 40) e (nCodUsu <> 420) e (nCodUsu <> 1053) e (nCodUsu <> 1186) e (nCodUsu <> 1282))
{
  TClaSql = "Select Usu_LibMov WWLibMov \
                From USU_TLibMov \
              Where Usu_CodEmp = :nCodEmp \
                And Usu_CodDep = :VSCodDep \
                And Usu_LibMov = 'A'";
  SQL_Criar(CCurPer);
  SQL_DefinirComando(CCurPer,TClaSql);
  SQL_DefinirInteiro(CCurPer, "nCodEmp", nCodEmp);
  SQL_DefinirAlfa(CCurPer, "VSCodDep", VSCodDep);
  SQL_AbrirCursor(CCurPer);
  Se (SQL_EOF(CCurPer) = 0)
  {
    vTemReg = 1;
  }
  SQL_Destruir(CCurPer);

  Se (vTemReg = 1)
  {
    TClaSql = "Select Usu_LibMov WWLibMov, \
                      Usu_CodOri WWCodOri \
                  From USU_TLibMov \
                Where Usu_CodEmp = :nCodEmp \
                  And Usu_CodUsu = :nCodUsu \
                  And Usu_CodDep = :VSCodDep";
    SQL_Criar(CCurLib);
    SQL_DefinirComando(CCurLib, TClaSql);
    SQL_DefinirInteiro(CCurLib, "nCodEmp", nCodEmp);
    SQL_DefinirInteiro(CCurLib, "nCodUsu", nCodUsu);
    SQL_DefinirAlfa(CCurLib, "VSCodDep", VSCodDep);
    SQL_AbrirCursor(CCurLib);
    Se (SQL_EOF(CCurLib) = 0)
    {
      SQL_RetornarAlfa(CCurLib, "WWLibMov", aLibMov);
      SQL_RetornarAlfa(CCurLib, "WWCodOri", aCodOri);
      LimpaEspacos(aCodOri);

      Se ((aCodOri = VSCodOri) Ou (aCodOri = ""))
        vAchou = 1;
    }
    SQL_Destruir(CCurLib);

    Definir Alfa aCodUsu;
    nCodUsu = CodUsu;
    IntParaAlfa(nCodUsu, aCodUsu);

    aMsgIna = "Permissão do usário ("+ aCodUsu +") inativa para efetuar manutenção no depósito " + VSCodDep + "! Verificar com Controladoria.";
    aMsgPer = "Usuário ("+ aCodUsu +") não possui permissão para efetuar manutenção no depósito " + VSCodDep + " e na origem " + VSCodOri +"! Verificar com Controladoria.";

    Se (aLibMov = "I")
      Mensagem(Erro, aMsgIna);

    Se (vAchou = 0)
      Mensagem(Erro, aMsgPer);
  }

}







/*
@ Somar FunRural no valor do estoque @
TClaSql = "SELECT * From E440IPC \
            where CodEmp = VsCodEmp \
              and CodPro = VsCodPro \
              and CodDer = VSCodDer \
              and NumNfc = VsNumNfc \
              and CodFor = VsCodFor \
              And SeqIpc = VSSeqIpc \
              and SnfNfc = VsSnfNfc";
  SQL_Criar(CBusPro);
  SQL_DefinirComando(CBusPro, TClaSql);
  SQL_DefinirInteiro(CBusPro,"VsCodEmp",VsCodEmp);
  SQL_DefinirAlfa(CBusPro,"VSCODPRO",VSCODPRO);
  SQL_AbrirCursor(CBusPro);
  Se (SQL_EOF(CBusPro) = 0)
    {
      SQL_RetornarAlfa(CBusPro,"VaCodFam",VaCodFam);
    }
  SQL_Destruir(CBusPro);

*/

@ Travar apontamento duplicado @
/*Definir Alfa CBusApo;
Se ((VSCODTNS = "90201") e (VSORIORP = "410"))
Inicio
  TClaSql = "SELECT CODLOT E210MVP WHERE CODLOT =:VSCodLot";
  SQL_Criar(CBusApo);
  SQL_DefinirComando(CBusApo, TClaSql);
  SQL_DefinirAlfa(CBusApo,"VSCodLot",VSCodLot);
  SQL_AbrirCursor(CBusApo);
  Se (SQL_EOF(CBusApo) = 0)
    {
      Geralog("Lote já apontado, favor verificar!");
    }
  SQL_Destruir(CBusApo);
Fim;

x=1;     */


/*
 - 02/06/2026 -  lote ao transferir para o deposito 01.14 - Area Vermelha.
*/
Definir Numero nCodLotNulo;

EstaNulo(VSCodLot, nCodLotNulo);
Se ((VSDepTrf = "01.14") e (nCodLotNulo = 0) e (VSESTADO <> "EXCLUINDO"))
{
  ExecSql "UPDATE E210DLS \
              SET USU_SITLOT = 'V' \
            WHERE CodEmp = :VSCodEmp \
              AND CodLot = :VSCodLot";
}
