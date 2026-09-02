/*
Processa pendencias de baixa gravadas na USU_TBXACMP via webservice.

Fluxo baseado na regra 929, mas sem IPOS e sem apontamento:
1) Recebe USU_IdeUni pela tabela de pendencias do webservice.
2) Define familia, centro de custo e deposito de baixa.
3) Remove reserva do componente.
4) Usa USU_CODLOT como lote do componente; se vier vazio, busca lote com saldo.
5) Valida saldo, libera o componente na OP e chama BaixarComponentes.
6) Atualiza a USU_TBXACMP com sucesso ou erro e grava log de processamento.

USU_SITPEN:
1 = pendente
2 = em processamento
3 = processado
4 = erro
*/

Definir Funcao Fun_GravaLog();

Definir Alfa CCurBxa;
Definir Alfa CCurFam;
Definir Alfa CCurCre;
Definir Alfa CCurLot;
Definir Alfa CCurEst;
Definir Alfa CCurCmo;
Definir Alfa TClaSql;
Definir Alfa aParApt;
Definir Alfa aRetorno;
Definir Alfa aMsgStr;
Definir Alfa aCodOri;
Definir Alfa aCodCmp;
Definir Alfa aDerCmp;
Definir Alfa aLotDes;
Definir Alfa aQtdUti;
Definir Alfa aNumOrp;
Definir Alfa aCodEtg;
Definir Alfa aDatMov;
Definir Alfa aCodCre;
Definir Alfa aCodFam;
Definir Alfa aCodCcu;
Definir Alfa aCodDep;
Definir Alfa aCodLot;
Definir Alfa aCodLotInf;
Definir Alfa aCodDepEst;
Definir Alfa aQtdEstCmp;
Definir Alfa aQtdMovCmp;
Definir Alfa aQtdMovEst;
Definir Alfa aQtdEstLot;
Definir Alfa aMsgLog;
Definir Alfa aBxaOrpOri;
Definir Alfa aIdeUni;
Definir Alfa aDesRet;
Definir Alfa aInfAdc;
Definir Alfa aInfLog;
Definir Alfa aJsoEnv;
Definir Numero nCodEmp;
Definir Numero nCodFil;
Definir Numero nQtdReg;
Definir Numero nCtdReg;
Definir Numero nNumOrp;
Definir Numero nCodEtg;
Definir Numero nQtdUti;
Definir Numero nQtdEstCmp;
Definir Numero nQtdEstLot;
Definir Numero nHorMov;
Definir Numero nHorSis;
Definir Numero nErro;
Definir Numero nPos;
Definir Numero nContinuar;
Definir Numero nLocPla;
Definir Numero nAchoLote;
Definir Numero nTransEst;
Definir Numero nWebErr;
Definir Numero nTemCmo;
Definir Numero nUsuPrc;
Definir Numero nStaInt;
Definir Data dDatMov;
Definir Data dDatSis;

nQtdReg = BaixaComponenteERP.pendencias.qtdLinhas;
nCtdReg = 0;

