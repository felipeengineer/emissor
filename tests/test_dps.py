from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from lxml import etree

from emissor.assinatura import Certificado, assinar, verificar_assinatura
from emissor.dps import NS, DadosDPS, id_dps, montar_dps, montar_pedido_cancelamento, para_bytes
from emissor.modelos import (
    Endereco,
    ErroValidacao,
    OpcaoSimplesNacional,
    Prestador,
    Servico,
    Tomador,
    cnpj_valido,
    cpf_valido,
)

N = {"n": NS}


def prestador(**kw):
    base = dict(documento="11.222.333/0001-81", razao_social="X", codigo_municipio="3550308")
    base.update(kw)
    return Prestador(**base)


def servico(**kw):
    base = dict(
        codigo_tributacao_nacional="01.07.01",
        descricao="Suporte técnico em informática",
        valor="1500,5",
        codigo_municipio_prestacao="3550308",
        aliquota_simples=Decimal("6"),
    )
    base.update(kw)
    return Servico(**base)


def test_validacao_documentos():
    assert cpf_valido("529.982.247-25")
    assert not cpf_valido("111.111.111-11")
    assert cnpj_valido("11.222.333/0001-81")
    assert not cnpj_valido("11.222.333/0001-82")


def test_id_dps_tem_45_caracteres():
    ident = id_dps(prestador(), "1", 27)
    assert ident == "DPS" + "3550308" + "2" + "11222333000181" + "00001" + "000000000000027"
    assert len(ident) == 45


def test_montar_dps_me_epp():
    dh = datetime(2026, 10, 8, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    tom = Tomador(
        "529.982.247-25",
        "Fulano",
        Endereco("3550308", "01001-000", "Praça da Sé", "1", "Sé"),
        email="f@example.com",
    )
    raiz = montar_dps(DadosDPS(prestador(), tom, servico(aliquota_iss="2.01"), "1", 27, data_emissao=dh))
    inf = raiz.find("n:infDPS", N)
    assert raiz.get("versao") == "1.00"
    assert inf.findtext("n:dhEmi", namespaces=N) == "2026-10-08T10:00:00-03:00"
    assert inf.findtext("n:nDPS", namespaces=N) == "27"
    assert inf.findtext("n:prest/n:CNPJ", namespaces=N) == "11222333000181"
    assert inf.find("n:prest/n:xNome", N) is None  # vem do cadastro nacional
    assert inf.findtext("n:prest/n:regTrib/n:opSimpNac", namespaces=N) == "3"
    assert inf.findtext("n:prest/n:regTrib/n:regApTribSN", namespaces=N) == "1"
    assert inf.findtext("n:toma/n:CPF", namespaces=N) == "52998224725"
    assert inf.findtext("n:toma/n:end/n:endNac/n:CEP", namespaces=N) == "01001000"
    assert inf.findtext("n:serv/n:cServ/n:cTribNac", namespaces=N) == "010701"
    assert inf.findtext("n:valores/n:vServPrest/n:vServ", namespaces=N) == "1500.50"
    assert inf.findtext("n:valores/n:trib/n:tribMun/n:pAliq", namespaces=N) == "2.01"
    assert inf.findtext("n:valores/n:trib/n:totTrib/n:pTotTribSN", namespaces=N) == "6.00"
    assert inf.find("n:valores/n:trib/n:tribFed", N) is None
    # ordem dos filhos de infDPS conforme o leiaute
    ordem = [etree.QName(e).localname for e in inf]
    assert ordem == ["tpAmb", "dhEmi", "verAplic", "serie", "nDPS", "dCompet", "tpEmit", "cLocEmi", "prest", "toma", "serv", "valores"]


def test_mei_nao_informa_regime_nem_aliquotas():
    p = prestador(opcao_simples=OpcaoSimplesNacional.MEI)
    raiz = montar_dps(DadosDPS(p, None, servico(aliquota_iss="2"), "1", 1))
    inf = raiz.find("n:infDPS", N)
    assert inf.findtext("n:prest/n:regTrib/n:opSimpNac", namespaces=N) == "2"
    assert inf.find("n:prest/n:regTrib/n:regApTribSN", N) is None
    assert inf.find(".//n:pAliq", N) is None
    assert inf.findtext(".//n:totTrib/n:indTotTrib", namespaces=N) == "0"
    assert inf.find("n:toma", N) is None


@pytest.mark.parametrize(
    "kw",
    [
        {"valor": "0"},
        {"codigo_tributacao_nacional": "123"},
        {"codigo_municipio_prestacao": "35"},
        {"aliquota_iss": "7"},
        {"descricao": " "},
    ],
)
def test_servico_invalido(kw):
    with pytest.raises(ErroValidacao):
        montar_dps(DadosDPS(prestador(), None, servico(**kw), "1", 1))


def test_iss_retido_exige_tomador():
    with pytest.raises(ErroValidacao):
        montar_dps(DadosDPS(prestador(), None, servico(retencao_iss=2), "1", 1))


def test_assinatura_valida_e_detecta_adulteracao(pfx):
    cert = Certificado.carregar_pfx(pfx, "1234")
    raiz = assinar(montar_dps(DadosDPS(prestador(), None, servico(), "1", 1)), cert)
    xml = para_bytes(raiz)
    doc = etree.fromstring(xml)
    assert verificar_assinatura(doc)
    assert doc[-1].tag == "{http://www.w3.org/2000/09/xmldsig#}Signature"
    assert doc.find(".//{*}Reference").get("URI") == "#" + doc[0].get("Id")

    doc.find(".//n:vServ", N).text = "9999.00"
    assert not verificar_assinatura(doc)


def test_pedido_cancelamento(pfx):
    chave = "1" * 50
    raiz = montar_pedido_cancelamento(
        chave_acesso=chave, documento_autor="11222333000181", codigo_motivo=1, justificativa="Valor informado errado", ambiente=2
    )
    inf = raiz.find("n:infPedReg", N)
    assert inf.get("Id") == f"PRE{chave}101101001"
    assert inf.findtext("n:e101101/n:cMotivo", namespaces=N) == "1"
    assert verificar_assinatura(assinar(raiz, Certificado.carregar_pfx(pfx, "1234")))
    with pytest.raises(ErroValidacao):
        montar_pedido_cancelamento(chave_acesso=chave, documento_autor="1", codigo_motivo=1, justificativa="curta", ambiente=2)
