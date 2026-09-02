Definir Alfa vaDados;
Definir Alfa vaRetorno;
Definir Alfa vaRet;
Definir Alfa aRetorno;
Definir Alfa wacao;
Definir Alfa aEmpresa;
Definir Alfa aCodOri;
Definir Alfa aNumOrp;
Definir Alfa aCodEtg;
Definir Alfa aSeqRot;
Definir Alfa aMaquina;
Definir Alfa aCodCre;
Definir Alfa aCodCcu;
Definir Alfa aSituacaoOP;
Definir Alfa aOperador;
Definir Alfa aMotivo;
Definir Alfa aDatIni;
Definir Alfa aHorIni;
Definir Alfa aDatFim;
Definir Alfa aHorFim;
Definir Alfa aProdOperador;
Definir Alfa aProdDatIni;
Definir Alfa aProdHorIni;
Definir Alfa aProdDatFim;
Definir Alfa aProdHorFim;
Definir Alfa aParametros;
Definir Alfa aParametroMov;
Definir Alfa aAchou;
Definir Alfa aObteve;
Definir Alfa aCursor;
Definir Alfa aSql;
Definir Alfa aEtapaAtual;
Definir Alfa aHora;
Definir Alfa aMinuto;
Definir Alfa aHoraOriginal;
Definir Alfa aSequenciaParada;
Definir Alfa aErroApontamento;

Definir Numero nCodEmp;
Definir Numero nNumOrp;
Definir Numero nCodEtg;
Definir Numero nSeqRot;
Definir Numero nNumCad;
Definir Numero nHora;
Definir Numero nMinuto;
Definir Numero nHorMov;
Definir Numero nUltimoHor;
Definir Numero nListaProducao;
Definir Numero nListaParada;
Definir Numero nErro;
Definir Numero nErroGeral;
Definir Numero nDiferenca;
Definir Numero nProdHorIni;
Definir Numero nMovimentosPacote;
Definir Numero nPacoteJaApontado;
Definir Numero nSequenciaParada;
Definir Numero nSuperiorProducao;
Definir Numero nSuperiorParada;

Definir Data dDatMov;
Definir Data dUltimaData;
Definir Data dProdDatIni;

Definir Funcao Fun_NormalizarHorario();
Definir Funcao Fun_ApontarMomento();
Definir Funcao Fun_NormalizarInicioConsulta();

@ Recebe um pacote de tempo do SIGMA e aponta producao e paradas na mesma transacao. @

vaRetorno = "";
vaRet = "";
wacao = "";
aRetorno = "";
aCodCcu = "";
nErroGeral = 0;
nUltimoHor = -1;
nPacoteJaApontado = 0;
MontaData(31,12,1900,dUltimaData);

ApontamentoTempos.tabelaEntradas.linhaatual = 0;
vaDados = ApontamentoTempos.tabelaEntradas.valor;
LimpaEspacos(vaDados);

ValorElementoJson(vaDados, "", "wacao", wacao);
ValorElementoJson(vaDados, "", "empresa", aEmpresa);
ValorElementoJson(vaDados, "", "origem", aCodOri);
ValorElementoJson(vaDados, "", "op", aNumOrp);
ValorElementoJson(vaDados, "", "estagio", aCodEtg);
ValorElementoJson(vaDados, "", "roteiro", aSeqRot);
ValorElementoJson(vaDados, "", "maquina", aMaquina);

Se (wacao <> "APONTAMENTO-TEMPOS")
  {
    nErroGeral = 1;
    aRetorno = "Acao inexistente!";
  }

Se (nErroGeral = 0)
  {
    AlfaParaInt(aEmpresa, nCodEmp);
    AlfaParaInt(aNumOrp, nNumOrp);
    AlfaParaInt(aCodEtg, nCodEtg);
    AlfaParaInt(aSeqRot, nSeqRot);
    TrocaEmpresaFilial(nCodEmp, 1);

    @ Busca o centro de custo do recurso recebido no payload. @
    aSql = "SELECT CODCRE WWCodCre, CODCCU WWCodCcu \
             FROM E725CRE \
            WHERE CODEMP = :nCodEmp \
              AND CODCRE = :aMaquina";
    SQL_Criar(aCursor);
    SQL_DefinirComando(aCursor, aSql);
    SQL_DefinirInteiro(aCursor, "nCodEmp", nCodEmp);
    SQL_DefinirAlfa(aCursor, "aMaquina", aMaquina);
    SQL_AbrirCursor(aCursor);
    Se (SQL_EOF(aCursor) = 0)
      {
        SQL_RetornarAlfa(aCursor, "WWCodCre", aCodCre);
        SQL_RetornarAlfa(aCursor, "WWCodCcu", aCodCcu);
      }
    SQL_FecharCursor(aCursor);
    SQL_Destruir(aCursor);

    EstaNulo(aCodCcu, nErro);
    Se (nErro = 1)
      {
        nErroGeral = 1;
        aRetorno = "Nao foi encontrado centro de custo para o recurso " + aMaquina + ".";
      }
  }

