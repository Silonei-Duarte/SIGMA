@ Importa saldos de paletes do WMS para USU_TPALWMS. @
@ Entrada esperada: {"wacao":"IMPORTAR-PALETES","chave":"","valor":""}. @

Definir Alfa vaDados;
Definir Alfa wacao;
Definir Alfa chave;
Definir Alfa valor;
Definir Alfa vaRet;
Definir Alfa vaRetorno;
Definir Alfa vaMsg;
Definir Alfa aCurQtd;
Definir Alfa aCurInserir;
Definir Alfa TClaSql;
Definir Data dDatSis;
Definir Numero nQtdAtualizados;
Definir Numero nEntrouAcao;
Definir Numero nErro;
Definir Numero nHorSis;

vaDados = "";
wacao = "";
chave = "";
valor = "";
vaRet = "";
vaMsg = "";
nQtdAtualizados = 0;
nEntrouAcao = 0;
nErro = 0;
dDatSis = DatSis;
nHorSis = HorSis;

ImportaWMS.tabelaEntradas.linhaatual = 0;
vaDados = ImportaWMS.tabelaEntradas.valor;
LimpaEspacos(vaDados);
ValorElementoJson(vaDados, "", "wacao", wacao);
ValorElementoJson(vaDados, "", "chave", chave);
ValorElementoJson(vaDados, "", "valor", valor);

Se (wacao = "IMPORTAR-PALETES")
  {
    nEntrouAcao = 1;

    IniciarTransacao();
    ExecSqlEx("DELETE FROM USU_TPALWMS", nErro, vaMsg);

    Se (nErro = 0)
      {
        SQL_Criar(aCurInserir);
        SQL_UsarSQLSenior2(aCurInserir, 0);
        SQL_UsarAbrangencia(aCurInserir, 0);
        TClaSql = "INSERT INTO USU_TPALWMS (USU_CODEMP, USU_PALWMS, USU_QTDDIS, USU_CODLOT, USU_CODCMP, \
          USU_DERCMP, USU_DATGER, USU_HORGER, USU_LOGPRC, USU_DATLOG, USU_HORLOG, USU_ARMWMS) \
          SELECT 1, e.ID, SUM(e.QTY), e.LOTTABLE01, p.CODPRO, NVL(d.CODDER, ' '), \
                 :dDatSis, :nHorSis, \
                 'Inserido', :dDatSis, :nHorSis, \
                 'wmwhse1' \
            FROM wmwhse1.v_XCLotxLocxId_Lottables@SQLDBLINK e \
            INNER JOIN e075pro p ON p.CODEMP = 1 \
               AND p.CODFAM IN ('621','622','623','624','626','627','628') \
               AND (e.SKU = p.CODPRO OR e.SKU LIKE p.CODPRO || '-%') \
            LEFT JOIN e075der d ON d.CODEMP = p.CODEMP AND d.CODPRO = p.CODPRO \
               AND ((e.SKU = p.CODPRO AND d.CODDER = ' ') OR e.SKU = p.CODPRO || '-' || d.CODDER) \
           WHERE e.QTY > 0 AND e.LOTTABLE01 > ' ' AND e.ID > ' ' AND d.CODDER IS NOT NULL \
           GROUP BY e.ID, e.LOTTABLE01, p.CODPRO, NVL(d.CODDER, ' ')";
        SQL_DefinirComando(aCurInserir, TClaSql);
        SQL_DefinirData(aCurInserir, "dDatSis", dDatSis);
        SQL_DefinirInteiro(aCurInserir, "nHorSis", nHorSis);
        SQL_AbrirCursor(aCurInserir);
        SQL_FecharCursor(aCurInserir);
        SQL_Destruir(aCurInserir);
      }

    Se (nErro = 1)
      {
        DesfazerTransacao();
        vaRet = "{|status|:|ERRO|,|message|:|" + vaMsg + "|}";
      }
    Senao
      {
        SQL_Criar(aCurQtd);
        TClaSql = "SELECT COUNT(*) TOTAL_REGISTROS FROM USU_TPALWMS";
        SQL_DefinirComando(aCurQtd, TClaSql);
        SQL_AbrirCursor(aCurQtd);
        Se (SQL_EOF(aCurQtd) = 0)
          SQL_RetornarInteiro(aCurQtd, "TOTAL_REGISTROS", nQtdAtualizados);
        SQL_FecharCursor(aCurQtd);
        SQL_Destruir(aCurQtd);
        FinalizarTransacao();
        IntParaAlfa(nQtdAtualizados, vaMsg);
        vaRet = "{|status|:|OK|,|message|:|Importacao de paletes concluida.|,|total_registros|:" + vaMsg + "}";
      }
  }

Se (nEntrouAcao = 0)
  vaRet = "{|status|:|ERRO|,|message|:|Acao inexistente.|}";

vaRetorno = vaRet;
SubstAlfa("|", "\"", vaRetorno);
ImportaWMS.waRetorno = vaRetorno;
