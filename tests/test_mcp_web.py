import asyncio
import json

from emissor.mcp_server import criar_servidor
from emissor.web.app import criar_app

from .conftest import CHAVE


def _rodar(coro):
    return asyncio.run(coro)


def _conteudo(resultado):
    """Extrai o retorno estruturado/JSON de uma chamada de ferramenta, qualquer que seja o formato do SDK."""
    if isinstance(resultado, tuple):
        resultado = resultado[-1] if isinstance(resultado[-1], dict) else resultado[0]
    if isinstance(resultado, dict):
        return resultado.get("result", resultado)
    if hasattr(resultado, "structured_content") and resultado.structured_content is not None:
        sc = resultado.structured_content
        return sc.get("result", sc)
    blocos = resultado.content if hasattr(resultado, "content") else resultado
    return json.loads(blocos[0].text)


def test_mcp_lista_ferramentas(emissor):
    servidor = criar_servidor(emissor)
    nomes = {t.name for t in _rodar(servidor.list_tools())}
    assert {
        "status_emissor",
        "emitir_nfse",
        "pre_visualizar_nfse",
        "cancelar_nfse",
        "consultar_nfse",
        "baixar_danfse",
        "calcular_aliquota_simples",
        "cadastrar_tomador",
    } <= nomes


def test_mcp_emite_nota(emissor, tomador):
    servidor = criar_servidor(emissor)
    r = _conteudo(_rodar(servidor.call_tool("emitir_nfse", {"servico": {"valor": "250.00"}, "tomador": tomador})))
    assert r["status"] == "emitida"
    assert r["chave_acesso"] == CHAVE
    assert "dps_xml" not in r

    notas = _conteudo(_rodar(servidor.call_tool("listar_notas", {})))
    assert notas[0]["valor"] == "250.00"

    calc = _conteudo(_rodar(servidor.call_tool("calcular_aliquota_simples", {"rbt12": "150000"})))
    assert calc["aliquota_efetiva"] == "6.00"


def test_web_fluxo_emissao(emissor, tomador):
    app = criar_app(emissor)
    app.config["TESTING"] = True
    c = app.test_client()
    assert c.get("/").status_code == 200
    assert c.get("/configuracoes").status_code == 200
    pagina = c.get("/notas/nova")
    assert pagina.status_code == 200
    with c.session_transaction() as s:
        token = s["_csrf"]

    # sem token CSRF é recusado
    assert c.post("/notas/nova", data={"valor": "10"}).status_code == 400

    r = c.post(
        "/notas/nova",
        data={"_csrf": token, "acao": "emitir", "valor": "123,45", "tomador_documento": tomador["documento"],
              "tomador_nome": tomador["nome"]},
    )
    assert r.status_code == 302
    detalhe = c.get(r.headers["Location"])
    assert CHAVE.encode() in detalhe.data
    assert "R$ 123,45".encode() in detalhe.data
    assert c.get("/notas/1/xml/nfse").status_code == 200
    assert c.get("/notas/1/danfse").data.startswith(b"%PDF")

    previa = c.post("/notas/nova", data={"_csrf": token, "acao": "previa", "valor": "5"})
    assert b"infDPS" in previa.data
