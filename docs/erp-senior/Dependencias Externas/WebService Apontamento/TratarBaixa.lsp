/*
Recebe uma baixa originada da tela Apontamentos V3 e grava a pendencia na
USU_TBXACMP. A execucao fisica da baixa permanece na regra BaixaComponenteERP.

Regras de quantidade:
- Repesagem = S: usa o saldo atual do lote menos 1, preservando saldo 1.
- ConsumoTotal = S: usa todo o saldo atual do lote.
- Ambos = S: erro, sem inserir pendencia.
- Ambos = N: usa a quantidade recebida no webservice.
*/

Definir Alfa vaDados;
Definir Alfa vaRetorno;
Definir Alfa vaRet;
Definir Alfa vaMsg;
Definir Alfa aCodEmp;
Definir Alfa aCodOri;
Definir Alfa aNumOrp;
Definir Alfa aCodEtg;
Definir Alfa aSeqRot;
Definir Alfa aLotDes;
Definir Alfa aCodCmp;
Definir Alfa aDerCmp;
Definir Alfa aQtdUti;
Definir Alfa aCodCre;
Definir Alfa aDatMov;
Definir Alfa aHorMov;
Definir Alfa aCodLot;
Definir Alfa aRepesagem;
Definir Alfa aConsumoTotal;
Definir Alfa aIdeUni;
Definir Alfa aLogInc;
Definir Alfa aSql;
Definir Alfa aMsgStr;
Definir Alfa aHora;
Definir Alfa aMin;
Definir Alfa CCurLot;
Definir Alfa CCurOrdem;
Definir Numero nCodEmp;
Definir Numero nNumOrp;
Definir Numero nCodEtg;
Definir Numero nSeqRot;
Definir Numero nHora;
Definir Numero nMin;
Definir Numero nHorMov;
Definir Numero nErro;
Definir Numero nQtdUti;
Definir Numero nSaldoLote;
Definir Numero nAchouSaldo;
Definir Numero nRetornoOk;
Definir Numero nExisteMesmoHorario;
Definir Data dDatMov;

vaRetorno = "";
vaRet = "";
vaMsg = "";
nErro = 0;
nAchouSaldo = 0;
nSaldoLote = 0;
nRetornoOk = 0;
nExisteMesmoHorario = 0;

@ Captura o JSON unico recebido na tabela wdados. @
TratarBaixa.tabelaEntradas.linhaAtual = 0;
vaDados = TratarBaixa.tabelaEntradas.valor;
LimpaEspacos(vaDados);

ValorElementoJson(vaDados, "", "codemp", aCodEmp);
ValorElementoJson(vaDados, "", "origem", aCodOri);
ValorElementoJson(vaDados, "", "numorp", aNumOrp);
ValorElementoJson(vaDados, "", "codetg", aCodEtg);
ValorElementoJson(vaDados, "", "seqrot", aSeqRot);
ValorElementoJson(vaDados, "", "lotdes", aLotDes);
ValorElementoJson(vaDados, "", "codcmp", aCodCmp);
ValorElementoJson(vaDados, "", "dercmp", aDerCmp);
ValorElementoJson(vaDados, "", "qtduti", aQtdUti);
ValorElementoJson(vaDados, "", "codigo_integrador", aCodCre);
ValorElementoJson(vaDados, "", "datmov", aDatMov);
ValorElementoJson(vaDados, "", "hormov", aHorMov);
ValorElementoJson(vaDados, "", "codlot", aCodLot);
ValorElementoJson(vaDados, "", "repesagem", aRepesagem);
ValorElementoJson(vaDados, "", "consumototal", aConsumoTotal);

LimpaEspacos(aCodEmp);
LimpaEspacos(aCodOri);
LimpaEspacos(aNumOrp);
LimpaEspacos(aCodEtg);
LimpaEspacos(aSeqRot);
LimpaEspacos(aCodCmp);
LimpaEspacos(aDerCmp);
LimpaEspacos(aCodCre);
LimpaEspacos(aDatMov);
LimpaEspacos(aHorMov);
LimpaEspacos(aCodLot);
LimpaEspacos(aRepesagem);
LimpaEspacos(aConsumoTotal);

