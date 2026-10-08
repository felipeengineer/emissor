"""MCP server do emissor: expõe emissão, consulta e cancelamento de NFS-e como ferramentas para
assistentes de IA (Claude Desktop, Claude Code etc.). Usa o mesmo banco e configuração da interface web.

Execução:  emissor mcp            (stdio)
           emissor mcp --http     (streamable HTTP em http://127.0.0.1:8001/mcp)
"""

from __future__ import annotations

import json
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from .dps import MOTIVOS_CANCELAMENTO
from .servico import Emissor
from .simples import anexo_por_fator_r, calcular_aliquotas

INSTRUCOES = """\
Emissor de NFS-e do Sistema Nacional (gov.br/nfse) para empresas do Simples Nacional (MEI e ME/EPP).

Fluxo recomendado:
1. `status_emissor` para ver se prestador e certificado estão configurados e qual o ambiente.
2. Para um novo cliente, `cadastrar_tomador` (ou passe os dados completos em `emitir_nfse`).
3. `pre_visualizar_nfse` para conferir a DPS, depois `emitir_nfse`.
Emitir e cancelar em PRODUÇÃO gera documento fiscal com efeito legal: confirme valores, tomador e
descrição com o usuário antes. Códigos de município são IBGE (7 dígitos); cTribNac tem 6 dígitos
(item+subitem+desdobro da lista da LC 116, ex.: 010701 = suporte técnico em informática).
"""


class EnderecoIn(BaseModel):
    codigo_municipio: str = Field(description="Código IBGE do município (7 dígitos)")
    cep: str
    logradouro: str
    numero: str
    bairro: str
    complemento: str = ""


class TomadorIn(BaseModel):
    documento: str = Field(description="CPF ou CNPJ do tomador")
    nome: str = Field(description="Nome ou razão social")
    endereco: EnderecoIn | None = None
    email: str = ""
    telefone: str = ""
    inscricao_municipal: str = ""


class ServicoIn(BaseModel):
    descricao: str = Field("", description="Discriminação do serviço (usa a padrão se vazio)")
    valor: str = Field(description="Valor do serviço em reais, ex.: '1500.00'")
    codigo_tributacao_nacional: str = Field("", description="cTribNac (6 dígitos); usa o padrão configurado se vazio")
    codigo_municipio_prestacao: str = Field("", description="IBGE do local da prestação; padrão = município do prestador")
    codigo_tributacao_municipal: str = ""
    codigo_nbs: str = ""
    retencao_iss: Literal[1, 2, 3] = Field(1, description="1=não retido, 2=retido pelo tomador, 3=retido pelo intermediário")
    aliquota_iss: str | None = Field(None, description="pAliq % (ME/EPP). Vazio = padrão configurado")
    aliquota_simples: str | None = Field(None, description="pTotTribSN: alíquota efetiva do SN % (ME/EPP)")
    desconto_incondicionado: str = "0"
    competencia: str = Field("", description="Data de competência AAAA-MM-DD (padrão: hoje)")