Se (nErroGeral = 0)
  {
    @ A OP precisa estar liberada ou em andamento. @
    aSituacaoOP = "";
    aSql = "SELECT SITORP WWSitOrp \
             FROM E900COP \
            WHERE CODEMP = :nCodEmp \
              AND CODORI = :aCodOri \
              AND NUMORP = :nNumOrp";
    SQL_Criar(aCursor);
    SQL_DefinirComando(aCursor, aSql);
    SQL_DefinirInteiro(aCursor, "nCodEmp", nCodEmp);
    SQL_DefinirAlfa(aCursor, "aCodOri", aCodOri);
    SQL_DefinirInteiro(aCursor, "nNumOrp", nNumOrp);
    SQL_AbrirCursor(aCursor);
    Se (SQL_EOF(aCursor) = 0)
      SQL_RetornarAlfa(aCursor, "WWSitOrp", aSituacaoOP);
    SQL_FecharCursor(aCursor);
    SQL_Destruir(aCursor);

    Se ((aSituacaoOP <> "L") e (aSituacaoOP <> "A"))
      {
        nErroGeral = 1;
        aRetorno = "OP nao esta liberada ou em andamento.";
      }
  }

Se (nErroGeral = 0)
  {
    @ Nao aponta se a OP ja possui inicio sem fim no ERP. @
    nDiferenca = 0;
    aSql = "SELECT SUM(CASE WHEN FIMORP = 'N' THEN 1 ELSE 0 END) \
                  - SUM(CASE WHEN FIMORP = 'S' THEN 1 ELSE 0 END) WWDiferenca \
             FROM E900EOQ \
            WHERE CODEMP = :nCodEmp \
              AND CODORI = :aCodOri \
              AND NUMORP = :nNumOrp \
           GROUP BY CODORI, NUMORP \
           HAVING SUM(CASE WHEN FIMORP = 'N' THEN 1 ELSE 0 END) \
                  <> SUM(CASE WHEN FIMORP = 'S' THEN 1 ELSE 0 END)";
    SQL_Criar(aCursor);
    SQL_UsarSQLSenior2(aCursor, 0);
    SQL_UsarAbrangencia(aCursor, 0);
    SQL_DefinirComando(aCursor, aSql);
    SQL_DefinirInteiro(aCursor, "nCodEmp", nCodEmp);
    SQL_DefinirAlfa(aCursor, "aCodOri", aCodOri);
    SQL_DefinirInteiro(aCursor, "nNumOrp", nNumOrp);
    SQL_AbrirCursor(aCursor);
    Se (SQL_EOF(aCursor) = 0)
      SQL_RetornarInteiro(aCursor, "WWDiferenca", nDiferenca);
    SQL_FecharCursor(aCursor);
    SQL_Destruir(aCursor);

    Se (nDiferenca > 0)
      {
        nErroGeral = 1;
        aRetorno = "Existe registro de inicio de OP sem registro de fim no ERP.";
      }
  }

