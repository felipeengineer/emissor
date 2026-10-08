"""Camada de aplicação: regras de emissão compartilhadas pela interface web, CLI e MCP server."""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from lxml import etree

from .api import ClienteSefin, ErroSefin, de_gzip_b64
from .assinatura import Certificado, ErroCertificado, assinar
from .banco import Banco, pasta_dados
from .dps import (
    AMBIENTE_HOMOLOGACAO,
    AMBIENTE_PRODUCAO,
    DadosDPS,
    id_dps,
    montar_dps,
    montar_pedido_cancelamento,
    para_bytes,
)
from .modelos import (
    ErroValidacao,
    OpcaoSimplesNacional,
    Prestador,
    RegimeApuracaoSN,
    RetencaoISS,
    Servico,
    Tomador,
    somente_digitos,
    validar_documento,
)
from .xsd import erros_esquema, validar_esquema

STATUS_PENDENTE = "pendente"
STATUS_EMITIDA = "emitida"
STATUS_REJEITADA = "rejeitada"
STATUS_ERRO_COMUNICACAO = "erro_comunicacao"
STATUS_CANCELADA = "cancelada"


class ErroEmissor(Exception):
    """Erro de negócio exibido ao usuário (configuração incompleta, nota inexistente etc.)."""


def _localname(el: etree._Element) -> str:
    return etree.QName(el).localname


def extrair_campo_xml(xml: bytes | str, nome: str) -> str | None:
    if isinstance(xml, str):
        xml = xml.encode()
    raiz = etree.fromstring(xml)
    for el in raiz.iter():
        if isinstance(el.tag, str) and _localname(el) == nome:
            return el.text
    return None