Se (aRepesagem = "")
  aRepesagem = "N";
Se (aConsumoTotal = "")
  aConsumoTotal = "N";

Se ((aCodEmp = "") ou (aCodOri = "") ou (aNumOrp = "") ou (aCodEtg = "") ou
    (aSeqRot = "") ou (aCodCmp = "") ou (aCodLot = "") ou (aCodCre = "") ou
    (aDatMov = "") ou (aHorMov = ""))
  vaMsg = "Campos obrigatorios nao informados para tratar baixa.";

Se ((vaMsg = "") e ((aRepesagem <> "S") e (aRepesagem <> "N")))
  vaMsg = "Indicador repesagem invalido. Use S ou N.";

Se ((vaMsg = "") e ((aConsumoTotal <> "S") e (aConsumoTotal <> "N")))
  vaMsg = "Indicador consumototal invalido. Use S ou N.";

Se ((vaMsg = "") e (aRepesagem = "S") e (aConsumoTotal = "S"))
  vaMsg = "Repesagem e consumo total nao podem ser S ao mesmo tempo. Corrija a origem do registro.";

Se (vaMsg = "")
  {
    AlfaParaInt(aCodEmp, nCodEmp);
    AlfaParaInt(aNumOrp, nNumOrp);
    AlfaParaInt(aCodEtg, nCodEtg);
    AlfaParaInt(aSeqRot, nSeqRot);
    AlfaParaData(aDatMov, dDatMov);

    aHora = aHorMov;
    CopiarAlfa(aHora, 1, 2);
    aMin = aHorMov;
    CopiarAlfa(aMin, 4, 2);
    AlfaParaInt(aHora, nHora);
    AlfaParaInt(aMin, nMin);
    nHorMov = (nHora * 60) + nMin;

    TrocaEmpresaFilial(nCodEmp, 1);

    @ Repesagem e consumo total precisam conhecer o saldo real do lote. @
    Se ((aRepesagem = "S") ou (aConsumoTotal = "S"))
      {
        aSql = "SELECT SUM(QtdEst) WWQtdEst \
                  FROM E210DLS \
                 WHERE CodEmp = :nCodEmp \
                   AND CodLot = :aCodLot \
                   AND CodPro = :aCodCmp \
                   AND CodDer = :aDerCmp \
                   AND QtdEst > 0 \
                   AND CodDep <> '08.01'";

        SQL_Criar(CCurLot);
        SQL_UsarSQLSenior2(CCurLot,0);
        SQL_UsarAbrangencia(CCurLot,0);
        SQL_DefinirComando(CCurLot, aSql);
        SQL_DefinirInteiro(CCurLot, "nCodEmp", nCodEmp);
        SQL_DefinirAlfa(CCurLot, "aCodLot", aCodLot);
        SQL_DefinirAlfa(CCurLot, "aCodCmp", aCodCmp);
        SQL_DefinirAlfa(CCurLot, "aDerCmp", aDerCmp);
        SQL_AbrirCursor(CCurLot);

        Se (SQL_EOF(CCurLot) = 0)
          {
            SQL_RetornarFlutuante(CCurLot, "WWQtdEst", nSaldoLote);
            Se (nSaldoLote > 0)
              nAchouSaldo = 1;
          }

        SQL_FecharCursor(CCurLot);
        SQL_Destruir(CCurLot);

        @ Repesagem idempotente: se o lote ja esta com saldo 1 ou menor. @
        @ Nao cria nova pendencia e responde sucesso para encerrar o log SIGMA. @
        Se ((aRepesagem = "S") e (nSaldoLote <= 1))
          {
            vaMsg = "Lote ja esta para repesagem com saldo 1 ou menor.";
            nRetornoOk = 1;
          }
        Senao
          {
            Se (nAchouSaldo = 0)
              vaMsg = "Lote informado nao possui saldo disponivel para baixa.";
          }
      }

    Se ((vaMsg = "") e (aRepesagem = "S"))
      nQtdUti = nSaldoLote - 1;
    Senao
      {
        Se ((vaMsg = "") e (aConsumoTotal = "S"))
          nQtdUti = nSaldoLote;
        Senao
          {
            Se (vaMsg = "")
              {
                SubstAlfa(".", ",", aQtdUti);
                AlfaParaDecimal(aQtdUti, nQtdUti);
                Se (nQtdUti <= 0)
                  vaMsg = "Quantidade utilizada deve ser maior que zero.";
              }
          }
      }
  }

