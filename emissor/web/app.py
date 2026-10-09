"""Interface web local (Flask) do emissor."""

from __future__ import annotations

import secrets
from functools import wraps

from flask import Flask, Response, abort, flash, redirect, render_template, request, send_file, session, url_for

from ..api import ErroSefin
from ..banco import pasta_dados
from ..dps import MOTIVOS_CANCELAMENTO
from ..modelos import ErroValidacao, normalizar_documento
from ..servico import Emissor, ErroEmissor
from ..simples import anexo_por_fator_r, calcular_aliquotas

ERROS_DE_NEGOCIO = (ErroEmissor, ErroValidacao, ErroSefin, ValueError)

STATUS_ROTULOS = {
    "emitida": "Emitida",
    "rejeitada": "Rejeitada",
    "cancelada": "Cancelada",
    "substituida": "Substituída",
    "pendente": "Pendente",
    "erro_comunicacao": "Erro de comunicação",
}


def _form_tomador(f) -> dict | None:
    doc = normalizar_documento(f.get("tomador_documento"))
    if not doc:
        return None
    if not f.get("tomador_nome"):
        return doc  # tomador já cadastrado
    endereco = None
    if f.get("tomador_cep") or f.get("tomador_logradouro"):
        endereco = {
            "codigo_municipio": f.get("tomador_municipio", ""),
            "cep": f.get("tomador_cep", ""),
            "logradouro": f.get("tomador_logradouro", ""),
            "numero": f.get("tomador_numero", ""),
            "bairro": f.get("tomador_bairro", ""),
            "complemento": f.get("tomador_complemento", ""),
        }
    return {
        "documento": doc,
        "nome": f.get("tomador_nome", ""),
        "email": f.get("tomador_email", ""),
        "telefone": f.get("tomador_telefone", ""),
        "inscricao_municipal": f.get("tomador_im", ""),
        "endereco": endereco,
    }


def _form_servico(f) -> dict:
    campos = (
        "descricao",
        "valor",
        "codigo_tributacao_nacional",
        "codigo_municipio_prestacao",
        "codigo_tributacao_municipal",
        "codigo_nbs",
        "retencao_iss",
        "aliquota_iss",
        "aliquota_simples",
        "desconto_incondicionado",
        "competencia",
    )
    return {c: (f.get(c) or "").strip() for c in campos}


