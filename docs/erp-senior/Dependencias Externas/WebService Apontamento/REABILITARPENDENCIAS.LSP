@==================================================================================================@
@    SISTEMA: Senior Gestão Empresarial                                                            @
@    EVENTO: Webservice                                                                            @
@--------------------------------------------------------------------------------------------------@
@    DESENVOLVEDOR: André Euzébio (Senior)                    DATA: 21/09/2025                     @
@--------------------------------------------------------------------------------------------------@
@    FINALIDADE:                                                                                   @
@    - Esta porta tem como objetivo setar o registro do log para reabilitado, ela serve para ser   @
@      adaptada de acordo com a necessidade da rotina do cliente, e caso possua uma integração     @
@      com estrutura de filas, é possivel implementar o código nesta porta para que os registros   @
@      sejam reabilitados durante a utilização da tela customizada FLogCtm_F, botão                @
@      Reabilitar Selecionados                                                                     @  
@==================================================================================================@
@                                    REVISÕES / ALTERAÇÔES                                         @
@--------------------------------------------------------------------------------------------------@
@    DESENVOLVEDOR: André Euzébio                             DATA: 09/10/2025                     @
@    DESCRIÇÃO: Implementado reabilitação para as tags TRA, CPG e FPG                              @
@                                                                                                  @
@    DESENVOLVEDOR: André Euzébio                             DATA: 20/10/2025                     @
@    DESCRIÇÃO: Implementado reabilitação para as tags REP                                         @
@                                                                                                  @
@    DESENVOLVEDOR: André Euzébio                             DATA: 05/11/2025                     @
@    DESCRIÇÃO: Adaptando a regra para salvar no log a chave do registro completa e melhorar a     @ 
@               integridade e garantir a reabilitação das pendencias corretas.                     @
@                                                                                                  @
@    DESENVOLVEDOR: André Euzébio                             DATA: 07/11/2025                     @
@    DESCRIÇÃO: Ajuste na regra para receber somente o código do processo e varrer a tabela        @
@               da grid com base no processo, garantindo que não haja problemas                    @
@==================================================================================================@
Definir interno.custom.senior.logs.ReabilitarPendencias this;

Definir Funcao fGravaLogIntegracao();
Definir Funcao fReabilitaRegistro();

@Definir Cursor cur_tlogctmaux;@
Definir Cursor cur_pendencia;
Definir Alfa TClaSql;

Definir Alfa sIdeUni;
Definir Alfa sIdePrc;
Definir Alfa aSitIex;

Definir Alfa sMensagemRetorno;
Definir Alfa sNomArq;
Definir Alfa sNomReg; @ Nome do processo para mensageria log @
Definir Alfa sCodReg; @ Código chave do registro para mensageria log @
Definir Alfa sChvReg; @ Chave do registro para mensageria log @
Definir Numero nAchouXcr; @ usado só pelo IdePrc XCR, que tem pendência em duas tabelas @

nCodUsu = this.CodUsu;
nCodPrc = this.CodPrc;

nStatusExecucao = 0; @ Sucesso @

Se (nCodPrc = 0)
{
  nStatusExecucao = 1; @ Erro @
  this.Retorno.CriarLinha();
  this.Retorno.Status = 1; @ Erro @  
  this.Retorno.mensagemRetorno = "Parâmetro CodPrc é obrigatório.";
}