@ O pacote deve conter exatamente um periodo de producao. @
Se (nErroGeral = 0)
  {
    ListaRegraCriarLista(nListaProducao);
    ListaRegraCarregarJson(nListaProducao, vaDados, "producoes", "operador;data_inicio;hora_inicio;data_fim;hora_fim");
    ListaRegraPrimeiro(nListaProducao, aAchou);
    Se (aAchou = "S")
      {
        ListaRegraObterValorAlfa(nListaProducao, "operador", aOperador, aObteve);
        ListaRegraObterValorAlfa(nListaProducao, "data_inicio", aDatIni, aObteve);
        ListaRegraObterValorAlfa(nListaProducao, "hora_inicio", aHorIni, aObteve);
        ListaRegraObterValorAlfa(nListaProducao, "data_fim", aDatFim, aObteve);
        ListaRegraObterValorAlfa(nListaProducao, "hora_fim", aHorFim, aObteve);
        aProdOperador = aOperador;
        aProdDatIni = aDatIni;
        aProdHorIni = aHorIni;
        aProdDatFim = aDatFim;
        aProdHorFim = aHorFim;
        ListaRegraProximo(nListaProducao, aAchou);
        Se (aAchou = "S")
          {
            nErroGeral = 1;
            aRetorno = "O pacote deve possuir somente um periodo de producao.";
          }
      }
    Senao
      {
        nErroGeral = 1;
        aRetorno = "O pacote nao possui periodo de producao.";
      }
    ListaRegraLiberarLista();
  }

Se (nErroGeral = 0)
  {
    @ O inicio identifica um pacote de tempo ja integrado. @
    Fun_NormalizarInicioConsulta();

    AlfaParaInt(aProdOperador, nNumCad);
    nMovimentosPacote = 0;

    @ Inicio e fim com quantidade zero identificam o pacote ja integrado. @
    aSql = "SELECT COUNT(1) WWMovimentos \
             FROM E900EOQ \
            WHERE CODEMP = :nCodEmp \
              AND CODORI = :aCodOri \
              AND NUMORP = :nNumOrp \
              AND CODETG = :nCodEtg \
              AND SEQROT = :nSeqRot \
              AND CODCRE = :aCodCre \
              AND NUMCAD = :nNumCad \
              AND QTDRE1 = 0 \
              AND DATINI = :dProdDatIni \
              AND HORINI = :nProdHorIni";
    SQL_Criar(aCursor);
    SQL_UsarSQLSenior2(aCursor, 0);
    SQL_UsarAbrangencia(aCursor, 0);
    SQL_DefinirComando(aCursor, aSql);
    SQL_DefinirInteiro(aCursor, "nCodEmp", nCodEmp);
    SQL_DefinirAlfa(aCursor, "aCodOri", aCodOri);
    SQL_DefinirInteiro(aCursor, "nNumOrp", nNumOrp);
    SQL_DefinirInteiro(aCursor, "nCodEtg", nCodEtg);
    SQL_DefinirInteiro(aCursor, "nSeqRot", nSeqRot);
    SQL_DefinirAlfa(aCursor, "aCodCre", aCodCre);
    SQL_DefinirInteiro(aCursor, "nNumCad", nNumCad);
    SQL_DefinirData(aCursor, "dProdDatIni", dProdDatIni);
    SQL_DefinirInteiro(aCursor, "nProdHorIni", nProdHorIni);
    SQL_AbrirCursor(aCursor);
    Se (SQL_EOF(aCursor) = 0)
      SQL_RetornarInteiro(aCursor, "WWMovimentos", nMovimentosPacote);
    SQL_FecharCursor(aCursor);
    SQL_Destruir(aCursor);

    Se (nMovimentosPacote > 0)
      nPacoteJaApontado = 1;
  }

Se ((nErroGeral = 0) e (nPacoteJaApontado = 0))
  {
    @ O superior da producao sera usado se a parada vier de outro superior. @
    AlfaParaInt(aProdOperador, nNumCad);
    nSuperiorProducao = 0;
    aSql = "SELECT SUPIME WWSupIme \
             FROM E906OPE \
            WHERE CODEMP = :nCodEmp \
              AND NUMCAD = :nNumCad";
    SQL_Criar(aCursor);
    SQL_DefinirComando(aCursor, aSql);
    SQL_DefinirInteiro(aCursor, "nCodEmp", nCodEmp);
    SQL_DefinirInteiro(aCursor, "nNumCad", nNumCad);
    SQL_AbrirCursor(aCursor);
    Se (SQL_EOF(aCursor) = 0)
      SQL_RetornarInteiro(aCursor, "WWSupIme", nSuperiorProducao);
    SQL_FecharCursor(aCursor);
    SQL_Destruir(aCursor);

    Se (nSuperiorProducao <= 0)
      {
        nErroGeral = 1;
        aRetorno = "Operador da producao nao possui superior cadastrado.";
      }
  }

