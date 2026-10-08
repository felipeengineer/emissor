"""Gera os XMLs de NFS-e de exemplo usados por tests/test_danfse.py.

Uso (na raiz do repositório): ``python tests/fixtures/gerar_fixtures.py``

A DPS embutida é montada por ``emissor.dps.montar_dps`` (como o emissor faz de verdade) e assinada com um
certificado autoassinado gerado na hora; o restante do ``infNFSe`` imita o que a SEFIN Nacional devolve
(dados do emitente vindos do cadastro, valores calculados, ``dhProc``, ``cStat`` etc.) e também é assinado.
As assinaturas são estruturalmente válidas (o XSD exige ``ds:Signature`` na NFSe), mas o certificado não é
ICP-Brasil. Todos os arquivos validam em ``NFSe_v1.01.xsd`` (cópia sem alterações do pacote oficial
``esquemas-nfse-rtc-v1-01-20260727.zip``, que inclui os tipos de ``emissor/schemas/1.01``).

Fixtures:

- ``nfse_me_epp_homologacao.xml``: ME/EPP, produção restrita (tpAmb = 2), tomador com CPF e endereço,
  desconto incondicionado, pTotTribSN.
- ``nfse_mei_producao.xml``: MEI, produção (tpAmb = 1), sem tomador, indTotTrib = 0, cStat 107.
- ``nfse_textos_longos.xml``: ME/EPP em produção com textos no tamanho máximo do leiaute, tomador com CNPJ
  alfanumérico, intermediário, destinatário (grupo IBSCBS), ISS retido, substituição e informações
  complementares. O ``montar_dps`` ainda não gera intermediário, substituição, infoCompl nem IBSCBS, então
  esses grupos são acrescentados à DPS depois de montada, na ordem do XSD.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree

from emissor.assinatura import Certificado, assinar
from emissor.dps import AMBIENTE_HOMOLOGACAO, AMBIENTE_PRODUCAO, NS, DadosDPS, montar_dps
from emissor.modelos import (
    Endereco,
    OpcaoSimplesNacional,
    Prestador,
    RetencaoISS,
    Servico,
    Tomador,
)

PASTA = Path(__file__).parent
SP = ZoneInfo("America/Sao_Paulo")


def _certificado() -> Certificado:
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CERTIFICADO DE TESTE - NAO ICP-BRASIL")])
    agora = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - timedelta(days=1))
        .not_valid_after(agora + timedelta(days=3650))
        .sign(chave, hashes.SHA256())
    )
    return Certificado(chave, cert, [])


def _sub(pai, tag: str, texto=None):
    el = etree.SubElement(pai, f"{{{NS}}}{tag}")
    if texto is not None:
        el.text = str(texto)
    return el


def _depois(el: etree._Element, irmao_anterior: str) -> int:
    """Índice logo após o filho `irmao_anterior` (para inserir na ordem do XSD)."""
    filhos = [etree.QName(f).localname for f in el]
    return filhos.index(irmao_anterior) + 1


def chave_acesso(c_mun: str, amb_ger: int, documento: str, n_nfse: int, competencia: date, c_num: str) -> str:
    """cMun(7) + ambGer(1) + tpInsc(1) + inscrição(14) + nNFSe(13) + AAMM(4) + cNum(9) + DV(1) = 50."""
    tp_insc = "2" if len(documento) == 14 else "1"
    base = f"{c_mun}{amb_ger}{tp_insc}{documento.zfill(14)}{n_nfse:013d}{competencia:%y%m}{c_num}"
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum((ord(c) - 48) * pesos[i % 8] for i, c in enumerate(reversed(base)))
    dv = 11 - soma % 11
    return base + str(0 if dv >= 10 else dv)


def montar_nfse(
    dps: etree._Element,
    *,
    chave: str,
    n_nfse: int,
    x_loc_emi: str,
    x_loc_prestacao: str,
    c_loc_incid: str,
    x_loc_incid: str,
    x_trib_nac: str,
    x_nbs: str | None,
    c_stat: int,
    dh_proc: datetime,
    n_dfse: int,
    emit: dict,
    valores: dict,
    x_out_inf: str | None = None,
    ibscbs: dict | None = None,
    cert: Certificado,
) -> etree._Element:
    raiz = etree.Element(f"{{{NS}}}NFSe", nsmap={None: NS})
    raiz.set("versao", "1.01")
    inf = _sub(raiz, "infNFSe")
    inf.set("Id", "NFS" + chave)
    _sub(inf, "xLocEmi", x_loc_emi)
    _sub(inf, "xLocPrestacao", x_loc_prestacao)
    _sub(inf, "nNFSe", n_nfse)
    _sub(inf, "cLocIncid", c_loc_incid)
    _sub(inf, "xLocIncid", x_loc_incid)
    _sub(inf, "xTribNac", x_trib_nac)
    if x_nbs:
        _sub(inf, "xNBS", x_nbs)
    _sub(inf, "verAplic", "SefinNacional_1.6.0")
    _sub(inf, "ambGer", 2)  # emitida pela Sefin Nacional
    _sub(inf, "tpEmis", 1)
    _sub(inf, "procEmi", 1)  # aplicativo do contribuinte (API)
    _sub(inf, "cStat", c_stat)
    _sub(inf, "dhProc", dh_proc.isoformat(timespec="seconds"))
    _sub(inf, "nDFSe", n_dfse)
    e = _sub(inf, "emit")
    _sub(e, "CNPJ", emit["CNPJ"])
    if emit.get("IM"):
        _sub(e, "IM", emit["IM"])
    _sub(e, "xNome", emit["xNome"])
    end = _sub(e, "enderNac")
    for tag in ("xLgr", "nro", "xCpl", "xBairro", "cMun", "UF", "CEP"):
        if emit["end"].get(tag):
            _sub(end, tag, emit["end"][tag])
    for tag in ("fone", "email"):
        if emit.get(tag):
            _sub(e, tag, emit[tag])
    v = _sub(inf, "valores")
    for tag in ("vCalcDR", "tpBM", "vCalcBM", "vBC", "pAliqAplic", "vISSQN", "vTotalRet", "vLiq"):
        if tag in valores:
            _sub(v, tag, valores[tag])
    if x_out_inf:
        _sub(inf, "xOutInf", x_out_inf)
    if ibscbs:
        g = _sub(inf, "IBSCBS")
        _sub(g, "cLocalidadeIncid", ibscbs["cLocalidadeIncid"])
        _sub(g, "xLocalidadeIncid", ibscbs["xLocalidadeIncid"])
        gv = _sub(g, "valores")
        _sub(gv, "vBC", ibscbs["vBC"])
        uf = _sub(gv, "uf")
        _sub(uf, "pIBSUF", ibscbs["pIBSUF"])
        _sub(uf, "pAliqEfetUF", ibscbs["pIBSUF"])
        mun = _sub(gv, "mun")
        _sub(mun, "pIBSMun", ibscbs["pIBSMun"])
        _sub(mun, "pAliqEfetMun", ibscbs["pIBSMun"])
        fed = _sub(gv, "fed")
        _sub(fed, "pCBS", ibscbs["pCBS"])
        _sub(fed, "pAliqEfetCBS", ibscbs["pCBS"])
        tot = _sub(g, "totCIBS")
        _sub(tot, "vTotNF", ibscbs["vTotNF"])
        gibs = _sub(tot, "gIBS")
        _sub(gibs, "vIBSTot", ibscbs["vIBSTot"])
        _sub(_sub(gibs, "gIBSUFTot"), "vIBSUF", ibscbs["vIBSUF"])
        _sub(_sub(gibs, "gIBSMunTot"), "vIBSMun", ibscbs["vIBSMun"])
        _sub(_sub(tot, "gCBS"), "vCBS", ibscbs["vCBS"])
    inf.append(dps)

    etree.indent(raiz, space="  ")
    assinar(dps, cert)  # assinatura do contribuinte na DPS
    assinar(raiz, cert)  # assinatura da Sefin Nacional na NFS-e
    return raiz


def nfse_me_epp_homologacao(cert: Certificado) -> etree._Element:
    dh = datetime(2026, 10, 8, 10, 15, 0, tzinfo=SP)
    prest = Prestador(
        documento="11222333000181",
        razao_social="(vem do cadastro)",
        codigo_municipio="3534401",  # Osasco/SP
        opcao_simples=OpcaoSimplesNacional.ME_EPP,
        inscricao_municipal="1234567",
        telefone="1136851234",
        email="contato@exemplotecnologia.com.br",
    )
    toma = Tomador(
        documento="52998224725",
        nome="Maria Aparecida dos Santos",
        endereco=Endereco("3550308", "01001000", "Praça da Sé", "100", "Sé", complemento="Conjunto 12"),
        email="maria.santos@example.com",
        telefone="11987654321",
    )
    serv = Servico(
        codigo_tributacao_nacional="010701",
        descricao=(
            "Suporte técnico mensal em informática: manutenção preventiva de 3 estações de trabalho, "
            "atualização do sistema de gestão e backup em nuvem. Referente a setembro/2026."
        ),
        valor=Decimal("1500.50"),
        codigo_municipio_prestacao="3534401",
        codigo_nbs="115013000",
        aliquota_iss=Decimal("2.01"),
        aliquota_simples=Decimal("6.00"),
        desconto_incondicionado=Decimal("50.00"),
    )
    dps = montar_dps(DadosDPS(prest, toma, serv, "1", 27, ambiente=AMBIENTE_HOMOLOGACAO, data_emissao=dh))
    chave = chave_acesso("3534401", 2, "11222333000181", 27, dh.date(), "448812375")
    return montar_nfse(
        dps,
        chave=chave,
        n_nfse=27,
        x_loc_emi="Osasco",
        x_loc_prestacao="Osasco",
        c_loc_incid="3534401",
        x_loc_incid="Osasco",
        x_trib_nac=(
            "Suporte técnico em informática, inclusive instalação, configuração e manutenção de programas "
            "de computação e bancos de dados."
        ),
        x_nbs="Serviços de suporte em tecnologia da informação (TI)",
        c_stat=100,
        dh_proc=dh + timedelta(seconds=3),
        n_dfse=88412,
        emit={
            "CNPJ": "11222333000181",
            "IM": "1234567",
            "xNome": "EXEMPLO TECNOLOGIA E SERVICOS LTDA",
            "end": {"xLgr": "Avenida dos Autonomistas", "nro": "1500", "xCpl": "Sala 304", "xBairro": "Centro",
                    "cMun": "3534401", "UF": "SP", "CEP": "06020010"},
            "fone": "1136851234",
            "email": "contato@exemplotecnologia.com.br",
        },  # fmt: skip
        valores={"vBC": "1450.50", "pAliqAplic": "2.01", "vISSQN": "29.16", "vLiq": "1450.50"},
        cert=cert,
    )


def nfse_mei_producao(cert: Certificado) -> etree._Element:
    dh = datetime(2026, 10, 7, 16, 42, 9, tzinfo=SP)
    prest = Prestador(
        documento="45723174000110",
        razao_social="(vem do cadastro)",
        codigo_municipio="3550308",  # São Paulo/SP
        opcao_simples=OpcaoSimplesNacional.MEI,
    )
    serv = Servico(
        codigo_tributacao_nacional="060101",
        descricao="Corte de cabelo masculino e barba",
        valor=Decimal("80.00"),
        codigo_municipio_prestacao="3550308",
        codigo_nbs="126021000",
    )
    dps = montar_dps(DadosDPS(prest, None, serv, "900", 1532, ambiente=AMBIENTE_PRODUCAO, data_emissao=dh))
    chave = chave_acesso("3550308", 2, "45723174000110", 1532, dh.date(), "000731904")
    return montar_nfse(
        dps,
        chave=chave,
        n_nfse=1532,
        x_loc_emi="São Paulo",
        x_loc_prestacao="São Paulo",
        c_loc_incid="3550308",
        x_loc_incid="São Paulo",
        x_trib_nac="Barbearia, cabeleireiros, manicuros, pedicuros e congêneres.",
        x_nbs="Serviços de cabeleireiros e barbeiros",
        c_stat=107,  # NFS-e MEI
        dh_proc=dh + timedelta(seconds=2),
        n_dfse=771203,
        emit={
            "CNPJ": "45723174000110",
            "xNome": "JOAO DA SILVA BARBEARIA",
            "end": {"xLgr": "Rua Augusta", "nro": "2203", "xBairro": "Jardim Paulista", "cMun": "3550308",
                    "UF": "SP", "CEP": "01413000"},
        },  # fmt: skip
        valores={"vLiq": "80.00"},
        cert=cert,
    )


NOME_TOMADOR_LONGO = (
    "COMPANHIA BRASILEIRA DE DISTRIBUICAO, LOGISTICA INTEGRADA, ARMAZENAGEM, TRANSPORTE MULTIMODAL, "
    "COMERCIO EXTERIOR E SERVICOS DE TECNOLOGIA DA INFORMACAO APLICADA A CADEIA DE SUPRIMENTOS DO "
    "VAREJO NACIONAL E INTERNACIONAL S.A. - FILIAL CENTRO DE DISTRIBUICAO REGIONAL SUDESTE FIM-DO-NOME"
)


def _texto_longo(prefixo: str, tamanho: int, *, quebras: bool) -> str:
    frase = (
        "Implantação de sistema de gestão empresarial com migração de dados legados, parametrização fiscal "
        "das filiais, integração com o e-commerce e treinamento presencial das equipes de faturamento. "
    )
    texto = prefixo
    i = 1
    while len(texto) < tamanho:
        texto += (f"\nEtapa {i}: " if quebras and i % 4 == 0 else f"Etapa {i}: ") + frase
        i += 1
    return texto[: tamanho - 8].rstrip() + " FIM-TXT"


def nfse_textos_longos(cert: Certificado) -> etree._Element:
    dh = datetime(2026, 9, 30, 23, 58, 41, tzinfo=SP)
    prest = Prestador(
        documento="11222333000181",
        razao_social="(vem do cadastro)",
        codigo_municipio="3534401",
        opcao_simples=OpcaoSimplesNacional.ME_EPP,
        inscricao_municipal="1234567",
    )
    toma = Tomador(
        documento="12ABC34501DE35",  # CNPJ alfanumérico (exemplo oficial da RFB: 12.ABC.345/01DE-35)
        nome=NOME_TOMADOR_LONGO,
        endereco=Endereco(
            "3550308",
            "04538132",
            "Avenida Brigadeiro Faria Lima, Torre Corporativa Norte, acesso pela via local paralela à marginal "
            "do rio Pinheiros, portaria de cargas e descargas junto ao estacionamento de visitantes do bloco B",
            "3477",
            "Itaim Bibi",
            complemento="Andar 14, conjuntos 141 a 148, ala oeste, recepção principal do centro de distribuição",
        ),
        email="contas.a.pagar.notas.fiscais.servicos@distribuidora-exemplo-logistica.com.br",
        telefone="1130405060",
        inscricao_municipal="987654321",
    )
    serv = Servico(
        codigo_tributacao_nacional="010701",
        descricao=_texto_longo("Contrato 2026/0042. ", 2000, quebras=True),
        valor=Decimal("12000.00"),
        codigo_municipio_prestacao="3550308",
        codigo_nbs="115013000",
        retencao_iss=RetencaoISS.RETIDO_PELO_TOMADOR,
        aliquota_iss=Decimal("2.00"),
        aliquota_simples=Decimal("11.20"),
    )
    dps = montar_dps(
        DadosDPS(prest, toma, serv, "1", 31, ambiente=AMBIENTE_PRODUCAO, data_emissao=dh, competencia=date(2026, 9, 30))
    )
    inf = dps.find(f"{{{NS}}}infDPS")
    q = {"n": NS}

    # Substituição de NFS-e (vai depois de cLocEmi).
    subst = etree.Element(f"{{{NS}}}subst")
    _sub(subst, "chSubstda", chave_acesso("3534401", 2, "11222333000181", 30, date(2026, 9, 30), "100200300"))
    _sub(subst, "cMotivo", "99")
    _sub(subst, "xMotivo", "Correção do valor contratado")
    inf.insert(_depois(inf, "cLocEmi"), subst)

    # Intermediário (vai depois de toma).
    interm = etree.Element(f"{{{NS}}}interm")
    _sub(interm, "CNPJ", "11444777000161")
    _sub(interm, "IM", "55443322")
    _sub(interm, "xNome", "INTERMEDIADORA DE SERVICOS DIGITAIS S.A.")
    end = _sub(interm, "end")
    nac = _sub(end, "endNac")
    _sub(nac, "cMun", "3304557")
    _sub(nac, "CEP", "20040002")
    _sub(end, "xLgr", "Avenida Rio Branco")
    _sub(end, "nro", "1")
    _sub(end, "xBairro", "Centro")
    _sub(interm, "fone", "2125550100")
    _sub(interm, "email", "nfse@intermediadora.example.com")
    inf.insert(_depois(inf, "toma"), interm)

    # Informações complementares (serv/infoCompl).
    info = _sub(inf.find("n:serv", q), "infoCompl")
    _sub(info, "idDocTec", "DRT-2026-000123")
    _sub(info, "docRef", "Pedido de compra PC-77801 de 01/09/2026")
    _sub(info, "xPed", "PC-77801")
    itens = _sub(info, "gItemPed")
    for item in ("10", "20", "30"):
        _sub(itens, "xItemPed", item)
    _sub(info, "xInfComp", _texto_longo("Observações do contrato: ", 2000, quebras=False))

    # Grupo IBSCBS da DPS (facultativo ao Simples em 2026), com destinatário diferente do tomador.
    ibs = _sub(inf, "IBSCBS")
    _sub(ibs, "finNFSe", "0")
    _sub(ibs, "cIndOp", "100301")
    _sub(ibs, "indDest", "1")
    dest = _sub(ibs, "dest")
    _sub(dest, "CPF", "12345678909")
    _sub(dest, "xNome", "Carlos Eduardo Pereira")
    end = _sub(dest, "end")
    nac = _sub(end, "endNac")
    _sub(nac, "cMun", "3509502")  # Campinas/SP
    _sub(nac, "CEP", "13010111")
    _sub(end, "xLgr", "Rua Barão de Jaguara")
    _sub(end, "nro", "900")
    _sub(end, "xBairro", "Centro")
    _sub(dest, "email", "carlos.pereira@example.com")
    trib = _sub(_sub(_sub(ibs, "valores"), "trib"), "gIBSCBS")
    _sub(trib, "CST", "000")
    _sub(trib, "cClassTrib", "000001")

    chave = chave_acesso("3534401", 2, "11222333000181", 31, dh.date(), "905517262")
    return montar_nfse(
        dps,
        chave=chave,
        n_nfse=31,
        x_loc_emi="Osasco",
        x_loc_prestacao="São Paulo",
        c_loc_incid="3550308",
        x_loc_incid="São Paulo",
        x_trib_nac=(
            "Suporte técnico em informática, inclusive instalação, configuração e manutenção de programas "
            "de computação e bancos de dados."
        ),
        x_nbs="Serviços de suporte em tecnologia da informação (TI)",
        c_stat=100,
        dh_proc=dh + timedelta(seconds=11),
        n_dfse=88513,
        emit={
            "CNPJ": "11222333000181",
            "IM": "1234567",
            "xNome": "EXEMPLO TECNOLOGIA E SERVICOS LTDA",
            "end": {"xLgr": "Avenida dos Autonomistas", "nro": "1500", "xCpl": "Sala 304", "xBairro": "Centro",
                    "cMun": "3534401", "UF": "SP", "CEP": "06020010"},
        },  # fmt: skip
        valores={"vBC": "12000.00", "pAliqAplic": "2.00", "vISSQN": "240.00", "vTotalRet": "240.00", "vLiq": "11760.00"},
        x_out_inf=_texto_longo("Mensagem da Administração Tributária Municipal: ", 2000, quebras=False),
        ibscbs={
            "cLocalidadeIncid": "3550308",
            "xLocalidadeIncid": "São Paulo",
            "vBC": "11760.00",
            "pIBSUF": "0.10",
            "pIBSMun": "0.00",
            "pCBS": "0.90",
            "vTotNF": "11760.00",
            "vIBSTot": "11.76",
            "vIBSUF": "11.76",
            "vIBSMun": "0.00",
            "vCBS": "105.84",
        },
        cert=cert,
    )


GERADORES = {
    "nfse_me_epp_homologacao.xml": nfse_me_epp_homologacao,
    "nfse_mei_producao.xml": nfse_mei_producao,
    "nfse_textos_longos.xml": nfse_textos_longos,
}


def main() -> int:
    cert = _certificado()
    for nome, gerar in GERADORES.items():
        xml = etree.tostring(gerar(cert), xml_declaration=True, encoding="UTF-8")
        (PASTA / nome).write_bytes(xml + b"\n")
        print("gerado", PASTA / nome)
    return 0


if __name__ == "__main__":
    sys.exit(main())