Se (nStatusExecucao = 0)
{
  Definir Alfa CCurLogAux;
  @- Cursor para varrer quais identificadores de processo que foram checados em tela -@
  TClaSql = "Select USU_CodPrc, USU_IdePrc \            
                From USU_TLogCtmAux \       
              Where 1=2 \                   
             Union All \                   
             Select Max(USU_CodPrc), USU_IdePrc \
                From USU_TLogCtmAux \
              Where USU_CodUsu = :nCodUsu \
                And USU_CodPrc = :nCodPrc \
                And USU_RegSel = 'T' \
              Group By USU_IdePrc";
  SQL_Criar(CCurLogAux);
  SQL_UsarAbrangencia(CCurLogAux, 0);
  SQL_UsarSQLSenior2(CCurLogAux, 0);
  SQL_DefinirComando(CCurLogAux, TClaSql);
  SQL_DefinirInteiro(CCurLogAux, "nCodUsu", nCodUsu);
  SQL_DefinirInteiro(CCurLogAux, "nCodPrc", nCodPrc);
  SQL_AbrirCursor(CCurLogAux);
  Se (SQL_EOF(CCurLogAux) <> 0)
  {
    nStatusExecucao = 1; @ Erro @
    this.Retorno.CriarLinha();
    this.Retorno.Status = 1; @ Erro @  
    this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";  
  }
  Senao
  {
    Enquanto (SQL_EOF(CCurLogAux) = 0)
    {
      SQL_RetornarALfa(CCurLogAux, "USU_IdePrc", sIdePrc);
    
      @--- Integração Salesforce ---@
      fReabilitaRegistro();
      @--- Fim Integração Salesforce ---@    
        
      Se (nStatusExecucao = 1)
      {
        this.Retorno.CriarLinha();
        this.Retorno.Status = 1; @ Erro @    
        this.Retorno.mensagemRetorno = "Reabilitação de pendencias para o identificador " + sIdePrc + " não implementada no serviço interno.custom.senior.logs.ReabilitarPendencias.";
      }  
      SQL_Proximo(CCurLogAux);
    }
  } 
  SQL_Destruir(CCurLogAux);
}  

