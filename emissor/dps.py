"""Montagem do XML da DPS (Declaração de Prestação de Serviço) e do pedido de cancelamento.

Leiaute: NFS-e Padrão Nacional (namespace http://www.sped.fazenda.gov.br/nfse).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from lxml import etree

from . import VERSAO_APLICATIVO
from .modelos import (
    ErroValidacao,
    OpcaoSimplesNacional,
    Prestador,
    RetencaoISS,
    Servico,
    Tomador,
    formatar_decimal,
    somente_digitos,
)

NS = "http://www.sped.fazenda.gov.br/nfse"
VERSAO_LEIAUTE = "1.00"

AMBIENTE_PRODUCAO = 1
AMBIENTE_HOMOLOGACAO = 2  # "produção restrita"

TP_EVENTO_CANCELAMENTO = "101101"

MOTIVOS_CANCELAMENTO = {
    1: "Erro na emissão",
    2: "Serviço não prestado",
    9: "Outros",
}


@dataclass
class DadosDPS:
    prestador: Prestador
    tomador: Tomador | None
    servico: Servico
    serie: str
    numero: int
    ambiente: int = AMBIENTE_HOMOLOGACAO
    data_emissao: datetime | None = None
    competencia: date | None = None
    versao: str = VERSAO_LEIAUTE

    def validar(self) -> None:
        self.prestador.validar()
        if self.tomador:
            self.tomador.validar()
        self.servico.validar()
        self.serie = somente_digitos(self.serie) or "1"
        if len(self.serie) > 5:
            raise ErroValidacao("serie: máximo de 5 dígitos")
        if not 1 <= int(self.numero) <= 999_999_999_999_999:
            raise ErroValidacao("numero da DPS fora da faixa permitida")
        if self.ambiente not in (AMBIENTE_PRODUCAO, AMBIENTE_HOMOLOGACAO):
            raise ErroValidacao("ambiente deve ser 1 (produção) ou 2 (homologação)")
        if self.servico.retencao_iss != RetencaoISS.NAO_RETIDO and not self.tomador:
            raise ErroValidacao("ISS retido exige a identificação do tomador")


def agora_brasilia() -> datetime:
    # A SEFIN rejeita dhEmi no futuro; recuamos alguns segundos por segurança contra desvio de relógio.
    return (datetime.now(ZoneInfo("America/Sao_Paulo")) - timedelta(seconds=30)).replace(microsecond=0)


def id_dps(prestador: Prestador, serie: str, numero: int) -> str:
    """Id = "DPS" + cLocEmi(7) + tipo inscrição(1: 1=CPF, 2=CNPJ) + inscrição(14) + série(5) + nDPS(15)."""
    doc = somente_digitos(prestador.documento)
    tipo = "2" if len(doc) == 14 else "1"
    return (
        "DPS"
        + somente_digitos(prestador.codigo_municipio).zfill(7)
        + tipo
        + doc.zfill(14)
        + somente_digitos(serie).zfill(5)
        + str(int(numero)).zfill(15)
    )


def _sub(pai: etree._Element, tag: str, texto: str | None = None) -> etree._Element:
    el = etree.SubElement(pai, f"{{{NS}}}{tag}")
    if texto is not None:
        el.text = str(texto)
    return el


def _documento(pai: etree._Element, doc: str) -> None:
    doc = somente_digitos(doc)
    _sub(pai, "CNPJ" if len(doc) == 14 else "CPF", doc)


def montar_dps(dados: DadosDPS) -> etree._Element:
    """Gera o elemento <DPS> (ainda sem assinatura)."""
    dados.validar()
    p, t, s = dados.prestador, dados.tomador, dados.servico
    dh = dados.data_emissao or agora_brasilia()
    if dh.tzinfo is None:
        raise ErroValidacao("data_emissao precisa ter fuso horário")
    competencia = dados.competencia or dh.date()

    raiz = etree.Element(f"{{{NS}}}DPS", nsmap={None: NS})
    raiz.set("versao", dados.versao)
    inf = _sub(raiz, "infDPS")
    inf.set("Id", id_dps(p, dados.serie, dados.numero))

    _sub(inf, "tpAmb", dados.ambiente)
    _sub(inf, "dhEmi", dh.isoformat(timespec="seconds"))
    _sub(inf, "verAplic", VERSAO_APLICATIVO)
    _sub(inf, "serie", dados.serie)
    _sub(inf, "nDPS", int(dados.numero))
    _sub(inf, "dCompet", competencia.isoformat())
    _sub(inf, "tpEmit", 1)  # 1 = emitido pelo próprio prestador
    _sub(inf, "cLocEmi", somente_digitos(p.codigo_municipio))

    # Prestador: quando ele é o emitente, nome e endereço vêm do Cadastro Nacional (não informar).
    prest = _sub(inf, "prest")
    _documento(prest, p.documento)
    if p.inscricao_municipal:
        _sub(prest, "IM", somente_digitos(p.inscricao_municipal))
    if p.telefone:
        _sub(prest, "fone", somente_digitos(p.telefone))
    if p.email:
        _sub(prest, "email", p.email.strip())
    reg = _sub(prest, "regTrib")
    _sub(reg, "opSimpNac", int(p.opcao_simples))
    if p.opcao_simples == OpcaoSimplesNacional.ME_EPP:
        _sub(reg, "regApTribSN", int(p.regime_apuracao_sn))
    _sub(reg, "regEspTrib", 0)  # 0 = nenhum regime especial

    if t:
        toma = _sub(inf, "toma")
        _documento(toma, t.documento)
        if t.inscricao_municipal:
            _sub(toma, "IM", somente_digitos(t.inscricao_municipal))
        _sub(toma, "xNome", t.nome.strip())
        if t.endereco:
            e = t.endereco
            end = _sub(toma, "end")
            nac = _sub(end, "endNac")
            _sub(nac, "cMun", somente_digitos(e.codigo_municipio))
            _sub(nac, "CEP", somente_digitos(e.cep))
            _sub(end, "xLgr", e.logradouro.strip())
            _sub(end, "nro", e.numero.strip())
            if e.complemento.strip():
                _sub(end, "xCpl", e.complemento.strip())
            _sub(end, "xBairro", e.bairro.strip())
        if t.telefone:
            _sub(toma, "fone", somente_digitos(t.telefone))
        if t.email:
            _sub(toma, "email", t.email.strip())

    serv = _sub(inf, "serv")
    loc = _sub(serv, "locPrest")
    _sub(loc, "cLocPrestacao", somente_digitos(s.codigo_municipio_prestacao))
    cserv = _sub(serv, "cServ")
    _sub(cserv, "cTribNac", s.codigo_tributacao_nacional)
    if s.codigo_tributacao_municipal:
        _sub(cserv, "cTribMun", somente_digitos(s.codigo_tributacao_municipal))
    _sub(cserv, "xDescServ", s.descricao.strip())
    if s.codigo_nbs:
        _sub(cserv, "cNBS", somente_digitos(s.codigo_nbs))

    valores = _sub(inf, "valores")
    vsp = _sub(valores, "vServPrest")
    _sub(vsp, "vServ", formatar_decimal(s.valor))
    if s.desconto_incondicionado > 0:
        desc = _sub(valores, "vDescCondIncond")
        _sub(desc, "vDescIncond", formatar_decimal(s.desconto_incondicionado))

    trib = _sub(valores, "trib")
    mun = _sub(trib, "tribMun")
    _sub(mun, "tribISSQN", 1)  # 1 = operação tributável
    _sub(mun, "tpRetISSQN", int(s.retencao_iss))
    if s.aliquota_iss is not None and p.opcao_simples == OpcaoSimplesNacional.ME_EPP:
        _sub(mun, "pAliq", formatar_decimal(s.aliquota_iss))

    # Optantes do SN: PIS/COFINS/IRPJ/CSLL/CPP são recolhidos no DAS, então não há grupo tribFed.
    tot = _sub(trib, "totTrib")
    if p.opcao_simples == OpcaoSimplesNacional.ME_EPP and s.aliquota_simples is not None:
        _sub(tot, "pTotTribSN", formatar_decimal(s.aliquota_simples))
    else:
        _sub(tot, "indTotTrib", 0)  # 0 = não informar valor estimado de tributos

    return raiz


def montar_pedido_cancelamento(
    *,
    chave_acesso: str,
    documento_autor: str,
    codigo_motivo: int,
    justificativa: str,
    ambiente: int,
    numero_pedido: int = 1,
    data_evento: datetime | None = None,
    versao: str = VERSAO_LEIAUTE,
) -> etree._Element:
    """Gera o <pedRegEvento> de cancelamento (e101101), ainda sem assinatura."""
    chave = somente_digitos(chave_acesso)
    if len(chave) != 50:
        raise ErroValidacao("chave de acesso deve ter 50 dígitos")
    if codigo_motivo not in MOTIVOS_CANCELAMENTO:
        raise ErroValidacao(f"motivo de cancelamento inválido; use um de {sorted(MOTIVOS_CANCELAMENTO)}")
    justificativa = (justificativa or "").strip()
    if not 15 <= len(justificativa) <= 255:
        raise ErroValidacao("justificativa do cancelamento deve ter entre 15 e 255 caracteres")
    doc = somente_digitos(documento_autor)
    dh = data_evento or agora_brasilia()

    raiz = etree.Element(f"{{{NS}}}pedRegEvento", nsmap={None: NS})
    raiz.set("versao", versao)
    inf = _sub(raiz, "infPedReg")
    inf.set("Id", f"PRE{chave}{TP_EVENTO_CANCELAMENTO}{int(numero_pedido):03d}")
    _sub(inf, "tpAmb", ambiente)
    _sub(inf, "verAplic", VERSAO_APLICATIVO)
    _sub(inf, "dhEvento", dh.isoformat(timespec="seconds"))
    _sub(inf, "CNPJAutor" if len(doc) == 14 else "CPFAutor", doc)
    _sub(inf, "chNFSe", chave)
    _sub(inf, "nPedRegEvento", int(numero_pedido))
    ev = _sub(inf, "e" + TP_EVENTO_CANCELAMENTO)
    _sub(ev, "xDesc", "Cancelamento de NFS-e")
    _sub(ev, "cMotivo", codigo_motivo)
    _sub(ev, "xMotivo", justificativa)
    return raiz


def para_bytes(el: etree._Element) -> bytes:
    return etree.tostring(el, xml_declaration=True, encoding="UTF-8")