def criar_servidor(emissor: Emissor | None = None) -> MCPServer:
    emissor = emissor or Emissor()
    mcp = MCPServer("emissor-nfse", instructions=INSTRUCOES)

    leitura = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

    @mcp.tool(annotations=leitura)
    def status_emissor() -> dict:
        """Mostra ambiente (produção/homologação), prestador, certificado, próximo nº de DPS e pendências de configuração."""
        return emissor.status()

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=True, open_world_hint=False))
    def configurar_prestador(
        documento: str,
        codigo_municipio: str,
        razao_social: str = "",
        opcao_simples: Literal[2, 3] = 3,
        regime_apuracao_sn: Literal[1, 2, 3] = 1,
        inscricao_municipal: str = "",
        telefone: str = "",
        email: str = "",
    ) -> dict:
        """Cadastra a empresa emitente. opcao_simples: 2=MEI, 3=ME/EPP. regime_apuracao_sn (só ME/EPP):
        1=federais e ISS pelo SN, 2=federais pelo SN e ISS fora (sublimite), 3=ambos fora."""
        return emissor.salvar_prestador(locals())

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=True, open_world_hint=False))
    def configurar_parametros(
        ambiente: Literal[1, 2] | None = None,
        serie: str | None = None,
        certificado_caminho: str | None = None,
        servico_padrao: ServicoIn | None = None,
        ultimo_numero_dps: int | None = None,
    ) -> dict:
        """Ajusta ambiente (1=produção, 2=homologação), série da DPS, caminho do certificado .pfx, serviço padrão
        e o último nº de DPS já usado (para continuar a numeração de outro sistema). A senha do certificado
        deve ser definida pela interface web ou pela variável de ambiente EMISSOR_CERT_SENHA."""
        padrao = None
        if servico_padrao is not None:
            padrao = servico_padrao.model_dump(exclude={"valor", "competencia", "desconto_incondicionado"})
        return emissor.salvar_parametros(
            ambiente=ambiente,
            serie=serie,
            certificado_caminho=certificado_caminho,
            servico_padrao=padrao,
            ultimo_numero_dps=ultimo_numero_dps,
        )

    @mcp.tool(annotations=leitura)
    def calcular_aliquota_simples(
        rbt12: str, anexo: Literal["III", "IV", "V"] | None = None, folha_12_meses: str | None = None
    ) -> dict:
        """Estima a alíquota efetiva do Simples Nacional (pTotTribSN) e a parcela de ISS (pAliq) a partir da
        receita bruta dos últimos 12 meses. Se informar a folha de 12 meses sem anexo, aplica o fator R (III ou V)."""
        if anexo is None:
            anexo = anexo_por_fator_r(folha_12_meses, rbt12) if folha_12_meses else "III"
        return calcular_aliquotas(rbt12, anexo)

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=True, open_world_hint=False))
    def cadastrar_tomador(tomador: TomadorIn) -> dict:
        """Cadastra ou atualiza um cliente (tomador do serviço)."""
        return emissor.salvar_tomador(tomador.model_dump())

    @mcp.tool(annotations=leitura)
    def listar_tomadores(busca: str = "") -> list[dict]:
        """Lista clientes cadastrados (filtra por nome ou documento)."""
        return emissor.listar_tomadores(busca)

    @mcp.tool(annotations=leitura)
    def pre_visualizar_nfse(servico: ServicoIn, tomador: TomadorIn | None = None, tomador_documento: str = "") -> dict:
        """Gera o XML da DPS sem assinar nem enviar, para conferência antes da emissão."""
        return emissor.pre_visualizar(_tomador(tomador, tomador_documento), servico.model_dump())

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=False, open_world_hint=True))
    def emitir_nfse(servico: ServicoIn, tomador: TomadorIn | None = None, tomador_documento: str = "") -> dict:
        """Emite a NFS-e: assina a DPS com o certificado A1 e envia à SEFIN Nacional. Informe o tomador completo
        ou só `tomador_documento` de um cliente já cadastrado (ou nenhum, para tomador não identificado).
        Em produção, confirme os dados com o usuário antes de chamar."""
        nota = emissor.emitir(_tomador(tomador, tomador_documento), servico.model_dump())
        nota.pop("dps_xml", None)
        nota.pop("nfse_xml", None)
        return nota

    @mcp.tool(annotations=leitura)
    def listar_notas(
        status: Literal["emitida", "rejeitada", "cancelada", "pendente", "erro_comunicacao"] | None = None,
        busca: str = "",
        limite: int = 20,
    ) -> list[dict]:
        """Lista as notas registradas localmente (mais recentes primeiro)."""
        return emissor.listar_notas(status=status, busca=busca, limite=limite)

    @mcp.tool(annotations=leitura)
    def obter_nota(nota_id: int, incluir_xml: bool = False) -> dict:
        """Detalhes de uma nota local. Com incluir_xml, retorna também os XMLs da DPS e da NFS-e."""
        nota = emissor.obter_nota(nota_id)
        if not nota:
            raise ValueError(f"Nota {nota_id} não encontrada")
        if not incluir_xml:
            nota.pop("dps_xml", None)
            nota.pop("nfse_xml", None)
        return nota

    @mcp.tool(annotations=leitura)
    def resumo_faturamento(ano_mes: str = "") -> dict:
        """Totais de notas emitidas no ambiente atual; ano_mes no formato AAAA-MM (vazio = todas)."""
        return emissor.resumo(ano_mes or None)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
    def consultar_nfse(chave_acesso: str) -> dict:
        """Consulta uma NFS-e na SEFIN Nacional pela chave de acesso (50 dígitos)."""
        return emissor.consultar(chave_acesso)

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=True, open_world_hint=True))
    def sincronizar_nota(nota_id: int) -> dict:
        """Para nota pendente ou com erro de comunicação: verifica na SEFIN se a DPS foi convertida em NFS-e."""
        nota = emissor.sincronizar(nota_id)
        nota.pop("dps_xml", None)
        nota.pop("nfse_xml", None)
        return nota

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=False, open_world_hint=True))
    def cancelar_nfse(nota_id: int, codigo_motivo: Literal[1, 2, 9], justificativa: str) -> dict:
        """Cancela uma NFS-e emitida (evento e101101). Motivos: 1=erro na emissão, 2=serviço não prestado,
        9=outros. Justificativa com 15 a 255 caracteres. Irreversível: confirme com o usuário."""
        nota = emissor.cancelar(nota_id, codigo_motivo, justificativa)
        nota.pop("dps_xml", None)
        nota.pop("nfse_xml", None)
        return nota

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=True, open_world_hint=True))
    def baixar_danfse(nota_id: int) -> dict:
        """Baixa o PDF do DANFSe (documento auxiliar) e informa onde foi salvo."""
        return {"arquivo": str(emissor.baixar_danfse(nota_id))}

    @mcp.resource("emissor://motivos-cancelamento")
    def motivos_cancelamento() -> str:
        """Códigos de motivo aceitos no cancelamento."""
        return json.dumps(MOTIVOS_CANCELAMENTO, ensure_ascii=False)

    return mcp


def _tomador(tomador: TomadorIn | None, documento: str) -> dict | str | None:
    if tomador is not None:
        return tomador.model_dump()
    return documento or None


def main(transporte: str = "stdio", host: str = "127.0.0.1", porta: int = 8001) -> None:
    servidor = criar_servidor()
    if transporte == "stdio":
        servidor.run("stdio")
    else:
        servidor.run("streamable-http", host=host, port=porta)