Funcao fReabilitaRegistro();
{
  @ Função responsável pela reabilitação dos registros da integração Salesforce @
  @ implementada no cliente Zeus do Brasil LTDA                                 @

  nStatusExecucao = 1; @ Força erro caso não encontrar implementação de reabilitação para integração @

  Se (nCodPrc = 1) 
  {
    @--- BCR - Baixa Consumo Real ---@
    Se (sIdePrc = "BCR") {
      nStatusExecucao = 0; @ Encontrado implementação @
      sNomReg = "Baixa Consumo Real";
      
      cur_pendencia.sql "select usu_t000exp.usu_ideuni,                        \ 
                                usu_t000exp.usu_sitpen                             \  
                           from usu_tlogctmaux,                                        \
                                usu_t000exp                                        \
                          where usu_tlogctmaux.usu_ideuni = usu_t000exp.usu_ideuni \
                            and usu_tlogctmaux.usu_regsel = 'T'                       \ 
                            and usu_tlogctmaux.usu_codprc = :nCodPrc                  \
                            and usu_tlogctmaux.usu_ideprc = :sIdePrc                  \    
                            and usu_tlogctmaux.usu_codusu = :nCodUsu";
      cur_pendencia.AbrirCursor();
      Se (cur_pendencia.NaoAchou)
      {
        this.Retorno.CriarLinha();
        this.Retorno.Status = 1; @ Erro @  
        this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";
      }
      Senao 
      Enquanto (cur_pendencia.Achou) {
        sIdeUni = cur_pendencia.usu_ideuni;
        nStaInt = cur_pendencia.usu_sitpen; 

        Se (nStaInt = 1) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @  
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
        }
        Senao Se (nStaInt = 3) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @  
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
        }
        Senao {
          @- Reabilita a pendencia de integração -@
          ExecSqlEx("update usu_t000exp                       \
                        set usu_sitpen = 1                       \                 
                      where usu_ideuni = :sIdeUni",nErro,sMensagemRetorno); 

          Se (nErro = 0) { 
            fGravaLogIntegracao(); @ Atualiza o Log de Pendencia @  
          } Senao { 
            this.Retorno.CriarLinha();
            this.Retorno.Status =  1; @ Erro @    
            this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
          }   
        }      
        cur_pendencia.Proximo();     
      }
      cur_pendencia.FecharCursor();  
    }

    Se (sIdePrc = "NFC")
    {
      nStatusExecucao = 0; @ Encontrado implementação @
      sNomReg = "Integração NFE (Avido de Recebimento)";
      
      Definir Alfa CCurPen;

      TClaSql = "Select Cix.SeqInt, Cix.SitIex \
                            From E000CIX Cix, USU_TLogCtmAux Log \
                          Where Log.USU_IdeUni = To_Char(Cix.SeqInt) \
                            And Log.USU_RegSel = 'T' \
                            And Log.USU_CodPrc = :nCodPrc \
                            And Log.USU_IdePrc = :sIdePrc \
                            And Log.USU_CodUsu = :nCodUsu";
      SQL_Criar(CCurPen);
      SQL_UsarAbrangencia(CCurPen, 0);
      SQL_UsarSQLSenior2(CCurPen, 0);
      SQL_DefinirComando(CCurPen, TClaSql);
      SQL_DefinirInteiro(CCurPen, "nCodPrc", nCodPrc);
      SQL_DefinirAlfa(CCurPen, "sIdePrc", sIdePrc);
      SQL_DefinirInteiro(CCurPen, "nCodUsu", nCodUsu);
      SQL_AbrirCursor(CCurPen);
      Se (SQL_EOF(CCurPen) <> 0)
      {
        this.Retorno.CriarLinha();
        this.Retorno.Status = 1; @ Erro @  
        this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";
      }
      Senao
      {
        Enquanto (SQL_EOF(CCurPen) = 0)
        {
          SQL_RetornarAlfa(CCurPen, "SeqInt", sIdeUni);
          SQL_RetornarAlfa(CCurPen, "SitIex", aSitIex);
          SQL_RetornarInteiro(CCurPen, "SeqInt", nIdeUni);

          Se (aSitIex = "P") 
          {
            this.Retorno.CriarLinha();
            this.Retorno.Status = 1; @ Erro @  
            this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
          }
          Senao Se (aSitIex = "S") 
          {
            this.Retorno.CriarLinha();
            this.Retorno.Status = 1; @ Erro @  
            this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
          }
          Senao 
          {
            @- Reabilita a pendencia de integração -@
            ExecSqlEx("Update E000CIX Set SitIex = 'P' \
                        Where SeqInt = :nIdeUni",nErro,sMensagemRetorno); 

            Se (nErro = 0) 
              fGravaLogIntegracao(); @ Atualiza o Log de Pendencia @  
            Senao 
            { 
              this.Retorno.CriarLinha();
              this.Retorno.Status =  1; @ Erro @    
              this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
            }   
          }      
          SQL_Proximo(CCurPen);
        }
      }
      SQL_Destruir(CCurPen);
    }

    @--- XAP - Apontamento de Produção WMS-XC (xcApontamentoDeProducao) ---@
    Se (sIdePrc = "XAP") {
      nStatusExecucao = 0; @ Encontrado implementação @
      sNomReg = "Apontamento de Produção WMS-XC";

      cur_pendencia.sql "select usu_t000exp.usu_ideuni,                  \
                                usu_t000exp.usu_sitpen                   \
                           from usu_tlogctmaux,                          \
                                usu_t000exp                              \
                          where usu_tlogctmaux.usu_ideuni = usu_t000exp.usu_ideuni \
                            and usu_tlogctmaux.usu_regsel = 'T'          \
                            and usu_tlogctmaux.usu_codprc = :nCodPrc     \
                            and usu_tlogctmaux.usu_ideprc = :sIdePrc     \
                            and usu_tlogctmaux.usu_codusu = :nCodUsu";
      cur_pendencia.AbrirCursor();
      Se (cur_pendencia.NaoAchou)
      {
        this.Retorno.CriarLinha();
        this.Retorno.Status = 1; @ Erro @
        this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";
      }
      Senao
      Enquanto (cur_pendencia.Achou) {
        sIdeUni = cur_pendencia.usu_ideuni;
        nStaInt = cur_pendencia.usu_sitpen;

        Se (nStaInt = 1) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
        }
        Senao Se (nStaInt = 3) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
        }
        Senao {
          @- Reabilita a pendencia de integração -@
          ExecSqlEx("update usu_t000exp                       \
                        set usu_sitpen = 1                     \
                      where usu_ideuni = :sIdeUni",nErro,sMensagemRetorno);

          Se (nErro = 0) {
            fGravaLogIntegracao(); @ Atualiza o Log de Pendencia @
          } Senao {
            this.Retorno.CriarLinha();
            this.Retorno.Status =  1; @ Erro @
            this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
          }
        }
        cur_pendencia.Proximo();
      }
      cur_pendencia.FecharCursor();
    }

    @--- XCR - Requisição / Transferência WMS (xcRequisicaoTransferenciaWms) - pendência pode estar em USU_T000EXP (processo 1) ou USU_TINTWMS (processos 2/3) ---@
    Se (sIdePrc = "XCR") {
      nStatusExecucao = 0; @ Encontrado implementação @
      sNomReg = "Requisição / Transferência WMS";
      nAchouXcr = 0;

      cur_pendencia.sql "select usu_t000exp.usu_ideuni,                  \
                                usu_t000exp.usu_sitpen                   \
                           from usu_tlogctmaux,                          \
                                usu_t000exp                              \
                          where usu_tlogctmaux.usu_ideuni = usu_t000exp.usu_ideuni \
                            and usu_tlogctmaux.usu_regsel = 'T'          \
                            and usu_tlogctmaux.usu_codprc = :nCodPrc     \
                            and usu_tlogctmaux.usu_ideprc = :sIdePrc     \
                            and usu_tlogctmaux.usu_codusu = :nCodUsu";
      cur_pendencia.AbrirCursor();
      Enquanto (cur_pendencia.Achou) {
        nAchouXcr = 1;
        sIdeUni = cur_pendencia.usu_ideuni;
        nStaInt = cur_pendencia.usu_sitpen;

        Se (nStaInt = 1) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
        }
        Senao Se (nStaInt = 3) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
        }
        Senao {
          ExecSqlEx("update usu_t000exp                       \
                        set usu_sitpen = 1                     \
                      where usu_ideuni = :sIdeUni",nErro,sMensagemRetorno);

          Se (nErro = 0) {
            fGravaLogIntegracao();
          } Senao {
            this.Retorno.CriarLinha();
            this.Retorno.Status =  1; @ Erro @
            this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
          }
        }
        cur_pendencia.Proximo();
      }
      cur_pendencia.FecharCursor();

      cur_pendencia.sql "select usu_tintwms.usu_ideuni,                  \
                                usu_tintwms.usu_sitpen                   \
                           from usu_tlogctmaux,                          \
                                usu_tintwms                              \
                          where usu_tlogctmaux.usu_ideuni = usu_tintwms.usu_ideuni \
                            and usu_tlogctmaux.usu_regsel = 'T'          \
                            and usu_tlogctmaux.usu_codprc = :nCodPrc     \
                            and usu_tlogctmaux.usu_ideprc = :sIdePrc     \
                            and usu_tlogctmaux.usu_codusu = :nCodUsu";
      cur_pendencia.AbrirCursor();
      Enquanto (cur_pendencia.Achou) {
        nAchouXcr = 1;
        sIdeUni = cur_pendencia.usu_ideuni;
        nStaInt = cur_pendencia.usu_sitpen;

        Se (nStaInt = 1) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
        }
        Senao Se (nStaInt = 3) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
        }
        Senao {
          ExecSqlEx("update usu_tintwms                       \
                        set usu_sitpen = 1                     \
                      where usu_ideuni = :sIdeUni",nErro,sMensagemRetorno);

          Se (nErro = 0) {
            fGravaLogIntegracao();
          } Senao {
            this.Retorno.CriarLinha();
            this.Retorno.Status =  1; @ Erro @
            this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
          }
        }
        cur_pendencia.Proximo();
      }
      cur_pendencia.FecharCursor();

      Se (nAchouXcr = 0)
      {
        this.Retorno.CriarLinha();
        this.Retorno.Status = 1; @ Erro @
        this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";
      }
    }
  }

  Se(nCodPrc = 2)
	{
			Se (sIdePrc = "TRK")
			{
					nStatusExecucao = 0; @ Encontrado implementação @
					sNomReg = "Envio Tracking SELLENT";
					
					Definir Alfa CCurPen;

					TClaSql = "select usu_ttrkhis.usu_ideuni, usu_ttrkhis.usu_staint \  
											from usu_tlogctmaux, usu_ttrkhis \
											where usu_tlogctmaux.usu_ideuni = usu_ttrkhis.usu_ideuni \
											and usu_tlogctmaux.usu_regsel = 'T' \ 
											and usu_tlogctmaux.usu_codprc = :nCodPrc \
											and usu_tlogctmaux.usu_ideprc = :sIdePrc \    
											and usu_tlogctmaux.usu_codusu = :nCodUsu";
					
					SQL_Criar(CCurPen);
					SQL_UsarAbrangencia(CCurPen, 0);
					SQL_UsarSQLSenior2(CCurPen, 0);
					SQL_DefinirComando(CCurPen, TClaSql);
					SQL_DefinirInteiro(CCurPen, "nCodPrc", nCodPrc);
					SQL_DefinirAlfa(CCurPen, "sIdePrc", sIdePrc);
					SQL_DefinirInteiro(CCurPen, "nCodUsu", nCodUsu);
					SQL_AbrirCursor(CCurPen);
					Se (SQL_EOF(CCurPen) <> 0)
					{
					this.Retorno.CriarLinha();
					this.Retorno.Status = 1; @ Erro @  
					this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";
					}
					Senao
					{
					Enquanto (SQL_EOF(CCurPen) = 0)
					{
							SQL_RetornarAlfa(CCurPen, "USU_IdeUni", sIdeUni);
							SQL_RetornarInteiro(CCurPen, "USU_StaInt", nStaInt);           

							Se (nStaInt = 1) 
							{
							this.Retorno.CriarLinha();
							this.Retorno.Status = 1; @ Erro @  
							this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
							}
							Senao Se (nStaInt = 3) 
							{
							this.Retorno.CriarLinha();
							this.Retorno.Status = 1; @ Erro @  
							this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
							}
							Senao 
							{
							@- Reabilita a pendencia de integração -@
							ExecSqlEx("Update USU_TTrkHis Set usu_staint = 1 \
													Where USU_IdeUni = :sIdeUni",nErro,sMensagemRetorno); 

							Se (nErro = 0) 
									fGravaLogIntegracao(); @ Atualiza o Log de Pendencia @  
							Senao 
							{ 
									this.Retorno.CriarLinha();
									this.Retorno.Status =  1; @ Erro @    
									this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
							}   
							}      
							SQL_Proximo(CCurPen);     
					}
					}
					SQL_Destruir(CCurPen);         
			}
	}
      
  Se (nCodPrc = 3)
  {
    @--- BXC - Baixa Componente ERP SIGMA---@
    Se (sIdePrc = "BXC") {
      nStatusExecucao = 0; @ Encontrado implementação @
      sNomReg = "Baixa Componente ERP";
      
      cur_pendencia.sql "select USU_TBXACMP.usu_ideuni,                        \ 
                                USU_TBXACMP.usu_sitpen                             \  
                           from usu_tlogctmaux,                                        \
                                USU_TBXACMP                                        \
                          where usu_tlogctmaux.usu_ideuni = USU_TBXACMP.usu_ideuni \
                            and usu_tlogctmaux.usu_regsel = 'T'                       \ 
                            and usu_tlogctmaux.usu_codprc = :nCodPrc                  \
                            and usu_tlogctmaux.usu_ideprc = :sIdePrc                  \    
                            and usu_tlogctmaux.usu_codusu = :nCodUsu";
      cur_pendencia.AbrirCursor();
      Se (cur_pendencia.NaoAchou)
      {
        this.Retorno.CriarLinha();
        this.Retorno.Status = 1; @ Erro @  
        this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";
      }
      Senao 
      Enquanto (cur_pendencia.Achou) {
        sIdeUni = cur_pendencia.usu_ideuni;
        nStaInt = cur_pendencia.usu_sitpen;
        sCodReg = sIdeUni;
        sChvReg = sIdeUni;

        Se (nStaInt = 1) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @  
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
        }
        Senao Se (nStaInt = 3) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @  
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
        }
        Senao {
          @- Reabilita a pendencia de baixa de componente ERP -@
          ExecSqlEx("update USU_TBXACMP                       \
                        set usu_sitpen = 1,                    \
                            usu_datprc = null,                 \
                            usu_horprc = null,                 \
                            usu_usuprc = null                  \                 
                      where usu_ideuni = :sIdeUni",nErro,sMensagemRetorno); 

          Se (nErro = 0) { 
            fGravaLogIntegracao(); @ Atualiza o Log de Pendencia @  
          } Senao { 
            this.Retorno.CriarLinha();
            this.Retorno.Status =  1; @ Erro @    
            this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
          }   
        }      
        cur_pendencia.Proximo();
      }
      cur_pendencia.FecharCursor();
    }

    @--- EST - Estorno de Componentes SIGMA---@
    Se (sIdePrc = "EST") {
      nStatusExecucao = 0; @ Encontrado implementação @
      sNomReg = "Estorno de Componentes";

      cur_pendencia.sql "select USU_TESTCMP.usu_ideuni,                        \
                                USU_TESTCMP.usu_sitpen                             \
                           from usu_tlogctmaux,                                        \
                                USU_TESTCMP                                        \
                          where usu_tlogctmaux.usu_ideuni = USU_TESTCMP.usu_ideuni \
                            and usu_tlogctmaux.usu_regsel = 'T'                       \
                            and usu_tlogctmaux.usu_codprc = :nCodPrc                  \
                            and usu_tlogctmaux.usu_ideprc = :sIdePrc                  \
                            and usu_tlogctmaux.usu_codusu = :nCodUsu";
      cur_pendencia.AbrirCursor();
      Se (cur_pendencia.NaoAchou)
      {
        this.Retorno.CriarLinha();
        this.Retorno.Status = 1; @ Erro @
        this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";
      }
      Senao
      Enquanto (cur_pendencia.Achou) {
        sIdeUni = cur_pendencia.usu_ideuni;
        nStaInt = cur_pendencia.usu_sitpen;
        sCodReg = sIdeUni;
        sChvReg = sIdeUni;

        Se (nStaInt = 1) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
        }
        Senao Se (nStaInt = 3) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
        }
        Senao {
          @- Reabilita a pendencia de estorno de componentes -@
          ExecSqlEx("update USU_TESTCMP                       \
                        set usu_sitpen = 1,                    \
                            usu_datprc = null,                 \
                            usu_horprc = null,                 \
                            usu_usuprc = null                  \
                      where usu_ideuni = :sIdeUni",nErro,sMensagemRetorno);

          Se (nErro = 0) {
            fGravaLogIntegracao(); @ Atualiza o Log de Pendencia @
          } Senao {
            this.Retorno.CriarLinha();
            this.Retorno.Status =  1; @ Erro @
            this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
          }
        }
        cur_pendencia.Proximo();
      }
      cur_pendencia.FecharCursor();
    }
  }

  Se (nCodPrc = 4)
  {
    @--- NFC - Integração OBC - Aviso de Entrega (SARG009), mesma tabela E000CIX do NFC/CodPrc=1 (SARG983) ---@
    Se (sIdePrc = "NFC")
    {
      nStatusExecucao = 0; @ Encontrado implementação @
      sNomReg = "Integração NF x OBC (Aviso de Entrega)";

      Definir Alfa CCurPen;

      TClaSql = "Select Cix.SeqInt, Cix.SitIex \
                            From E000CIX Cix, USU_TLogCtmAux Log \
                          Where Log.USU_IdeUni = To_Char(Cix.SeqInt) \
                            And Log.USU_RegSel = 'T' \
                            And Log.USU_CodPrc = :nCodPrc \
                            And Log.USU_IdePrc = :sIdePrc \
                            And Log.USU_CodUsu = :nCodUsu";
      SQL_Criar(CCurPen);
      SQL_UsarAbrangencia(CCurPen, 0);
      SQL_UsarSQLSenior2(CCurPen, 0);
      SQL_DefinirComando(CCurPen, TClaSql);
      SQL_DefinirInteiro(CCurPen, "nCodPrc", nCodPrc);
      SQL_DefinirAlfa(CCurPen, "sIdePrc", sIdePrc);
      SQL_DefinirInteiro(CCurPen, "nCodUsu", nCodUsu);
      SQL_AbrirCursor(CCurPen);
      Se (SQL_EOF(CCurPen) <> 0)
      {
        this.Retorno.CriarLinha();
        this.Retorno.Status = 1; @ Erro @
        this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";
      }
      Senao
      {
        Enquanto (SQL_EOF(CCurPen) = 0)
        {
          SQL_RetornarAlfa(CCurPen, "SeqInt", sIdeUni);
          SQL_RetornarAlfa(CCurPen, "SitIex", aSitIex);
          SQL_RetornarInteiro(CCurPen, "SeqInt", nIdeUni);

          Se (aSitIex = "P")
          {
            this.Retorno.CriarLinha();
            this.Retorno.Status = 1; @ Erro @
            this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
          }
          Senao Se (aSitIex = "S")
          {
            this.Retorno.CriarLinha();
            this.Retorno.Status = 1; @ Erro @
            this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
          }
          Senao
          {
            @- Reabilita a pendencia de integração -@
            ExecSqlEx("Update E000CIX Set SitIex = 'P' \
                        Where SeqInt = :nIdeUni",nErro,sMensagemRetorno);

            Se (nErro = 0)
              fGravaLogIntegracao(); @ Atualiza o Log de Pendencia @
            Senao
            {
              this.Retorno.CriarLinha();
              this.Retorno.Status =  1; @ Erro @
              this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
            }
          }
          SQL_Proximo(CCurPen);
        }
      }
      SQL_Destruir(CCurPen);
    }
  }

  Se (nCodPrc = 5)
  {
    @--- APT - Apontamento de Produção SKA (skaApontamentoDeProducao) ---@
    Se (sIdePrc = "APT") {
      nStatusExecucao = 0; @ Encontrado implementação @
      sNomReg = "Apontamento de Produção SKA";

      cur_pendencia.sql "select usu_tskaexpops.usu_ideuni,               \
                                usu_tskaexpops.usu_sitpen                \
                           from usu_tlogctmaux,                          \
                                usu_tskaexpops                          \
                          where usu_tlogctmaux.usu_ideuni = usu_tskaexpops.usu_ideuni \
                            and usu_tlogctmaux.usu_regsel = 'T'          \
                            and usu_tlogctmaux.usu_codprc = :nCodPrc     \
                            and usu_tlogctmaux.usu_ideprc = :sIdePrc     \
                            and usu_tlogctmaux.usu_codusu = :nCodUsu";
      cur_pendencia.AbrirCursor();
      Se (cur_pendencia.NaoAchou)
      {
        this.Retorno.CriarLinha();
        this.Retorno.Status = 1; @ Erro @
        this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";
      }
      Senao
      Enquanto (cur_pendencia.Achou) {
        sIdeUni = cur_pendencia.usu_ideuni;
        nStaInt = cur_pendencia.usu_sitpen;

        Se (nStaInt = 1) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
        }
        Senao Se (nStaInt = 3) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
        }
        Senao {
          @- Reabilita a pendencia de integração -@
          ExecSqlEx("update usu_tskaexpops                    \
                        set usu_sitpen = 1                     \
                      where usu_ideuni = :sIdeUni",nErro,sMensagemRetorno);

          Se (nErro = 0) {
            fGravaLogIntegracao(); @ Atualiza o Log de Pendencia @
          } Senao {
            this.Retorno.CriarLinha();
            this.Retorno.Status =  1; @ Erro @
            this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
          }
        }
        cur_pendencia.Proximo();
      }
      cur_pendencia.FecharCursor();
    }

    @--- RFG - Apontamento de Refugo SKA (skaApontamentoRefugo) ---@
    Se (sIdePrc = "RFG") {
      nStatusExecucao = 0; @ Encontrado implementação @
      sNomReg = "Apontamento de Refugo SKA";

      cur_pendencia.sql "select usu_tskaexpops.usu_ideuni,               \
                                usu_tskaexpops.usu_sitpen                \
                           from usu_tlogctmaux,                          \
                                usu_tskaexpops                          \
                          where usu_tlogctmaux.usu_ideuni = usu_tskaexpops.usu_ideuni \
                            and usu_tlogctmaux.usu_regsel = 'T'          \
                            and usu_tlogctmaux.usu_codprc = :nCodPrc     \
                            and usu_tlogctmaux.usu_ideprc = :sIdePrc     \
                            and usu_tlogctmaux.usu_codusu = :nCodUsu";
      cur_pendencia.AbrirCursor();
      Se (cur_pendencia.NaoAchou)
      {
        this.Retorno.CriarLinha();
        this.Retorno.Status = 1; @ Erro @
        this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";
      }
      Senao
      Enquanto (cur_pendencia.Achou) {
        sIdeUni = cur_pendencia.usu_ideuni;
        nStaInt = cur_pendencia.usu_sitpen;

        Se (nStaInt = 1) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
        }
        Senao Se (nStaInt = 3) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
        }
        Senao {
          @- Reabilita a pendencia de integração -@
          ExecSqlEx("update usu_tskaexpops                    \
                        set usu_sitpen = 1                     \
                      where usu_ideuni = :sIdeUni",nErro,sMensagemRetorno);

          Se (nErro = 0) {
            fGravaLogIntegracao(); @ Atualiza o Log de Pendencia @
          } Senao {
            this.Retorno.CriarLinha();
            this.Retorno.Status =  1; @ Erro @
            this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
          }
        }
        cur_pendencia.Proximo();
      }
      cur_pendencia.FecharCursor();
    }

    @--- BCC - Baixa de Consumo de Componente SKA (skaBaixaConsumoComponente) ---@
    Se (sIdePrc = "BCC") {
      nStatusExecucao = 0; @ Encontrado implementação @
      sNomReg = "Baixa de Consumo de Componente SKA";

      cur_pendencia.sql "select usu_tskaexpops.usu_ideuni,               \
                                usu_tskaexpops.usu_sitpen                \
                           from usu_tlogctmaux,                          \
                                usu_tskaexpops                          \
                          where usu_tlogctmaux.usu_ideuni = usu_tskaexpops.usu_ideuni \
                            and usu_tlogctmaux.usu_regsel = 'T'          \
                            and usu_tlogctmaux.usu_codprc = :nCodPrc     \
                            and usu_tlogctmaux.usu_ideprc = :sIdePrc     \
                            and usu_tlogctmaux.usu_codusu = :nCodUsu";
      cur_pendencia.AbrirCursor();
      Se (cur_pendencia.NaoAchou)
      {
        this.Retorno.CriarLinha();
        this.Retorno.Status = 1; @ Erro @
        this.Retorno.mensagemRetorno = "Nenhum registro selecionado para reabilitar.";
      }
      Senao
      Enquanto (cur_pendencia.Achou) {
        sIdeUni = cur_pendencia.usu_ideuni;
        nStaInt = cur_pendencia.usu_sitpen;

        Se (nStaInt = 1) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já está reabilitado.";
        }
        Senao Se (nStaInt = 3) {
          this.Retorno.CriarLinha();
          this.Retorno.Status = 1; @ Erro @
          this.Retorno.mensagemRetorno = "O Registro selecionado "+ sIdeUni +" já foi processado e não pode ser reabilitado.";
        }
        Senao {
          @- Reabilita a pendencia de integração -@
          ExecSqlEx("update usu_tskaexpops                    \
                        set usu_sitpen = 1                     \
                      where usu_ideuni = :sIdeUni",nErro,sMensagemRetorno);

          Se (nErro = 0) {
            fGravaLogIntegracao(); @ Atualiza o Log de Pendencia @
          } Senao {
            this.Retorno.CriarLinha();
            this.Retorno.Status =  1; @ Erro @
            this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;
          }
        }
        cur_pendencia.Proximo();
      }
      cur_pendencia.FecharCursor();
    }
  }

}