Enquanto (nCtdReg < nQtdReg)
  {
    BaixaComponenteERP.pendencias.linhaAtual = nCtdReg;
    aIdeUni = BaixaComponenteERP.pendencias.ideUni;

    TClaSql = "SELECT USU_CODEMP WWCodEmp, \
                      USU_CODORI WWCodOri, \
                      USU_NUMORP WWNumOrp, \
                      USU_CODETG WWCodEtg, \
                      USU_CODCMP WWCodCmp, \
                      USU_DERCMP WWDerCmp, \
                      USU_LOTDES WWLotDes, \
                      USU_QTDUTI WWQtdUti, \
                      USU_CODCRE WWCodCre, \
                      USU_CODLOT WWCodLot, \
                      USU_DATMOV WWDatMov, \
                      USU_HORMOV WWHorMov \
                 FROM USU_TBXACMP \
                WHERE USU_IdeUni = :aIdeUni \
                  AND USU_SitPen = 2";

    SQL_Criar(CCurBxa);
    SQL_UsarSQLSenior2(CCurBxa,0);
    SQL_UsarAbrangencia(CCurBxa,0);
    SQL_DefinirComando(CCurBxa, TClaSql);
    SQL_DefinirAlfa(CCurBxa, "aIdeUni", aIdeUni);
    SQL_AbrirCursor(CCurBxa);

    Se (SQL_EOF(CCurBxa) = 0)
      {
    @ Carrega a pendencia. USU_CODCRE e alfa na tabela, pois E725CRE.CodCre tambem e codigo texto. @
    SQL_RetornarInteiro(CCurBxa,"WWCodEmp",nCodEmp);
    SQL_RetornarAlfa(CCurBxa,"WWCodOri",aCodOri);
    SQL_RetornarInteiro(CCurBxa,"WWNumOrp",nNumOrp);
    SQL_RetornarInteiro(CCurBxa,"WWCodEtg",nCodEtg);
    SQL_RetornarAlfa(CCurBxa,"WWCodCmp",aCodCmp);
    SQL_RetornarAlfa(CCurBxa,"WWDerCmp",aDerCmp);
    SQL_RetornarData(CCurBxa,"WWDatMov",dDatMov);
    SQL_RetornarInteiro(CCurBxa,"WWHorMov",nHorMov);
    SQL_RetornarAlfa(CCurBxa,"WWLotDes",aLotDes);
    SQL_RetornarAlfa(CCurBxa,"WWCodLot",aCodLotInf);
    LimpaEspacos(aCodLotInf);
    SQL_RetornarFlutuante(CCurBxa,"WWQtdUti",nQtdUti);
    SQL_RetornarAlfa(CCurBxa,"WWCodCre",aCodCre);

    @ Data/hora/usuario de processamento. USU_DATMOV/USU_HORMOV ficam como data/hora do movimento. @
    dDatSis = DatSis;
    nHorSis = HorSis;
    nUsuPrc = CodUsu;

    @ O web service de movimentacao de estoque exige empresa/filial no contexto correto. @
    nCodFil = 1;
    TrocaEmpresaFilial(nCodEmp,nCodFil);

    /*
    Converte campos numericos/data para alfa porque o parametro BaixarComponentes e texto.
    QtdUti deve ir com ponto para BaixarComponentes.
    MovimentarEstoque espera virgula em QtdMov.
    */
    IntParaStr(nQtdUti,aQtdUti);
    SubstAlfa(",", ".", aQtdUti);
    aQtdMovEst = aQtdUti;
    SubstAlfa(".", ",", aQtdMovEst);
    IntParaAlfa(nNumOrp,aNumOrp);
    IntParaAlfa(nCodEtg,aCodEtg);
    ConverteMascara(3,dDatMov,aDatMov,"DD/MM/YYYY");
    aInfLog = "Origem " + aCodOri + " OP " + aNumOrp + " Comp. " + aCodCmp + "/" + aDerCmp + " Qtd. " + aQtdUti + " - ";

    @ Inicializa variaveis de decisao por registro para nao herdar estado da pendencia anterior. @
    aRetorno = "";
    aCodFam = "";
    aCodCcu = "";
    aCodDep = "";
    aCodLot = "";
    aCodDepEst = "";
    aJsoEnv = "";
    nContinuar = 0;
    nAchoLote = 0;
    nTransEst = 0;
    nQtdEstLot = 0;
    nTemCmo = 0;
    aBxaOrpOri = "";

    nContinuar = 1;

    Se (nContinuar = 1)
      {
        /*
        Busca familia do componente para aplicar as exceções.
        Familias usadas nesta regra:
        500 = Receita Massa.
        613 = Quimicos para Insumos.
        629 = Cola.
        615 = Quimicos para Consumo.

        Familias 613/629/615 baixam no deposito 01.15.
        Familia 500 baixa no deposito 01.02.
        */
        TClaSql = "Select CodFam WWCodFam \
                     From E075PRO \
                    Where CodEmp = :nCodEmp \
                      And CodPro = :aCodCmp";

        SQL_Criar(CCurFam);
        SQL_DefinirComando(CCurFam,TClaSql);
        SQL_DefinirInteiro(CCurFam,"nCodEmp",nCodEmp);
        SQL_DefinirAlfa(CCurFam,"aCodCmp",aCodCmp);
        SQL_AbrirCursor(CCurFam);

        Se (SQL_EOF(CCurFam) = 0)
          SQL_RetornarAlfa(CCurFam,"WWCodFam",aCodFam);

        SQL_FecharCursor(CCurFam);
        SQL_Destruir(CCurFam);

        /*
        Busca centro de custo do recurso e define o deposito padrao.
        O centro de custo entra no parametro CodCcu do BaixarComponentes.
        O deposito nao entra no parametro, mas orienta a busca/validacao do estoque.
        */
        TClaSql = "Select CodCcu WWCodCcu, Usu_LocPla WWLocPla \
                     From E725CRE \
                    Where CodEmp = :nCodEmp \
                      And CodCre = :aCodCre";

        SQL_Criar(CCurCre);
        SQL_UsarSQLSenior2(CCurCre,0);
        SQL_UsarAbrangencia(CCurCre,0);
        SQL_DefinirComando(CCurCre,TClaSql);
        SQL_DefinirInteiro(CCurCre,"nCodEmp",nCodEmp);
        SQL_DefinirAlfa(CCurCre,"aCodCre",aCodCre);
        SQL_AbrirCursor(CCurCre);

        Se (SQL_EOF(CCurCre) = 0)
          {
            SQL_RetornarAlfa(CCurCre,"WWCodCcu",aCodCcu);
            SQL_RetornarInteiro(CCurCre,"WWLocPla",nLocPla);

            /*
            Regra base de deposito por origem/local da planta.
            Origens usadas nesta regra:
            500 = Cavaco.
            405 = Bobina Rebobinada.
            410 = Bobina Rebobinada.
            510 = Receita da Massa.
            */
            Se (aCodOri = "510")
              aCodDep = "P01.03";
            Senao
              {
                Se (nLocPla = 1)
                  aCodDep = "P01.01";
                Se (nLocPla = 2)
                  aCodDep = "P01.02";
              }

            /*
            Excecoes por familia.
            Para producao de massa/bobinas:
            613/629/615 = quimicos/cola no deposito 01.15.
            500 = receita massa no deposito 01.02.
            */
            Se ((aCodOri = "405") ou (aCodOri = "410") ou (aCodOri = "510"))
              {
                Se ((aCodFam = "613") ou (aCodFam = "629") ou (aCodFam = "615"))
                  aCodDep = "01.15";

                Se (aCodFam = "500")
                  aCodDep = "01.02";
              }
          }

        SQL_FecharCursor(CCurCre);
        SQL_Destruir(CCurCre);

        @ Sem centro de custo/deposito nao da para montar uma baixa confiavel. @
        Se ((aCodCcu = "") ou (aCodDep = ""))
          {
            aRetorno = "Nao foi possivel definir centro de custo/deposito para o recurso " + aCodCre;
            nContinuar = 0;
          }
      }

    Se (nContinuar = 1)
      {
        @ Remove reserva do componente antes de tentar baixar. @
        IniciarTransacao();
        ExecSql "UPDATE E210DLS SET QtdRes = 0 Where CodEmp = :nCodEmp \
                 and CodPro =:aCodCmp and CodDer =:aDerCmp";
        FinalizarTransacao();
      }

    Se (nContinuar = 1)
      {
        /*
        USU_LOTDES e o lote destino/produto acabado.
        USU_CODLOT e o lote do componente. Se vier preenchido, respeita esse lote.
        Se o lote do componente estiver em outro deposito, transfere para o deposito da baixa.
        Se o lote informado nao existir para o componente, grava erro sem tentar outro lote.
        */
        Se ((aCodLotInf <> "") e (aCodLotInf <> "0"))
          {
            TClaSql = "SELECT QtdEst WWQtdEst, CodDep WWCodDep \
                         FROM E210DLS \
                        WHERE CodEmp = :nCodEmp \
                          AND CodLot = :aCodLotInf \
                          AND CodPro = :aCodCmp \
                          AND CodDer = :aDerCmp \
                          AND QtdEst <> 0 \
                          AND CodDep <> '08.01' \
                     ORDER BY CodDep DESC";

            SQL_Criar(CCurLot);
            SQL_DefinirComando(CCurLot,TClaSql);
            SQL_DefinirInteiro(CCurLot,"nCodEmp",nCodEmp);
            SQL_DefinirAlfa(CCurLot,"aCodLotInf",aCodLotInf);
            SQL_DefinirAlfa(CCurLot,"aCodCmp",aCodCmp);
            SQL_DefinirAlfa(CCurLot,"aDerCmp",aDerCmp);
            SQL_AbrirCursor(CCurLot);

            Se (SQL_EOF(CCurLot) = 0)
              {
                SQL_RetornarAlfa(CCurLot,"WWCodDep",aCodDepEst);
                SQL_RetornarFlutuante(CCurLot,"WWQtdEst",nQtdEstLot);
                aCodLot = aCodLotInf;
                nAchoLote = 1;

                @ Mesmo com lote certo, o saldo precisa estar no deposito esperado pela baixa. @
                Se (aCodDepEst <> aCodDep)
                  nTransEst = 1;

                @ Quando o lote foi informado, a quantidade precisa caber nele. @
                Se (nQtdEstLot < nQtdUti)
                  {
                    ConverteMascara(2,nQtdEstLot,aQtdEstLot,"ZZZ.ZZZ.ZZ9,99");
                    LimpaEspacos(aQtdEstLot);
                    ConverteMascara(2,nQtdUti,aQtdMovCmp,"ZZZ.ZZZ.ZZ9,99");
                    LimpaEspacos(aQtdMovCmp);

                    aRetorno = "Saldo do lote " + aCodLotInf + " no deposito " + aCodDepEst + " (" + aQtdEstLot +
                               ") insuficiente para atender a quantidade de baixa do componente " + aCodCmp + " (" + aQtdMovCmp + ")";
                    nContinuar = 0;
                  }
              }
            Senao
              {
                aRetorno = "Lote " + aCodLotInf + " nao encontrado com saldo para o componente " + aCodCmp + "/" + aDerCmp;
                nContinuar = 0;
              }

            SQL_FecharCursor(CCurLot);
            SQL_Destruir(CCurLot);
          }

        /*
        Se nao veio lote do componente, procura um lote com saldo no deposito.
        Se nao encontrar, segue sem CodLot.
        Para familia 500 não envia CodLot quando o lote foi achado automaticamente.
        */
        Se ((nContinuar = 1) e (nAchoLote = 0))
          {
            TClaSql = "Select CodLot WWCodLot \
                         From E210DLS \
                        Where CodEmp = :nCodEmp \
                          And CodDep = :aCodDep \
                          And QtdEst >= :nQtdUti \
                          And CodPro = :aCodCmp \
                          And CodDer = :aDerCmp";

            SQL_Criar(CCurLot);
            SQL_DefinirComando(CCurLot,TClaSql);
            SQL_DefinirInteiro(CCurLot,"nCodEmp",nCodEmp);
            SQL_DefinirAlfa(CCurLot,"aCodDep",aCodDep);
            SQL_DefinirFlutuante(CCurLot,"nQtdUti",nQtdUti);
            SQL_DefinirAlfa(CCurLot,"aCodCmp",aCodCmp);
            SQL_DefinirAlfa(CCurLot,"aDerCmp",aDerCmp);
            SQL_AbrirCursor(CCurLot);

            Se (SQL_EOF(CCurLot) = 0)
              {
                SQL_RetornarAlfa(CCurLot,"WWCodLot",aCodLot);
                nAchoLote = 1;
              }

            SQL_FecharCursor(CCurLot);
            SQL_Destruir(CCurLot);
          }
      }

    Se ((nContinuar = 1) e (nTransEst = 1))
      {
        /*
        Transfere o lote informado do componente para o deposito onde a baixa deve ocorrer.
        Este bloco so existe quando USU_CODLOT veio preenchido e foi achado em outro deposito.
        */
        Definir interno.com.senior.g5.co.mcm.est.estoques.MovimentarEstoque VMovEst;
        Definir Alfa aCodEmp;
        Definir Alfa aCodFil;
        Definir Alfa aMsgRet;
        Definir Alfa aErrExe;

        IntParaAlfa(nCodEmp, aCodEmp);
        IntParaAlfa(nCodFil, aCodFil);

        VMovEst.dadosGerais.CodEmp = aCodEmp;
        VMovEst.dadosGerais.CodFil = aCodFil;
        VMovEst.dadosGerais.CodPro = aCodCmp;
        VMovEst.dadosGerais.CodDer = aDerCmp;
        VMovEst.dadosGerais.CodDep = aCodDepEst;
        VMovEst.dadosGerais.CodTns = "90242";
        VMovEst.dadosGerais.QtdMov = aQtdMovEst;
        VMovEst.dadosGerais.DatMov = aDatMov;
        VMovEst.dadosGerais.MotMvp = "Transferencia Manual - BaixarComponentes, SIGMA";
        VMovEst.dadosGerais.CodLot = aCodLot;
        VMovEst.dadosGerais.DepTrf = aCodDep;
        VMovEst.ModoExecucao = 1;
        VMovEst.Executar();

        aRetorno = VMovEst.retornoMovimento.retorno;
        aMsgRet = VMovEst.mensagemRetorno;
        aErrExe = VMovEst.erroExecucao;
        nWebErr = VMovEst.tipoRetorno;

        Se (nWebErr = 2)
          {
            CopiarAlfa(aRetorno,1,180);
            aMsgLog = "Erro na transf. automatica do dep. " + aCodDepEst + " para dep. " + aCodDep + ": " + aRetorno;
            aRetorno = aMsgLog;
            nContinuar = 0;
          }
      }

    Se (nContinuar = 1)
      {

        /*
        Valida saldo total do componente no deposito definido antes de chamar a baixa.
        Mesmo sem CodLot, precisa existir saldo suficiente no deposito.
        */
        TClaSql = "SELECT QtdEst WWQtdEst \
                     FROM E210EST \
                    WHERE CodEmp = :nCodEmp \
                      AND CodPro = :aCodCmp \
                      AND CodDer = :aDerCmp \
                      AND CodDep = :aCodDep";

        SQL_Criar(CCurEst);
        SQL_DefinirComando(CCurEst,TClaSql);
        SQL_DefinirInteiro(CCurEst,"nCodEmp",nCodEmp);
        SQL_DefinirAlfa(CCurEst,"aCodCmp",aCodCmp);
        SQL_DefinirAlfa(CCurEst,"aDerCmp",aDerCmp);
        SQL_DefinirAlfa(CCurEst,"aCodDep",aCodDep);
        SQL_AbrirCursor(CCurEst);

        nQtdEstCmp = 0;
        Se (SQL_EOF(CCurEst) = 0)
          SQL_RetornarFlutuante(CCurEst,"WWQtdEst",nQtdEstCmp);

        SQL_FecharCursor(CCurEst);
        SQL_Destruir(CCurEst);

        Se (nQtdEstCmp < nQtdUti)
          {
            ConverteMascara(2,nQtdEstCmp,aQtdEstCmp,"ZZZ.ZZZ.ZZ9,99");
            LimpaEspacos(aQtdEstCmp);
            ConverteMascara(2,nQtdUti,aQtdMovCmp,"ZZZ.ZZZ.ZZ9,99");
            LimpaEspacos(aQtdMovCmp);

            aRetorno = "Saldo em estoque no deposito " + aCodDep + " (" + aQtdEstCmp +
                       ") insuficiente para atender a quantidade de baixa do componente " + aCodCmp + " (" + aQtdMovCmp + ")";
            nContinuar = 0;
          }
      }

    Se (nContinuar = 1)
      {
        @ Parametros minimos da baixa. LotDes e CodLot sao adicionados separadamente abaixo. @
        aParApt = "CodOri=" + aCodOri +
                  ",NumOrp=" + aNumOrp +
                  ",CodEtg=" + aCodEtg +
                  ",CodCmp=" + aCodCmp +
                  ",CodDer=" + aDerCmp +
                  ",CodCcu=" + aCodCcu +
                  ",QtdUti=" + aQtdUti +
                  ",DatMov=" + aDatMov;

        @ LotDes representa o lote destino/produto acabado gravado pelo apontamento. @
        Se ((aLotDes <> "") e (aLotDes <> "0"))
          aParApt = aParApt + ",LotDes=" + aLotDes;

        /*
        CodLot representa o lote do componente.
        Se veio informado, envia sempre que achou/validou.
        Se foi buscado automaticamente, segue a excecao da familia 500.
        */
        Se ((nAchoLote = 1) e (((aCodLotInf <> "") e (aCodLotInf <> "0")) ou (aCodFam <> "500")))
          aParApt = aParApt + ",CodLot=" + aCodLot;

        aJsoEnv = aParApt;
      }

    Se (nContinuar = 1)
      {
        @ Usa o backup do baixar na OP criado pelas regras de apontamento. @
        TClaSql = "SELECT USU_BXAORP WWBxaOrp \
                     FROM E900CMO \
                    WHERE CODEMP = :nCodEmp \
                      AND CODORI = :aCodOri \
                      AND NUMORP = :nNumOrp \
                      AND CODETG = :nCodEtg \
                      AND CODCMP = :aCodCmp \
                      AND CODDER = :aDerCmp";

        SQL_Criar(CCurCmo);
        SQL_DefinirComando(CCurCmo,TClaSql);
        SQL_DefinirInteiro(CCurCmo,"nCodEmp",nCodEmp);
        SQL_DefinirAlfa(CCurCmo,"aCodOri",aCodOri);
        SQL_DefinirInteiro(CCurCmo,"nNumOrp",nNumOrp);
        SQL_DefinirInteiro(CCurCmo,"nCodEtg",nCodEtg);
        SQL_DefinirAlfa(CCurCmo,"aCodCmp",aCodCmp);
        SQL_DefinirAlfa(CCurCmo,"aDerCmp",aDerCmp);
        SQL_AbrirCursor(CCurCmo);

        Se (SQL_EOF(CCurCmo) = 0)
          {
            SQL_RetornarAlfa(CCurCmo,"WWBxaOrp",aBxaOrpOri);
            nTemCmo = 1;
          }

        SQL_FecharCursor(CCurCmo);
        SQL_Destruir(CCurCmo);

        Se (nTemCmo = 0)
          {
            aRetorno = "Componente " + aCodCmp + "/" + aDerCmp + " nao encontrado na OP " + aCodOri + "-" + aNumOrp;
            nContinuar = 0;
          }
        Senao
          {
            Se ((aBxaOrpOri = "") ou (aBxaOrpOri = " "))
              {
                aRetorno = "Backup USU_BxaOrp nao encontrado para o componente " + aCodCmp + "/" + aDerCmp;
                nContinuar = 0;
              }
          }
      }

    @ Qualquer validacao que zere nContinuar cai aqui e grava erro na fila. @
    Se (nContinuar = 0)
      {
        IniciarTransacao();
        ExecSQLEx(
        "UPDATE USU_TBXACMP \
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
        aDesRet = "Baixa de componente ERP.";
        aInfAdc = aInfLog + aRetorno;
        Fun_GravaLog();
      }

    Se (nContinuar = 1)
      {
        IniciarTransacao();
        aRetorno = "";

        @ Libera temporariamente o componente para permitir a baixa pela rotina padrao. @
        ExecSQLEx(
        "UPDATE E900CMO \
            SET BXAORP = 'S' \
          WHERE CODEMP = :nCodEmp \
            AND CODORI = :aCodOri \
            AND NUMORP = :nNumOrp \
            AND CODETG = :nCodEtg \
            AND CODCMP = :aCodCmp \
            AND CODDER = :aDerCmp",
        nErro,aMsgStr);

        Se (nErro = 1)
          {
            aRetorno = "Erro ao liberar baixa na OP: " + aMsgStr;
          }

        @ Chamada padrao de baixa. Se retornar "ERRO", desfaz e marca a fila com status 4. @
        Se (nErro = 0)
          {
            BaixarComponentes(aParApt,aRetorno);

            @ Restaura imediatamente pelo backup original do baixar na OP. @
            ExecSQLEx(
            "UPDATE E900CMO \
                SET BXAORP = USU_BXAORP \
              WHERE CODEMP = :nCodEmp \
                AND CODORI = :aCodOri \
                AND NUMORP = :nNumOrp \
                AND CODETG = :nCodEtg \
                AND CODCMP = :aCodCmp \
                AND CODDER = :aDerCmp \
                AND USU_BXAORP IS NOT NULL \
                AND USU_BXAORP <> ' '",
            nErro,aMsgStr);

            Se (nErro = 1)
              aRetorno = "Erro ao restaurar baixa na OP: " + aMsgStr;
          }

        PosicaoAlfa("ERRO",aRetorno,nPos);

        Se ((nPos > 0) ou (nErro = 1))
          {
            DeletarAlfa(aRetorno,249,999);
            DesfazerTransacao();

            IniciarTransacao();
            ExecSQLEx(
            "UPDATE USU_TBXACMP \
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
            aDesRet = "Baixa de componente ERP.";
            aInfAdc = aInfLog + aRetorno;
            Fun_GravaLog();
          }
        Senao
          {
            ExecSQLEx(
            "UPDATE USU_TBXACMP \
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
                aDesRet = "Baixa de componente ERP.";
                aInfAdc = aInfLog + "Erro ao atualizar status da pendencia: " + aMsgStr;
              }
            Senao
              {
                FinalizarTransacao();
                nStaInt = 3; @ 3 - Sucesso @
                aDesRet = "Baixa de componente ERP.";
                aInfAdc = aInfLog + "Processado com sucesso.";
              }

            Fun_GravaLog();
          }
      }

      }

    SQL_FecharCursor(CCurBxa);
    SQL_Destruir(CCurBxa);
    nCtdReg++;
  }

@ Ao final do lote, remove somente pendencias processadas com sucesso ha mais de 3 meses. @
IniciarTransacao();
ExecSQLEx(
"DELETE FROM USU_TBXACMP \
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
  sGrvLog.IdePrc = "BXC";
  sGrvLog.CodEmp = nCodEmp;
  sGrvLog.StaInt = nStaInt; @ 3-Processado, 4-Erro @
  sGrvLog.DesRet = aDesRet;
  sGrvLog.InfAdc = aInfAdc;
  sGrvLog.IdeUni = aIdeUni;
  sGrvLog.JsoEnv = aJsoEnv;
  sGrvLog.Executar();
Fim;