Se (vaMsg = "")
  {
    @ Mantem a sequencia de baixas do mesmo lote quando chegam no mesmo minuto. @
    nExisteMesmoHorario = 1;
    Enquanto (nExisteMesmoHorario > 0)
      {
        nExisteMesmoHorario = 0;
        SQL_Criar(CCurOrdem);
        SQL_UsarSQLSenior2(CCurOrdem,0);
        SQL_UsarAbrangencia(CCurOrdem,0);
        SQL_DefinirComando(CCurOrdem, "SELECT COUNT(1) WWQTD \
                                        FROM USU_TBXACMP \
                                       WHERE USU_CODEMP = :nCodEmp \
                                         AND USU_CODLOT = :aCodLot \
                                         AND USU_DATMOV = :dDatMov \
                                         AND USU_HORMOV = :nHorMov");
        SQL_DefinirInteiro(CCurOrdem, "nCodEmp", nCodEmp);
        SQL_DefinirAlfa(CCurOrdem, "aCodLot", aCodLot);
        SQL_DefinirData(CCurOrdem, "dDatMov", dDatMov);
        SQL_DefinirInteiro(CCurOrdem, "nHorMov", nHorMov);
        SQL_AbrirCursor(CCurOrdem);
        Se (SQL_EOF(CCurOrdem) = 0)
          SQL_RetornarInteiro(CCurOrdem, "WWQTD", nExisteMesmoHorario);
        SQL_FecharCursor(CCurOrdem);
        SQL_Destruir(CCurOrdem);

        Se (nExisteMesmoHorario > 0)
          {
            nHorMov++;
            Se (nHorMov > 1439)
              {
                dDatMov++;
                nHorMov = 1;
              }
          }
      }

    ObterGuid(aIdeUni);
    Se (aRepesagem = "S")
      aLogInc = "Inserido por TRATAR-BAIXA - REPESAGEM";
    Senao
      {
        Se (aConsumoTotal = "S")
          aLogInc = "Inserido por TRATAR-BAIXA - CONSUMO TOTAL";
        Senao
          aLogInc = "Inserido por TRATAR-BAIXA - CONSUMO COMUM";
      }

    IniciarTransacao();
    ExecSqlEx(
    "INSERT INTO USU_TBXACMP (USU_CODEMP, USU_CODORI, USU_NUMORP, USU_CODETG, \
        USU_CODCMP, USU_DERCMP, USU_LOTDES, USU_QTDUTI, USU_LOGINC, \
        USU_CODCRE, USU_CODLOT, USU_DATMOV, USU_HORMOV, USU_SITPEN, USU_IDEUNI) \
      VALUES (:nCodEmp, :aCodOri, :nNumOrp, :nCodEtg, \
        :aCodCmp, :aDerCmp, :aLotDes, :nQtdUti, :aLogInc, \
        :aCodCre, :aCodLot, :dDatMov, :nHorMov, 1, :aIdeUni)",
    nErro, aMsgStr);

    Se (nErro = 1)
      {
        DesfazerTransacao();
        vaMsg = "ERRO ao gravar pendencia de baixa: " + aMsgStr;
      }
    Senao
      {
        FinalizarTransacao();
        vaMsg = "Pendencia de baixa gravada com sucesso.";
        nRetornoOk = 1;
      }
  }

Se (nRetornoOk = 1)
  vaRet = "{|status|:|OK|,|message|:|" + vaMsg + "|}";
Senao
  vaRet = "{|status|:|ERRO|,|message|:|" + vaMsg + "|}";

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
TratarBaixa.waRetorno = vaRetorno;