Funcao fGravaLogIntegracao();
{ 
  Definir interno.custom.senior.logs.GravarLog wsGraLog;
  wsGraLog.CodPrc = nCodPrc; 
  wsGraLog.IdePrc = sIdePrc; 
  wsGraLog.TknInt = "";
  wsGraLog.StaInt = 1; @ 1-Pendente | 2-Em Processamento | 3-Processado | 4-Erro @
  wsGraLog.CodRet = 0;
  wsGraLog.DesRet = "Pendência de integração do(a) " + sNomReg + " (" + sCodReg + ") Reabilitado(a) com sucesso!";
  wsGraLog.JsoEnv = "";
  wsGraLog.JsoRet = "";
  wsGraLog.UrlApi = "";
  wsGraLog.IdeUni = sIdeUni;
  wsGraLog.InfAdc = "";
  wsGraLog.RegRea = "S"; @ Reabilitar pendencia @
  wsGraLog.ChvReg = sChvReg;
  wsGraLog.Executar();

  nStatusRetorno = wsGraLog.Retorno.Status;
  sMensagemRetorno = wsGraLog.Retorno.MensagemRetorno;
  
  Se (nStatusRetorno = 0)
  {
    @ Atualiza o histórico de logs para registro reabilitado = T: True @
    ExecSQL "update usu_tlogctm           \
                set usu_regrea = 'T'      \                 
              where usu_codprc = :nCodPrc \
                and usu_ideprc = :sIdePrc \
                and usu_ideuni = :sIdeUni";
                
    this.Retorno.CriarLinha();
    this.Retorno.Status = 0; @ Sucesso @  
    this.Retorno.mensagemRetorno = "A pendência dos registros "+ sIdeUni +" foi reabilitada com sucesso.";
    this.Retorno.IdeUni = sIdeUni;
  }
  Senao
  {
    this.Retorno.CriarLinha();
    this.Retorno.Status =  1; @ Erro @    
    this.Retorno.mensagemRetorno = "Ocorreu um erro ao reabilitar o registro "+ sIdeUni +" do identificador de "+ sNomReg +". (custom.senior.logs.ReabilitarPendencias): " + sMensagemRetorno;      
  }
}