Se ((nErroGeral = 0) e (nPacoteJaApontado = 0))
  {
    MontaData(31,12,1900,dUltimaData);
    nUltimoHor = -1;
    IniciarTransacao();

    @ Inicio da producao. @
    aOperador = aProdOperador;
    AlfaParaData(aProdDatIni, dDatMov);
    aHora = aProdHorIni;
    aEtapaAtual = "inicio da producao";
    Fun_NormalizarHorario();
    Se (nErroGeral = 0)
      {
        aParametros = "CodOri=" + aCodOri +
                      ",NumOrp=" + aNumOrp +
                      ",CodEtg=" + aCodEtg +
                      ",SeqRot=" + aSeqRot +
                      ",NumCad=" + aOperador +
                      ",QtdRe1=0" +
                      ",QtdRfg=0" +
                      ",CodCcu=" + aCodCcu +
                      ",CodCre=" + aCodCre;
        Fun_ApontarMomento();
      }

    @ Cada parada gera seu inicio e fim entre os dois apontamentos de producao. @
    Se (nErroGeral = 0)
      {
        ListaRegraCriarLista(nListaParada);
        ListaRegraCarregarJson(nListaParada, vaDados, "paradas", "operador;motivo;data_inicio;hora_inicio;data_fim;hora_fim");
        ListaRegraPrimeiro(nListaParada, aAchou);
        nSequenciaParada = 0;
        Enquanto ((aAchou = "S") e (nErroGeral = 0))
          {
            nSequenciaParada++;
            IntParaAlfa(nSequenciaParada, aSequenciaParada);
            ListaRegraObterValorAlfa(nListaParada, "operador", aOperador, aObteve);
            ListaRegraObterValorAlfa(nListaParada, "motivo", aMotivo, aObteve);
            ListaRegraObterValorAlfa(nListaParada, "data_inicio", aDatIni, aObteve);
            ListaRegraObterValorAlfa(nListaParada, "hora_inicio", aHorIni, aObteve);
            ListaRegraObterValorAlfa(nListaParada, "data_fim", aDatFim, aObteve);
            ListaRegraObterValorAlfa(nListaParada, "hora_fim", aHorFim, aObteve);
            AlfaParaInt(aOperador, nNumCad);

            Se (aMotivo = "")
              {
                nErroGeral = 1;
                aRetorno = "Parada com motivo nao informado.";
              }
            Senao
              {
                @ A parada deve ser apontada pelo superior do operador informado. @
                nSuperiorParada = 0;
                aSql = "SELECT SUPIME WWSupIme \
                         FROM E906OPE \
                        WHERE CODEMP = :nCodEmp \
                          AND NUMCAD = :nNumCad";
                SQL_Criar(aCursor);
                SQL_DefinirComando(aCursor, aSql);
                SQL_DefinirInteiro(aCursor, "nCodEmp", nCodEmp);
                SQL_DefinirInteiro(aCursor, "nNumCad", nNumCad);
                SQL_AbrirCursor(aCursor);
                Se (SQL_EOF(aCursor) = 0)
                  SQL_RetornarInteiro(aCursor, "WWSupIme", nSuperiorParada);
                SQL_FecharCursor(aCursor);
                SQL_Destruir(aCursor);

                Se (nSuperiorParada <= 0)
                  {
                    nErroGeral = 1;
                    aRetorno = "Operador da parada nao possui superior cadastrado.";
                  }
                Senao
                  {
                    Se (nSuperiorParada <> nSuperiorProducao)
                      nSuperiorParada = nSuperiorProducao;
                    IntParaAlfa(nSuperiorParada, aOperador);
                aParametros = "CodOri=" + aCodOri +
                              ",NumOrp=" + aNumOrp +
                              ",CodEtg=" + aCodEtg +
                              ",SeqRot=" + aSeqRot +
                              ",CodCre=" + aCodCre +
                              ",CodMtv=" + aMotivo +
                              ",NumCad=" + aOperador +
                              ",TipOpr=2";

                AlfaParaData(aDatIni, dDatMov);
                aHora = aHorIni;
                aEtapaAtual = "inicio da parada " + aSequenciaParada;
                Fun_NormalizarHorario();
                Se (nErroGeral = 0)
                  Fun_ApontarMomento();

                Se (nErroGeral = 0)
                  {
                    AlfaParaData(aDatFim, dDatMov);
                    aHora = aHorFim;
                    aEtapaAtual = "fim da parada " + aSequenciaParada;
                    Fun_NormalizarHorario();
                    Se (nErroGeral = 0)
                      Fun_ApontarMomento();
                  }
                  }
              }

            ListaRegraProximo(nListaParada, aAchou);
          }
        ListaRegraLiberarLista();
      }

    @ Fim da producao. @
    Se (nErroGeral = 0)
      {
        aOperador = aProdOperador;
        AlfaParaData(aProdDatFim, dDatMov);
        aHora = aProdHorFim;
        aEtapaAtual = "fim da producao";
        Fun_NormalizarHorario();
        Se (nErroGeral = 0)
          {
            aParametros = "CodOri=" + aCodOri +
                          ",NumOrp=" + aNumOrp +
                          ",CodEtg=" + aCodEtg +
                          ",SeqRot=" + aSeqRot +
                          ",NumCad=" + aOperador +
                          ",QtdRe1=0" +
                          ",QtdRfg=0" +
                          ",CodCcu=" + aCodCcu +
                          ",CodCre=" + aCodCre;
            Fun_ApontarMomento();
          }
      }

    Se (nErroGeral = 1)
      DesfazerTransacao();
    Senao
      FinalizarTransacao();
  }

