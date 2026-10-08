import pytest
from lxml import etree

from emissor.api import ErroSefin
from emissor.assinatura import verificar_assinatura
from emissor.modelos import ErroValidacao
from emissor.servico import ErroEmissor
from emissor.simples import anexo_por_fator_r, calcular_aliquotas

from .conftest import CHAVE


def test_status_pronto(emissor):
    s = emissor.status()
    assert s["pronto_para_emitir"], s["pendencias"]
    assert s["proximo_numero_dps"] == 1
    assert s["certificado"]["titular"].startswith("EMPRESA TESTE")


def test_emitir_com_sucesso(emissor, cliente_falso, tomador):
    nota = emissor.emitir(tomador, {"valor": "1000"})
    assert nota["status"] == "emitida"
    assert nota["chave_acesso"] == CHAVE
    assert nota["numero_nfse"] == "42"
    assert nota["numero_dps"] == 1
    enviado = etree.fromstring(cliente_falso.enviados[-1])
    assert verificar_assinatura(enviado)
    # serviço padrão aplicado
    assert enviado.findtext(".//{*}cTribNac") == "010701"
    assert enviado.findtext(".//{*}pTotTribSN") == "6.00"
    assert emissor.emitir(None, {"valor": "50"})["numero_dps"] == 2


def test_emitir_com_tomador_cadastrado(emissor, tomador):
    emissor.salvar_tomador(tomador)
    nota = emissor.emitir(tomador["documento"], {"valor": "10", "descricao": "Consultoria"})
    assert nota["tomador_nome"] == "Fulano de Tal"
    with pytest.raises(ErroEmissor):
        emissor.emitir("11222333000181", {"valor": "10"})


def test_dados_invalidos_nao_consomem_numero(emissor, cliente_falso):
    with pytest.raises(ErroValidacao):
        emissor.emitir(None, {"valor": "-1"})
    assert not cliente_falso.enviados
    assert emissor.status()["proximo_numero_dps"] == 1


def test_rejeicao_e_erro_de_comunicacao(emissor, cliente_falso):
    cliente_falso.erro = ErroSefin("DPS rejeitada", 400, [{"Codigo": "E0001", "Descricao": "Teste"}])
    nota = emissor.emitir(None, {"valor": "10"})
    assert nota["status"] == "rejeitada"
    assert "E0001" in nota["mensagem"]

    cliente_falso.erro = ErroSefin("timeout")
    nota = emissor.emitir(None, {"valor": "10"})
    assert nota["status"] == "erro_comunicacao"
    cliente_falso.erro = None
    assert emissor.sincronizar(nota["id"])["status"] == "emitida"


def test_cancelar_e_danfse(emissor, cliente_falso):
    nota = emissor.emitir(None, {"valor": "10"})
    pdf = emissor.baixar_danfse(nota["id"])
    assert pdf.read_bytes().startswith(b"%PDF")
    cancelada = emissor.cancelar(nota["id"], 1, "Valor informado incorretamente")
    assert cancelada["status"] == "cancelada"
    assert verificar_assinatura(etree.fromstring(cliente_falso.eventos[-1][1]))
    with pytest.raises(ErroEmissor):
        emissor.cancelar(nota["id"], 1, "Valor informado incorretamente")


def test_resumo(emissor):
    emissor.emitir(None, {"valor": "10"})
    emissor.emitir(None, {"valor": "15.50"})
    r = emissor.resumo()
    assert r["quantidade_emitidas"] == 2
    assert r["valor_total_emitido"] == "25.50"


def test_calculadora_simples():
    r = calcular_aliquotas("150000", "III")
    assert r["aliquota_efetiva"] == "6.00" and r["aliquota_iss"] == "2.01"
    r = calcular_aliquotas("500000", "III")  # (500000*13,5% - 17640)/500000 = 9,972%
    assert r["faixa"] == 3 and r["aliquota_efetiva"] == "9.97" and r["aliquota_iss"] == "3.24"
    r = calcular_aliquotas("3000000", "IV")  # efetiva 15,874% * 40% = 6,35% -> limitado a 5%
    assert r["aliquota_iss"] == "5.00"
    assert anexo_por_fator_r(30000, 100000) == "III"
    assert anexo_por_fator_r(10000, 100000) == "V"
    with pytest.raises(ValueError):
        calcular_aliquotas("5000000")
