"""Montagem do XML da DPS (Declaração de Prestação de Serviço) e do pedido de cancelamento.

Leiaute: NFS-e Padrão Nacional (namespace http://www.sped.fazenda.gov.br/nfse).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from lxml import etree

from . import VERSAO_APLICATIVO
from .modelos import (
    ErroValidacao,
    OpcaoSimplesNacional,
    Prestador,
    RegimeApuracaoSN,
    RetencaoISS,
    Servico,
    Tomador,
    formatar_decimal,
    normalizar_documento,
    somente_digitos,
)

NS = "http://www.sped.fazenda.gov.br/nfse"
VERSAO_LEIAUTE = "1.01"  # vigente desde 01/01/2026

AMBIENTE_PRODUCAO = 1
AMBIENTE_HOMOLOGACAO = 2  # "produção restrita"

TP_EVENTO_CANCELAMENTO = "101101"

# Faixa de série reservada ao "aplicativo próprio do contribuinte" (API); fora dela: rejeição E0010.
SERIE_API_MAX = 49999
ALIQUOTA_ISS_MIN_RETENCAO = Decimal("1.80")  # E0621/E0628
ALIQUOTA_ISS_MAX = Decimal("5.00")  # E0595

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
        """Regras locais do Anexo I (v1.01) que a SEFIN aplica; os códigos estão nas mensagens."""
        p, t, s = self.prestador, self.tomador, self.servico
        p.validar()
        if t:
            t.validar()
        s.validar()
        self.serie = somente_digitos(self.serie) or "1"
        if not 1 <= int(self.serie) <= SERIE_API_MAX:
            raise ErroValidacao(f"série da DPS emitida via API deve estar entre 1 e {SERIE_API_MAX} (regra E0010)")
        if not 1 <= int(self.numero) <= 999_999_999_999_999:
            raise ErroValidacao("numero da DPS fora da faixa permitida")
        if self.ambiente not in (AMBIENTE_PRODUCAO, AMBIENTE_HOMOLOGACAO):
            raise ErroValidacao("ambiente deve ser 1 (produção) ou 2 (homologação)")

        retido = s.retencao_iss != RetencaoISS.NAO_RETIDO
        if retido and p.opcao_simples == OpcaoSimplesNacional.MEI:
            raise ErroValidacao("MEI não pode ter ISS retido (regra E0583)")
        if s.retencao_iss == RetencaoISS.RETIDO_PELO_INTERMEDIARIO:
            raise ErroValidacao(
                "ISS retido pelo intermediário exige o grupo do intermediário, que este emissor não gera "
                "(regras E0264/E0293)"
            )
        if retido and not t:
            raise ErroValidacao("ISS retido exige a identificação do tomador (regra E0204)")
        if s.retencao_iss == RetencaoISS.RETIDO_PELO_TOMADOR and not t.endereco:
            raise ErroValidacao("ISS retido pelo tomador exige o endereço do tomador (regra E0237)")
        # E0235 (aplicada no ADN): tomador com CNPJ exige endereço nacional.
        if t and len(t.documento) == 14 and not t.endereco:
            raise ErroValidacao("Tomador com CNPJ exige endereço (regra E0235)")

        if p.opcao_simples == OpcaoSimplesNacional.ME_EPP and s.aliquota_simples is None:
            raise ErroValidacao(
                "ME/EPP deve informar a alíquota nominal do Simples Nacional da sua faixa (pTotTribSN, "
                "regra E0712); a calculadora em Configurações mostra o valor"
            )
        if deve_informar_paliq(p, s):
            if s.aliquota_iss is None:
                raise ErroValidacao(
                    "informe a alíquota do ISS: obrigatória para ME/EPP com ISS retido, ou com ISS fora do "
                    "Simples em município não conveniado (regras E0621/E0628/E0640)"
                )
            minimo = ALIQUOTA_ISS_MIN_RETENCAO if retido else Decimal("0.01")
            if not minimo <= s.aliquota_iss <= ALIQUOTA_ISS_MAX:
                raise ErroValidacao(
                    f"alíquota do ISS deve estar entre {minimo:.2f}% e {ALIQUOTA_ISS_MAX:.2f}% (regras E0595/E0621)"
                )


def deve_informar_paliq(prestador: Prestador, servico: Servico) -> bool:
    """Se a DPS deve levar pAliq. Fora destes casos o campo é proibido e não é enviado.

    - MEI: nunca (E0600).
    - ME/EPP com ISS no DAS (regApTribSN=1): só com ISS retido (obrigatório: E0621/E0628;
      proibido sem retenção: E0625/E0631).
    - ME/EPP com ISS fora do DAS (regApTribSN 2 ou 3): só se o município de incidência não for
      conveniado ativo (obrigatório: E0640; proibido em conveniado: E0635).
    """
    if prestador.opcao_simples != OpcaoSimplesNacional.ME_EPP:
        return False
    if prestador.regime_apuracao_sn == RegimeApuracaoSN.TRIBUTOS_FEDERAIS_E_ISS_PELO_SN:
        return servico.retencao_iss != RetencaoISS.NAO_RETIDO
    return not servico.municipio_incidencia_conveniado


def agora_brasilia() -> datetime:
    # A SEFIN rejeita (E0008) dhEmi posterior ao seu horário de processamento; recuamos 60s contra
    # desvio de relógio.
    return (datetime.now(ZoneInfo("America/Sao_Paulo")) - timedelta(seconds=60)).replace(microsecond=0)


def id_dps(prestador: Prestador, serie: str, numero: int) -> str:
    """Id = "DPS" + cLocEmi(7) + tipo inscrição(1: 1=CPF, 2=CNPJ) + inscrição(14) + série(5) + nDPS(15)."""
    doc = normalizar_documento(prestador.documento)
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
    doc = normalizar_documento(doc)
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
    # Ordem no XSD 1.01: tribISSQN → cPaisResult? → tpImunidade? → exigSusp? → BM? → tpRetISSQN → pAliq?
    # (no 1.00 o pAliq vinha antes do tpRetISSQN).
    _sub(mun, "tpRetISSQN", int(s.retencao_iss))
    if deve_informar_paliq(p, s):
        _sub(mun, "pAliq", formatar_decimal(s.aliquota_iss))

    # Optantes do SN: PIS/COFINS/IRPJ/CSLL/CPP são recolhidos no DAS, então não há grupo tribFed.
    tot = _sub(trib, "totTrib")
    if p.opcao_simples == OpcaoSimplesNacional.ME_EPP:
        _sub(tot, "pTotTribSN", formatar_decimal(s.aliquota_simples))  # indTotTrib proibido (E0712)
    else:
        _sub(tot, "indTotTrib", 0)  # MEI: pTotTribSN proibido (E0710)

    return raiz


def montar_pedido_cancelamento(
    *,
    chave_acesso: str,
    documento_autor: str,
    codigo_motivo: int,
    justificativa: str,
    ambiente: int,
    data_evento: datetime | None = None,
    versao: str = VERSAO_LEIAUTE,
) -> etree._Element:
    """Gera o <pedRegEvento> de cancelamento (e101101), ainda sem assinatura."""
    chave = normalizar_chave(chave_acesso)
    if codigo_motivo not in MOTIVOS_CANCELAMENTO:
        raise ErroValidacao(f"motivo de cancelamento inválido; use um de {sorted(MOTIVOS_CANCELAMENTO)}")
    justificativa = normalizar_texto(justificativa)
    if not 15 <= len(justificativa) <= 255:
        raise ErroValidacao("justificativa do cancelamento deve ter entre 15 e 255 caracteres")
    if not re.fullmatch(r"[\x21-\xff][\x20-\xff]*[\x21-\xff]", justificativa):
        raise ErroValidacao("justificativa: use apenas letras, números e pontuação comum (sem emojis)")
    doc = normalizar_documento(documento_autor)
    dh = data_evento or agora_brasilia()
    if dh.tzinfo is None:
        raise ErroValidacao("data_evento precisa ter fuso horário")

    raiz = etree.Element(f"{{{NS}}}pedRegEvento", nsmap={None: NS})
    raiz.set("versao", versao)
    inf = _sub(raiz, "infPedReg")
    inf.set("Id", f"PRE{chave}{TP_EVENTO_CANCELAMENTO}")  # TSIdEvento: "PRE" + chave(50) + tpEvento(6)
    _sub(inf, "tpAmb", ambiente)
    _sub(inf, "verAplic", VERSAO_APLICATIVO)
    _sub(inf, "dhEvento", dh.isoformat(timespec="seconds"))
    _sub(inf, "CNPJAutor" if len(doc) == 14 else "CPFAutor", doc)
    _sub(inf, "chNFSe", chave)
    ev = _sub(inf, "e" + TP_EVENTO_CANCELAMENTO)
    _sub(ev, "xDesc", "Cancelamento de NFS-e")
    _sub(ev, "cMotivo", codigo_motivo)
    _sub(ev, "xMotivo", justificativa)
    return raiz


def normalizar_chave(chave_acesso: str) -> str:
    """Chave de acesso de 50 posições; a inscrição (posições 10–23) pode ter letras (CNPJ alfanumérico)."""
    chave = re.sub(r"[^0-9A-Z]", "", (chave_acesso or "").upper())
    if not re.fullmatch(r"[0-9]{9}[0-9A-Z]{14}[0-9]{27}", chave):
        raise ErroValidacao("chave de acesso inválida: deve ter 50 posições")
    return chave


_TROCAS_TEXTO = str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'", "\u2013": "-", "\u2014": "-", "\u2026": "..."})


def normalizar_texto(texto: str | None) -> str:
    """Troca aspas curvas, travessões e reticências por equivalentes Latin-1 e junta as linhas."""
    return " ".join((texto or "").translate(_TROCAS_TEXTO).split())


def para_bytes(el: etree._Element) -> bytes:
    return etree.tostring(el, xml_declaration=True, encoding="UTF-8")