class Emissor:
    def __init__(
        self,
        banco: Banco | None = None,
        fabrica_cliente: Callable[[Certificado, int], Any] | None = None,
    ):
        self.banco = banco or Banco()
        self._fabrica_cliente = fabrica_cliente or (lambda cert, amb: ClienteSefin(cert, amb))

    # ------------------------------------------------------------------ configuração
    def configuracao(self) -> dict:
        return {
            "prestador": self.banco.obter_config("prestador"),
            "ambiente": self.banco.obter_config("ambiente", AMBIENTE_HOMOLOGACAO),
            "serie": self.banco.obter_config("serie", "1"),
            "certificado_caminho": self.banco.obter_config("certificado_caminho", ""),
            "certificado_senha_definida": bool(self._senha_certificado()),
            "servico_padrao": self.banco.obter_config("servico_padrao", {}),
        }

    def salvar_prestador(self, dados: dict) -> dict:
        p = Prestador(
            documento=dados["documento"],
            razao_social=dados.get("razao_social", ""),
            codigo_municipio=dados["codigo_municipio"],
            opcao_simples=OpcaoSimplesNacional(int(dados.get("opcao_simples", 3))),
            regime_apuracao_sn=RegimeApuracaoSN(int(dados.get("regime_apuracao_sn", 1))),
            inscricao_municipal=dados.get("inscricao_municipal", "") or "",
            telefone=dados.get("telefone", "") or "",
            email=dados.get("email", "") or "",
        )
        p.validar()
        d = asdict(p)
        d["opcao_simples"] = int(p.opcao_simples)
        d["regime_apuracao_sn"] = int(p.regime_apuracao_sn)
        self.banco.salvar_config("prestador", d)
        return d

    def salvar_parametros(
        self,
        *,
        ambiente: int | None = None,
        serie: str | None = None,
        certificado_caminho: str | None = None,
        certificado_senha: str | None = None,
        servico_padrao: dict | None = None,
        ultimo_numero_dps: int | None = None,
    ) -> dict:
        if ambiente is not None:
            if int(ambiente) not in (AMBIENTE_PRODUCAO, AMBIENTE_HOMOLOGACAO):
                raise ErroValidacao("ambiente deve ser 1 (produção) ou 2 (homologação)")
            self.banco.salvar_config("ambiente", int(ambiente))
        if serie is not None:
            serie = somente_digitos(serie)
            if not 1 <= len(serie) <= 5:
                raise ErroValidacao("série deve ter de 1 a 5 dígitos")
            self.banco.salvar_config("serie", serie)
        if certificado_caminho is not None:
            self.banco.salvar_config("certificado_caminho", certificado_caminho)
        if certificado_senha is not None:
            self.banco.salvar_config("certificado_senha", certificado_senha)
        if servico_padrao is not None:
            self.banco.salvar_config("servico_padrao", {k: v for k, v in servico_padrao.items() if v not in (None, "")})
        if ultimo_numero_dps is not None:
            self.banco.definir_ultimo_numero(self.ambiente, self.serie, int(ultimo_numero_dps))
        return self.configuracao()

    @property
    def ambiente(self) -> int:
        return int(self.banco.obter_config("ambiente", AMBIENTE_HOMOLOGACAO))

    @property
    def serie(self) -> str:
        return str(self.banco.obter_config("serie", "1"))

    def _senha_certificado(self) -> str:
        return os.environ.get("EMISSOR_CERT_SENHA") or self.banco.obter_config("certificado_senha", "") or ""

    def prestador(self) -> Prestador:
        d = self.banco.obter_config("prestador")
        if not d:
            raise ErroEmissor("Prestador não configurado. Cadastre os dados da empresa em Configurações.")
        return Prestador(
            documento=d["documento"],
            razao_social=d.get("razao_social", ""),
            codigo_municipio=d["codigo_municipio"],
            opcao_simples=OpcaoSimplesNacional(d.get("opcao_simples", 3)),
            regime_apuracao_sn=RegimeApuracaoSN(d.get("regime_apuracao_sn", 1)),
            inscricao_municipal=d.get("inscricao_municipal", ""),
            telefone=d.get("telefone", ""),
            email=d.get("email", ""),
        )

    def certificado(self) -> Certificado:
        caminho = os.environ.get("EMISSOR_CERT_PFX") or self.banco.obter_config("certificado_caminho", "")
        if not caminho:
            raise ErroEmissor("Certificado digital A1 (.pfx) não configurado.")
        try:
            cert = Certificado.carregar_pfx(caminho, self._senha_certificado())
        except ErroCertificado as e:
            raise ErroEmissor(str(e)) from e
        if cert.vencido:
            raise ErroEmissor(f"Certificado vencido em {cert.validade:%d/%m/%Y}.")
        return cert

    def status(self) -> dict:
        """Diagnóstico do que falta para emitir."""
        pendencias = []
        info: dict[str, Any] = {"ambiente": "produção" if self.ambiente == AMBIENTE_PRODUCAO else "homologação (produção restrita)"}
        try:
            p = self.prestador()
            info["prestador"] = {"documento": p.documento, "razao_social": p.razao_social, "regime": p.opcao_simples.name}
        except ErroEmissor as e:
            pendencias.append(str(e))
        try:
            c = self.certificado()
            info["certificado"] = {"titular": c.titular, "validade": c.validade.date().isoformat()}
        except ErroEmissor as e:
            pendencias.append(str(e))
        padrao = self.banco.obter_config("servico_padrao", {})
        if not padrao.get("codigo_tributacao_nacional"):
            pendencias.append("Opcional: defina o código de tributação nacional padrão do serviço (cTribNac).")
        info["serie"] = self.serie
        info["proximo_numero_dps"] = self.banco.ultimo_numero(self.ambiente, self.serie) + 1
        info["pronto_para_emitir"] = not [p for p in pendencias if not p.startswith("Opcional")]
        info["pendencias"] = pendencias
        return info

    # ------------------------------------------------------------------ tomadores
    def salvar_tomador(self, dados: dict) -> dict:
        t = Tomador.de_dict(dados)
        t.validar()
        return self.banco.salvar_tomador(t.para_dict())

    def listar_tomadores(self, busca: str = "") -> list[dict]:
        return self.banco.listar_tomadores(busca)

    def obter_tomador(self, documento: str) -> dict | None:
        return self.banco.obter_tomador(somente_digitos(documento))

    def excluir_tomador(self, documento: str) -> bool:
        return self.banco.excluir_tomador(somente_digitos(documento))

    def _resolver_tomador(self, tomador: dict | str | None) -> Tomador | None:
        if tomador in (None, "", {}):
            return None
        if isinstance(tomador, str):
            doc = validar_documento(tomador, "tomador")
            salvo = self.banco.obter_tomador(doc)
            if not salvo:
                raise ErroEmissor(f"Tomador {doc} não cadastrado. Informe os dados completos ou cadastre-o antes.")
            return Tomador.de_dict(salvo)
        if set(tomador) <= {"documento", "id"}:
            return self._resolver_tomador(tomador["documento"])
        t = Tomador.de_dict(tomador)
        t.validar()
        return t

    # ------------------------------------------------------------------ DPS
    def _montar_servico(self, dados: dict, prestador: Prestador) -> tuple[Servico, date | None]:
        padrao = self.banco.obter_config("servico_padrao", {}) or {}

        def campo(nome, default=None):
            v = dados.get(nome)
            return v if v not in (None, "") else padrao.get(nome, default)

        if dados.get("valor") in (None, ""):
            raise ErroValidacao("servico.valor é obrigatório")
        aliq_iss = campo("aliquota_iss")
        aliq_sn = campo("aliquota_simples")
        servico = Servico(
            codigo_tributacao_nacional=campo("codigo_tributacao_nacional", ""),
            descricao=campo("descricao", ""),
            valor=dados["valor"],
            codigo_municipio_prestacao=campo("codigo_municipio_prestacao", prestador.codigo_municipio),
            codigo_tributacao_municipal=campo("codigo_tributacao_municipal", "") or "",
            codigo_nbs=campo("codigo_nbs", "") or "",
            retencao_iss=RetencaoISS(int(campo("retencao_iss", 1))),
            aliquota_iss=Decimal(str(aliq_iss)) if aliq_iss not in (None, "") else None,
            aliquota_simples=Decimal(str(aliq_sn)) if aliq_sn not in (None, "") else None,
            desconto_incondicionado=dados.get("desconto_incondicionado") or Decimal("0"),
        )
        competencia = dados.get("competencia")
        if isinstance(competencia, str) and competencia:
            competencia = date.fromisoformat(competencia)
        return servico, competencia or None

    def pre_visualizar(self, tomador: dict | str | None, servico: dict) -> dict:
        """Monta a DPS (sem assinar, sem reservar número e sem enviar) para conferência."""
        prestador = self.prestador()
        serv, competencia = self._montar_servico(servico, prestador)
        numero = self.banco.ultimo_numero(self.ambiente, self.serie) + 1
        dados = DadosDPS(prestador, self._resolver_tomador(tomador), serv, self.serie, numero, self.ambiente, competencia=competencia)
        dps = montar_dps(dados)
        return {
            "id_dps": id_dps(prestador, self.serie, numero),
            "numero_dps": numero,
            "ambiente": self.ambiente,
            "versao": dps.get("versao"),
            "erros_esquema": erros_esquema(dps, "DPS"),
            "xml": para_bytes(dps).decode(),
        }

    def emitir(self, tomador: dict | str | None, servico: dict) -> dict:
        """Valida, assina, envia a DPS à SEFIN Nacional e registra o resultado localmente."""
        prestador = self.prestador()
        tom = self._resolver_tomador(tomador)
        serv, competencia = self._montar_servico(servico, prestador)
        # Valida (regras e XSD oficial) antes de reservar número para não "queimar" nDPS com dados inválidos.
        ambiente, serie = self.ambiente, self.serie
        teste = DadosDPS(prestador, tom, serv, serie, self.banco.ultimo_numero(ambiente, serie) + 1, ambiente, competencia=competencia)
        validar_esquema(montar_dps(teste), "DPS")
        cert = self.certificado()

        numero = self.banco.proximo_numero_dps(ambiente, serie)
        dados = DadosDPS(prestador, tom, serv, serie, numero, ambiente, competencia=competencia)
        dps = assinar(montar_dps(dados), cert)
        validar_esquema(dps, "DPS")
        xml_assinado = para_bytes(dps)
        ident = id_dps(prestador, serie, numero)

        nota_id = self.banco.criar_nota(
            ambiente=ambiente,
            serie=serie,
            numero_dps=numero,
            id_dps=ident,
            status=STATUS_PENDENTE,
            tomador_documento=tom.documento if tom else None,
            tomador_nome=tom.nome if tom else None,
            descricao=serv.descricao,
            valor=str(serv.valor),
            dps_xml=xml_assinado.decode(),
        )
        cliente = self._fabrica_cliente(cert, ambiente)
        try:
            resposta = cliente.emitir(xml_assinado)
        except ErroSefin as e:
            comunicacao = e.status_http is None or e.status_http >= 500
            self.banco.atualizar_nota(
                nota_id,
                status=STATUS_ERRO_COMUNICACAO if comunicacao else STATUS_REJEITADA,
                mensagem=str(e),
            )
            nota = self.obter_nota(nota_id)
            nota["erros"] = e.erros
            if comunicacao:
                nota["dica"] = "A nota pode ter sido autorizada. Use 'sincronizar' para consultar a DPS na SEFIN."
            return nota

        self._registrar_autorizacao(nota_id, resposta)
        nota = self.obter_nota(nota_id)
        if resposta.get("alertas"):
            nota["alertas"] = resposta["alertas"]
        return nota

    def _registrar_autorizacao(self, nota_id: int, resposta: dict) -> None:
        chave = resposta.get("chaveAcesso")
        nfse_xml = de_gzip_b64(resposta["nfseXmlGZipB64"]).decode() if resposta.get("nfseXmlGZipB64") else None
        numero = extrair_campo_xml(nfse_xml, "nNFSe") if nfse_xml else None
        if not chave and nfse_xml:
            # Id do infNFSe = "NFS" + chave de acesso (50 dígitos)
            inf = next((e for e in etree.fromstring(nfse_xml.encode()).iter() if isinstance(e.tag, str) and _localname(e) == "infNFSe"), None)
            if inf is not None and inf.get("Id", "").startswith("NFS"):
                chave = inf.get("Id")[3:]
        self.banco.atualizar_nota(
            nota_id, status=STATUS_EMITIDA, chave_acesso=chave, numero_nfse=numero, nfse_xml=nfse_xml, mensagem=None
        )

    def sincronizar(self, nota_id: int) -> dict:
        """Para notas pendentes/com erro de comunicação: verifica na SEFIN se a DPS virou NFS-e."""
        nota = self._nota_ou_erro(nota_id)
        cliente = self._fabrica_cliente(self.certificado(), nota["ambiente"])
        try:
            r = cliente.consultar_dps(nota["id_dps"])
        except ErroSefin as e:
            if e.status_http == 404:
                self.banco.atualizar_nota(nota_id, status=STATUS_REJEITADA, mensagem="DPS não encontrada na SEFIN (não foi autorizada).")
                return self.obter_nota(nota_id)
            raise
        chave = r.get("chaveAcesso")
        if chave:
            r2 = cliente.consultar_nfse(chave)
            r2.setdefault("chaveAcesso", chave)
            self._registrar_autorizacao(nota_id, r2)
        return self.obter_nota(nota_id)

    def consultar(self, chave_acesso: str) -> dict:
        """Consulta a NFS-e na SEFIN e atualiza a cópia local (se existir)."""
        chave = somente_digitos(chave_acesso)
        local = self.banco.obter_nota(chave_acesso=chave)
        cliente = self._fabrica_cliente(self.certificado(), local["ambiente"] if local else self.ambiente)
        r = cliente.consultar_nfse(chave)
        xml = de_gzip_b64(r["nfseXmlGZipB64"]).decode() if r.get("nfseXmlGZipB64") else None
        resultado = {
            "chave_acesso": chave,
            "numero_nfse": extrair_campo_xml(xml, "nNFSe") if xml else None,
            "xml": xml,
        }
        if local and xml:
            self.banco.atualizar_nota(local["id"], nfse_xml=xml, numero_nfse=resultado["numero_nfse"])
        return resultado

    def cancelar(self, nota_id: int, codigo_motivo: int, justificativa: str) -> dict:
        nota = self._nota_ou_erro(nota_id)
        if nota["status"] != STATUS_EMITIDA or not nota["chave_acesso"]:
            raise ErroEmissor(f"Só é possível cancelar notas emitidas (status atual: {nota['status']}).")
        prestador = self.prestador()
        cert = self.certificado()
        pedido = montar_pedido_cancelamento(
            chave_acesso=nota["chave_acesso"],
            documento_autor=prestador.documento,
            codigo_motivo=int(codigo_motivo),
            justificativa=justificativa,
            ambiente=nota["ambiente"],
        )
        pedido = assinar(pedido, cert)
        validar_esquema(pedido, "pedRegEvento")
        xml = para_bytes(pedido)
        cliente = self._fabrica_cliente(cert, nota["ambiente"])
        try:
            cliente.registrar_evento(nota["chave_acesso"], xml)
        except ErroSefin as e:
            raise ErroEmissor(f"Cancelamento não aceito: {e}") from e
        self.banco.atualizar_nota(nota_id, status=STATUS_CANCELADA, mensagem=f"Cancelada: {justificativa}")
        return self.obter_nota(nota_id)

    def baixar_danfse(self, nota_id: int) -> Path:
        nota = self._nota_ou_erro(nota_id)
        if not nota["chave_acesso"]:
            raise ErroEmissor("Nota sem chave de acesso (ainda não autorizada).")
        pasta = pasta_dados() / "danfse"
        pasta.mkdir(exist_ok=True)
        destino = pasta / f"NFSe_{nota['chave_acesso']}.pdf"
        if not destino.exists():
            cliente = self._fabrica_cliente(self.certificado(), nota["ambiente"])
            try:
                destino.write_bytes(cliente.baixar_danfse(nota["chave_acesso"]))
            except ErroSefin as e:
                raise ErroEmissor(str(e)) from e
        return destino

    # ------------------------------------------------------------------ notas
    def obter_nota(self, nota_id: int) -> dict | None:
        return self.banco.obter_nota(nota_id)

    def _nota_ou_erro(self, nota_id: int) -> dict:
        nota = self.banco.obter_nota(int(nota_id))
        if not nota:
            raise ErroEmissor(f"Nota {nota_id} não encontrada.")
        return nota

    def listar_notas(self, **filtros) -> list[dict]:
        return self.banco.listar_notas(**filtros)

    def resumo(self, ano_mes: str | None = None) -> dict:
        """Totais de notas emitidas (útil para conferir o faturamento do mês / RBT12)."""
        notas = self.banco.listar_notas(limite=100_000, ambiente=self.ambiente)
        if ano_mes:
            notas = [n for n in notas if n["criado_em"].startswith(ano_mes)]
        emitidas = [n for n in notas if n["status"] == STATUS_EMITIDA]
        return {
            "periodo": ano_mes or "todos",
            "quantidade_emitidas": len(emitidas),
            "valor_total_emitido": str(sum((Decimal(n["valor"]) for n in emitidas), Decimal("0.00"))),
            "canceladas": sum(1 for n in notas if n["status"] == STATUS_CANCELADA),
            "rejeitadas": sum(1 for n in notas if n["status"] == STATUS_REJEITADA),
            "pendentes": sum(1 for n in notas if n["status"] in (STATUS_PENDENTE, STATUS_ERRO_COMUNICACAO)),
        }
