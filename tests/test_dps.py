from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from lxml import etree

from emissor.api import ClienteSefin, ErroSefin
from emissor.assinatura import Certificado, assinar, verificar_assinatura
from emissor.xsd import erros_esquema
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
    assert raiz.get("versao") == "1.01"
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
    trib_mun = [etree.QName(e).localname for e in inf.find("n:valores/n:trib/n:tribMun", N)]
    assert trib_mun == ["tribISSQN", "tpRetISSQN", "pAliq"]  # ordem do leiaute 1.01
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


TOMADOR_COMPLETO = Tomador(
    "52998224725",
    "Fulano",
    Endereco("3550308", "01001000", "Praça da Sé", "1", "Sé", "apto 2"),
    email="f@example.com",
    telefone="1133334444",
    inscricao_municipal="999",
)


@pytest.mark.parametrize(
    "prest, tom, serv",
    [
        # ME/EPP com todos os campos opcionais, ISS retido e desconto
        (
            prestador(inscricao_municipal="12345", telefone="11999999999", email="a@example.com"),
            TOMADOR_COMPLETO,
            servico(codigo_tributacao_municipal="001", codigo_nbs="123456789", retencao_iss=2,
                    aliquota_iss="2.01", desconto_incondicionado="10"),
        ),
        (prestador(), None, servico(aliquota_simples=None)),  # sem tomador e sem alíquotas
        (prestador(opcao_simples=OpcaoSimplesNacional.MEI), TOMADOR_COMPLETO, servico()),  # MEI
        (prestador(documento="52998224725"), Tomador("11222333000181", "ACME"), servico()),  # prestador CPF, tomador CNPJ
    ],
)
def test_dps_confere_com_xsd_oficial(pfx, prest, tom, serv):
    raiz = montar_dps(DadosDPS(prest, tom, serv, "1", 27))
    assert erros_esquema(raiz, "DPS") == []
    assinado = etree.fromstring(para_bytes(assinar(raiz, Certificado.carregar_pfx(pfx, "1234"))))
    assert erros_esquema(assinado, "DPS") == []


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
    assert inf.get("Id") == f"PRE{chave}101101"
    assert inf.findtext("n:e101101/n:cMotivo", namespaces=N) == "1"
    assinado = assinar(raiz, Certificado.carregar_pfx(pfx, "1234"))
    assert verificar_assinatura(assinado)
    assert erros_esquema(etree.fromstring(para_bytes(assinado)), "pedRegEvento") == []
    with pytest.raises(ErroValidacao):
        montar_pedido_cancelamento(chave_acesso=chave, documento_autor="1", codigo_motivo=1, justificativa="curta", ambiente=2)


class _Resposta:
    def __init__(self, status, corpo):
        import json as _json

        self.status_code, self.ok, self._corpo = status, status < 400, corpo
        self.text = _json.dumps(corpo)

    def json(self):
        return self._corpo


@pytest.mark.parametrize(
    "corpo",
    [
        {"erro": [{"Codigo": "E0008", "Descricao": "dhEmi posterior"}]},  # formato da emissão/evento
        {"erro": {"codigo": "E0008", "descricao": "dhEmi posterior"}},
        {"erros": [{"Codigo": "E0008", "Descricao": "dhEmi posterior"}]},
    ],
)
def test_erros_da_sefin_sao_lidos(corpo):
    with pytest.raises(ErroSefin) as exc:
        ClienteSefin._json_ou_erro(_Resposta(400, corpo), "DPS rejeitada")
    assert "E0008" in str(exc.value) and exc.value.status_http == 400