Se (nErroGeral = 1)
  vaRet = "{|status|:|ERRO|,|message|:|" + aRetorno + "|}";
Senao
  Se (nPacoteJaApontado = 1)
    vaRet = "{|status|:|OK|,|message|:|Pacote de tempo ja apontado.|}";
  Senao
    vaRet = "{|status|:|OK|,|message|:|Apontamento de tempos processado.|}";

vaRetorno = vaRet;
SubstAlfa("|", "\"", vaRetorno);
ApontamentoTempos.waRetorno = vaRetorno;


Funcao Fun_NormalizarHorario();
  {
    @ O ERP trabalha por minuto: 00:00 vira 00:01 e cada evento fica apos o anterior. @
    aHoraOriginal = aHora;
    aHora = aHoraOriginal;
    CopiarAlfa(aHora, 1, 2);
    aMinuto = aHoraOriginal;
    CopiarAlfa(aMinuto, 4, 2);
    AlfaParaInt(aHora, nHora);
    AlfaParaInt(aMinuto, nMinuto);
    nHorMov = (nHora * 60) + nMinuto;

    Se (nHorMov = 0)
      nHorMov = 1;

    Se (dDatMov < dUltimaData)
      {
        nErroGeral = 1;
        aRetorno = "Horario do " + aEtapaAtual + " anterior ao apontamento anterior do pacote.";
      }

    Se ((nErroGeral = 0) e (dDatMov = dUltimaData) e (nHorMov <= nUltimoHor))
      {
        nHorMov = nUltimoHor + 1;
        Se (nHorMov > 1439)
          {
            dDatMov++;
            nHorMov = 1;
          }
      }

    Se (nErroGeral = 0)
      {
        ConverteMascara(3, dDatMov, aDatIni, "DD/MM/YYYY");
        ConverteMascara(4, nHorMov, aHora, "hh:mm:ss");
        LimpaEspacos(aDatIni);
        LimpaEspacos(aHora);
        dUltimaData = dDatMov;
        nUltimoHor = nHorMov;
      }
  }


Funcao Fun_ApontarMomento();
  {
    aParametroMov = aParametros + ",DatMov=" + aDatIni + ",HorMov=" + aHora;
    ApontarOPs(aParametroMov, aRetorno);
    PosicaoAlfa("ERRO", aRetorno, nErro);
    Se (nErro > 0)
      {
        nErroGeral = 1;
        aErroApontamento = aRetorno;
        CopiarAlfa(aErroApontamento, 0, 220);
        aRetorno = "Erro no " + aEtapaAtual + ": " + aErroApontamento;
      }
  }


Funcao Fun_NormalizarInicioConsulta();
  {
    @ Aplica somente o ajuste de 00:00 ao inicio usado como marcador do pacote. @
    MontaData(31,12,1900,dUltimaData);
    nUltimoHor = -1;

    AlfaParaData(aProdDatIni, dDatMov);
    aHora = aProdHorIni;
    aEtapaAtual = "inicio da producao";
    Fun_NormalizarHorario();
    dProdDatIni = dDatMov;
    nProdHorIni = nHorMov;
  }