def criar_app(emissor: Emissor | None = None) -> Flask:
    app = Flask(__name__)
    emissor = emissor or Emissor()
    chave = emissor.banco.obter_config("_secret_key")
    if not chave:
        chave = secrets.token_hex(32)
        emissor.banco.salvar_config("_secret_key", chave)
    app.secret_key = chave
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    app.extensions["emissor"] = emissor

    def csrf_token() -> str:
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    @app.before_request
    def verificar_csrf():
        if request.method == "POST" and request.form.get("_csrf") != session.get("_csrf"):
            abort(400, "Token CSRF inválido; recarregue a página.")

    @app.context_processor
    def contexto():
        return {
            "csrf_token": csrf_token,
            "ambiente": emissor.ambiente,
            "status_rotulos": STATUS_ROTULOS,
        }

    def tratar_erros(view):
        @wraps(view)
        def wrapper(*a, **kw):
            try:
                return view(*a, **kw)
            except ERROS_DE_NEGOCIO as e:
                flash(str(e), "erro")
                return redirect(request.referrer or url_for("painel"))

        return wrapper

    @app.get("/")
    def painel():
        return render_template(
            "painel.html",
            status=emissor.status(),
            resumo=emissor.resumo(),
            notas=emissor.listar_notas(limite=10),
        )

    @app.get("/notas")
    def notas():
        busca = request.args.get("q", "")
        status = request.args.get("status") or None
        return render_template("notas.html", notas=emissor.listar_notas(busca=busca, status=status, limite=500), busca=busca, filtro=status)

    @app.route("/notas/nova", methods=["GET", "POST"])
    def nova_nota():
        padrao = emissor.configuracao()["servico_padrao"]
        form = request.form if request.method == "POST" else {}
        preview = None
        if request.method == "POST":
            tomador = _form_tomador(request.form)
            servico = _form_servico(request.form)
            try:
                if request.form.get("acao") == "emitir":
                    nota = emissor.emitir(
                        tomador, servico, confirmar_competencia_anterior=bool(request.form.get("confirmar_competencia"))
                    )
                    if nota["status"] == "emitida":
                        flash(f"NFS-e emitida! Chave de acesso {nota['chave_acesso']}", "ok")
                    else:
                        flash(f"NFS-e não autorizada: {nota.get('mensagem')}", "erro")
                    return redirect(url_for("detalhe_nota", nota_id=nota["id"]))
                preview = emissor.pre_visualizar(tomador, servico)
            except ERROS_DE_NEGOCIO as e:
                flash(str(e), "erro")
        return render_template(
            "nova_nota.html",
            form=form,
            padrao=padrao,
            tomadores=emissor.listar_tomadores(),
            preview=preview,
        )

    @app.get("/notas/<int:nota_id>")
    def detalhe_nota(nota_id: int):
        nota = emissor.obter_nota(nota_id) or abort(404)
        return render_template("detalhe_nota.html", nota=nota, motivos=MOTIVOS_CANCELAMENTO)

    @app.get("/notas/<int:nota_id>/xml/<tipo>")
    def baixar_xml(nota_id: int, tipo: str):
        nota = emissor.obter_nota(nota_id) or abort(404)
        conteudo = nota.get("nfse_xml" if tipo == "nfse" else "dps_xml") or abort(404)
        nome = f"NFSe_{nota['chave_acesso']}.xml" if tipo == "nfse" else f"{nota['id_dps']}.xml"
        return Response(conteudo, mimetype="application/xml", headers={"Content-Disposition": f"attachment; filename={nome}"})

    @app.get("/notas/<int:nota_id>/danfse")
    @tratar_erros
    def danfse(nota_id: int):
        return send_file(emissor.baixar_danfse(nota_id), mimetype="application/pdf")

    @app.post("/notas/<int:nota_id>/sincronizar")
    @tratar_erros
    def sincronizar(nota_id: int):
        nota = emissor.sincronizar(nota_id)
        flash(f"Situação atualizada: {STATUS_ROTULOS.get(nota['status'], nota['status'])}", "ok")
        return redirect(url_for("detalhe_nota", nota_id=nota_id))

    @app.post("/notas/<int:nota_id>/cancelar")
    @tratar_erros
    def cancelar(nota_id: int):
        emissor.cancelar(nota_id, int(request.form["motivo"]), request.form.get("justificativa", ""))
        flash("NFS-e cancelada.", "ok")
        return redirect(url_for("detalhe_nota", nota_id=nota_id))

    @app.route("/tomadores", methods=["GET", "POST"])
    def tomadores():
        if request.method == "POST":
            dados = _form_tomador(request.form)
            try:
                if not isinstance(dados, dict):
                    raise ErroValidacao("Informe documento e nome do tomador")
                emissor.salvar_tomador(dados)
                flash("Tomador salvo.", "ok")
                return redirect(url_for("tomadores"))
            except ERROS_DE_NEGOCIO as e:
                flash(str(e), "erro")
        editar = emissor.obter_tomador(request.args["editar"]) if request.args.get("editar") else None
        return render_template(
            "tomadores.html", tomadores=emissor.listar_tomadores(request.args.get("q", "")), editar=editar, form=request.form
        )

    @app.post("/tomadores/<documento>/excluir")
    def excluir_tomador(documento: str):
        emissor.excluir_tomador(documento)
        flash("Tomador excluído.", "ok")
        return redirect(url_for("tomadores"))

    @app.route("/configuracoes", methods=["GET", "POST"])
    def configuracoes():
        calculo = None
        if request.method == "POST":
            secao = request.form.get("secao")
            f = request.form
            try:
                if secao == "prestador":
                    emissor.salvar_prestador(
                        {k: f.get(k, "") for k in ("documento", "razao_social", "codigo_municipio", "opcao_simples",
                                                    "regime_apuracao_sn", "inscricao_municipal", "telefone", "email")}
                    )
                    flash("Dados do prestador salvos.", "ok")
                elif secao == "certificado":
                    arquivo = request.files.get("pfx")
                    caminho = None
                    if arquivo and arquivo.filename:
                        pasta = pasta_dados() / "certificados"
                        pasta.mkdir(exist_ok=True)
                        destino = pasta / "certificado.pfx"
                        arquivo.save(destino)
                        destino.chmod(0o600)
                        caminho = str(destino)
                    emissor.salvar_parametros(certificado_caminho=caminho, certificado_senha=f.get("senha") or None)
                    c = emissor.certificado()
                    flash(f"Certificado OK: {c.titular} (válido até {c.validade:%d/%m/%Y})", "ok")
                elif secao == "parametros":
                    emissor.salvar_parametros(
                        ambiente=int(f["ambiente"]),
                        serie=f.get("serie", "1"),
                        ultimo_numero_dps=int(f["ultimo_numero_dps"]) if f.get("ultimo_numero_dps") else None,
                        data_autorizacao_emissor_nacional=f.get("data_autorizacao_emissor_nacional", ""),
                    )
                    flash("Parâmetros salvos.", "ok")
                elif secao == "servico_padrao":
                    emissor.salvar_parametros(servico_padrao=_form_servico(f))
                    flash("Serviço padrão salvo.", "ok")
                elif secao == "calculadora":
                    anexo = f.get("anexo") or (anexo_por_fator_r(f["folha"], f["rbt12"]) if f.get("folha") else "III")
                    calculo = calcular_aliquotas(f.get("rbt12", "0").replace(",", "."), anexo)
                    if f.get("aplicar"):
                        padrao = emissor.configuracao()["servico_padrao"]
                        # Só a alíquota efetiva (pTotTribSN). O pAliq do ISS é preenchido pelo próprio
                        # Sistema Nacional quando o município é conveniado.
                        # pTotTribSN = alíquota NOMINAL da faixa (Cartilha 20.5), não a efetiva.
                        padrao.update(aliquota_simples=calculo["aliquota_nominal"])
                        emissor.salvar_parametros(servico_padrao=padrao)
                        flash("Alíquota nominal aplicada ao serviço padrão (pTotTribSN).", "ok")
                if secao != "calculadora":
                    return redirect(url_for("configuracoes"))
            except ERROS_DE_NEGOCIO as e:
                flash(str(e), "erro")
        cfg = emissor.configuracao()
        return render_template(
            "configuracoes.html",
            cfg=cfg,
            prestador=cfg["prestador"] or {},
            padrao=cfg["servico_padrao"],
            ultimo=emissor.banco.ultimo_numero(emissor.ambiente, emissor.serie),
            calculo=calculo,
        )

    @app.template_filter("moeda")
    def moeda(valor) -> str:
        try:
            v = f"{float(valor):,.2f}"
        except (TypeError, ValueError):
            return str(valor)
        return "R$ " + v.replace(",", "X").replace(".", ",").replace("X", ".")

    @app.template_filter("doc")
    def formatar_documento(doc) -> str:
        d = normalizar_documento(doc)
        if len(d) == 14:
            return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
        if len(d) == 11:
            return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
        return doc or ""

    return app


def main(host: str = "127.0.0.1", porta: int = 8000, debug: bool = False) -> None:
    criar_app().run(host=host, port=porta, debug=debug)
