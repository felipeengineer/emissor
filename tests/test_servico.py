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


def test_certificado_de_outro_cnpj_e_recusado(emissor, cliente_falso):
    # O certificado de teste é de 11222333000181; trocar o prestador simula o e-CNPJ do contador (E0718).
    emissor.salvar_prestador({"documento": "12ABC34501DE35", "codigo_municipio": "3534401", "opcao_simples": 3})
    with pytest.raises(ErroEmissor, match="E0718"):
        emissor.emitir(None, {"valor": "10"})
    assert not cliente_falso.enviados
    assert any("E0718" in p for p in emissor.status()["pendencias"])


def test_competencia_anterior_a_migracao_em_producao(emissor, cliente_falso):
    emissor.salvar_parametros(ambiente=1, data_autorizacao_emissor_nacional="2026-11-01")
    with pytest.raises(ErroEmissor, match="E0025"):
        emissor.emitir(None, {"valor": "10", "competencia": "2026-10-20"})
    assert not cliente_falso.enviados
    nota = emissor.emitir(None, {"valor": "10", "competencia": "2026-11-03"})
    assert nota["status"] == "emitida"
    # confirmação explícita libera (ex.: data de autorização diferente no cadastro do município)
    assert emissor.emitir(None, {"valor": "10", "competencia": "2026-10-20"}, confirmar_competencia_anterior=True)["status"] == "emitida"


def test_homologacao_nao_bloqueia_competencia(emissor):
    assert emissor.emitir(None, {"valor": "10", "competencia": "2026-10-01"})["status"] == "emitida"


def test_rejeicao_traz_orientacao(emissor, cliente_falso):
    cliente_falso.erro = ErroSefin("DPS rejeitada", 400, [{"Codigo": "E0039", "Descricao": "x"}])
    nota = emissor.emitir(None, {"valor": "10"})
    assert nota["status"] == "rejeitada"
    assert "01/11/2026" in nota["dica"] and "01/11/2026" in nota["mensagem"]


def test_cancelamento_com_timeout_e_reconciliado(emissor, cliente_falso):
    nota = emissor.emitir(None, {"valor": "10"})
    cliente_falso.erro_evento = ErroSefin("timeout")
    assert emissor.cancelar(nota["id"], 1, "Valor informado incorretamente")["status"] == "cancelada"


def test_sincronizar_detecta_cancelamento_feito_fora(emissor, cliente_falso):
    nota = emissor.emitir(None, {"valor": "10"})
    cliente_falso.eventos_externos = [{"tipoEvento": "105102"}]
    assert emissor.sincronizar(nota["id"])["status"] == "substituida"


def test_serie_fora_da_faixa_da_api(emissor):
    with pytest.raises(ErroValidacao, match="E0010"):
        emissor.salvar_parametros(serie="70000")
