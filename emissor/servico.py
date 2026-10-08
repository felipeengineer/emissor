"""Camada de aplicação: regras de emissão compartilhadas pela interface web, CLI e MCP server."""

from __future__ import annotations

import json
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
    SERIE_API_MAX,
    DadosDPS,
    id_dps,
    montar_dps,
    montar_pedido_cancelamento,
    normalizar_chave,
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
    normalizar_documento,
    somente_digitos,
    validar_documento,
)
from .xsd import erros_esquema, validar_esquema

STATUS_PENDENTE = "pendente"
STATUS_EMITIDA = "emitida"
STATUS_REJEITADA = "rejeitada"
STATUS_ERRO_COMUNICACAO = "erro_comunicacao"
STATUS_CANCELADA = "cancelada"
STATUS_SUBSTITUIDA = "substituida"

# Res. CGSN 191/2026: ME/EPP do Simples emite pelo Emissor Nacional a partir desta data.
INICIO_OBRIGATORIEDADE_ME_EPP = date(2026, 11, 1)
OSASCO = "3534401"

TP_EVENTO_CANCELAMENTO = "101101"
TP_EVENTO_CANCELAMENTO_SUBSTITUICAO = "105102"

# Orientação para as rejeições mais prováveis na migração (Anexo I v1.01 e Cartilha v1.1).
DICAS_REJEICAO = {
    "E0010": "Série fora da faixa da API: use uma série entre 1 e 49999.",
    "E0025": "Competência anterior à autorização de uso do Emissor Nacional no cadastro do município: "
    "emita essa nota pelo sistema da prefeitura (Cartilha 5.3).",
    "E0037": "Município emissor sem convênio no Sistema Nacional.",
    "E0038": "Convênio do município ainda não está ativo.",
    "E0039": "O município ainda não liberou os emissores públicos para ME/EPP. Para o Simples Nacional, "
    "a liberação é automática a partir de 01/11/2026; antes disso, teste em produção restrita.",
    "E0084": "CNPJ não habilitado para emitir no Sistema Nacional: confira o cadastro (CNC) do município e o "
    "credenciamento para API no Portal do Contribuinte.",
    "E0160": "A situação no Simples Nacional informada não confere com o cadastro do CNPJ na competência.",
    "E0718": "O certificado digital não é do prestador: use o e-CNPJ da própria empresa.",
}


def dicas_para(erros: list[dict]) -> list[str]:
    codigos = {str(e.get("Codigo") or e.get("codigo") or "").strip().upper() for e in erros or []}
    return [DICAS_REJEICAO[c] for c in sorted(codigos) if c in DICAS_REJEICAO]


def tipos_de_evento(resposta: Any) -> set[str]:
    """Extrai códigos de evento (ex.: 101101) de qualquer formato de resposta da consulta de eventos."""
    tipos: set[str] = set()

    def visitar(v: Any, chave: str = "") -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                visitar(x, k)
        elif isinstance(v, list):
            for x in v:
                visitar(x, chave)
        elif isinstance(v, str):
            if chave.endswith("XmlGZipB64"):
                try:
                    raiz = etree.fromstring(de_gzip_b64(v))
                except Exception:
                    return
                for el in raiz.iter():
                    nome = _localname(el) if isinstance(el.tag, str) else ""
                    if len(nome) == 7 and nome[0] == "e" and nome[1:].isdigit():  # grupo do evento, ex.: e101101
                        tipos.add(nome[1:])
            elif "tipo" in chave.lower() and "evento" in chave.lower():
                tipos.update(c for c in (v, v.strip()) if c.isdigit() and len(c) == 6)
        elif isinstance(v, int) and "tipo" in chave.lower() and "evento" in chave.lower():
            tipos.add(str(v))

    visitar(resposta)
    return tipos


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
            "data_autorizacao_emissor_nacional": self.banco.obter_config("data_autorizacao_emissor_nacional", ""),
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
        data_autorizacao_emissor_nacional: str | None = None,
    ) -> dict:
        if ambiente is not None:
            if int(ambiente) not in (AMBIENTE_PRODUCAO, AMBIENTE_HOMOLOGACAO):
                raise ErroValidacao("ambiente deve ser 1 (produção) ou 2 (homologação)")
            self.banco.salvar_config("ambiente", int(ambiente))
        if serie is not None:
            serie = somente_digitos(serie)
            if not serie or not 1 <= int(serie) <= SERIE_API_MAX:
                raise ErroValidacao(f"série da API deve estar entre 1 e {SERIE_API_MAX} (regra E0010)")
            self.banco.salvar_config("serie", str(int(serie)))
        if certificado_caminho is not None:
            self.banco.salvar_config("certificado_caminho", certificado_caminho)
        if certificado_senha is not None:
            self.banco.salvar_config("certificado_senha", certificado_senha)
        if servico_padrao is not None:
            self.banco.salvar_config("servico_padrao", {k: v for k, v in servico_padrao.items() if v not in (None, "")})
        if ultimo_numero_dps is not None:
            self.banco.definir_ultimo_numero(self.ambiente, self.serie, int(ultimo_numero_dps))
        if data_autorizacao_emissor_nacional is not None:
            if data_autorizacao_emissor_nacional:
                date.fromisoformat(data_autorizacao_emissor_nacional)
            self.banco.salvar_config("data_autorizacao_emissor_nacional", data_autorizacao_emissor_nacional)
        return self.configuracao()

    def data_autorizacao_emissor_nacional(self, prestador: Prestador) -> date | None:
        """Primeira competência aceita pelo Emissor Nacional em produção (regra E0025).

        Configurável; para ME/EPP o padrão é 01/11/2026 (Res. CGSN 191/2026). MEI já emite desde 2023.
        """
        valor = self.banco.obter_config("data_autorizacao_emissor_nacional", "")
        if valor:
            return date.fromisoformat(valor)
        if prestador.opcao_simples == OpcaoSimplesNacional.ME_EPP:
            return INICIO_OBRIGATORIEDADE_ME_EPP
        return None

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

    def _conferir_titular(self, cert: Certificado, prestador: Prestador) -> None:
        """E0718: o documento do certificado deve ser idêntico ao do prestador (não basta a raiz do CNPJ)."""
        doc = cert.documento_titular
        if doc and doc != normalizar_documento(prestador.documento):
            raise ErroEmissor(
                f"O certificado é de {doc}, mas o prestador é {prestador.documento}: a SEFIN rejeita (E0718). "
                "Use o e-CNPJ da própria empresa (o de filial ou do contador não serve)."
            )

    def status(self) -> dict:
        """Diagnóstico do que falta para emitir."""
        pendencias = []
        info: dict[str, Any] = {"ambiente": "produção" if self.ambiente == AMBIENTE_PRODUCAO else "homologação (produção restrita)"}
        try:
            p = self.prestador()
            info["prestador"] = {"documento": p.documento, "razao_social": p.razao_social, "regime": p.opcao_simples.name}
        except ErroEmissor as e:
            pendencias.append(str(e))
        avisos: list[str] = []
        try:
            c = self.certificado()
            info["certificado"] = {"titular": c.titular, "documento": c.documento_titular, "validade": c.validade.date().isoformat()}
            if "prestador" in info:
                try:
                    self._conferir_titular(c, p)
                except ErroEmissor as e:
                    pendencias.append(str(e))
        except ErroEmissor as e:
            pendencias.append(str(e))
        padrao = self.banco.obter_config("servico_padrao", {})
        if not padrao.get("codigo_tributacao_nacional"):
            pendencias.append("Opcional: defina o código de tributação nacional padrão do serviço (cTribNac).")
        if "prestador" in info and p.opcao_simples == OpcaoSimplesNacional.ME_EPP and not padrao.get("aliquota_simples"):
            pendencias.append("Defina a alíquota nominal do Simples (pTotTribSN) no serviço padrão (regra E0712).")
        avisos.append(
            "Emissão via API exige credenciamento prévio no Portal do Contribuinte (página gov.br do serviço). "
            "Confirme com o e-CNPJ e faça uma emissão de teste em produção restrita."
        )
        if "prestador" in info and p.opcao_simples == OpcaoSimplesNacional.ME_EPP and date.today() < INICIO_OBRIGATORIEDADE_ME_EPP:
            texto = "Antes de 01/11/2026 a emissão em produção só funciona se o município tiver liberado o Emissor Nacional (senão: E0039)."
            if somente_digitos(p.codigo_municipio) == OSASCO:
                texto += " Osasco aparece como 'AderenteEmissorNacional = Não' na lista oficial de 28/09/2026; use produção restrita para testar."
            avisos.append(texto)
        info["serie"] = self.serie
        info["proximo_numero_dps"] = self.banco.ultimo_numero(self.ambiente, self.serie) + 1
        info["pronto_para_emitir"] = not [p for p in pendencias if not p.startswith("Opcional")]
        info["pendencias"] = pendencias
        info["avisos"] = avisos
        return info

    # ------------------------------------------------------------------ tomadores
    def salvar_tomador(self, dados: dict) -> dict:
        t = Tomador.de_dict(dados)
        t.validar()
        return self.banco.salvar_tomador(t.para_dict())

    def listar_tomadores(self, busca: str = "") -> list[dict]:
        return self.banco.listar_tomadores(busca)

    def obter_tomador(self, documento: str) -> dict | None:
        return self.banco.obter_tomador(normalizar_documento(documento))

    def excluir_tomador(self, documento: str) -> bool:
        return self.banco.excluir_tomador(normalizar_documento(documento))

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

    def _conferir_competencia(self, prestador: Prestador, competencia: date | None, confirmar: bool) -> None:
        """E0025: em produção, competência anterior à autorização de uso é rejeitada (Cartilha 5.3)."""
        if self.ambiente != AMBIENTE_PRODUCAO or confirmar:
            return
        inicio = self.data_autorizacao_emissor_nacional(prestador)
        comp = competencia or date.today()
        if inicio and comp < inicio:
            raise ErroEmissor(
                f"Competência {comp:%m/%Y} é anterior à autorização do Emissor Nacional ({inicio:%d/%m/%Y}). "
                "Emita essa nota pelo sistema da prefeitura (a SEFIN rejeita com E0025 e a Cartilha 5.3 "
                "proíbe usar os dois sistemas na mesma competência). Se a data de autorização no cadastro do "
                "município for outra, ajuste-a em Configurações ou confirme a emissão."
            )

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

    def emitir(self, tomador: dict | str | None, servico: dict, confirmar_competencia_anterior: bool = False) -> dict:
        """Valida, assina, envia a DPS à SEFIN Nacional e registra o resultado localmente."""
        prestador = self.prestador()
        tom = self._resolver_tomador(tomador)
        serv, competencia = self._montar_servico(servico, prestador)
        self._conferir_competencia(prestador, competencia, confirmar_competencia_anterior)
        # Valida (regras e XSD oficial) antes de reservar número para não "queimar" nDPS com dados inválidos.
        ambiente, serie = self.ambiente, self.serie
        teste = DadosDPS(prestador, tom, serv, serie, self.banco.ultimo_numero(ambiente, serie) + 1, ambiente, competencia=competencia)
        validar_esquema(montar_dps(teste), "DPS")
        cert = self.certificado()
        self._conferir_titular(cert, prestador)

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
            elif dicas := dicas_para(e.erros):
                nota["dica"] = " ".join(dicas)
                self.banco.atualizar_nota(nota_id, mensagem=f"{e} — {nota['dica']}")
                nota["mensagem"] = f"{e} — {nota['dica']}"
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
            # Id do infNFSe = "NFS" + chave de acesso (50 posições)
            inf = next((e for e in etree.fromstring(nfse_xml.encode()).iter() if isinstance(e.tag, str) and _localname(e) == "infNFSe"), None)
            if inf is not None and inf.get("Id", "").startswith("NFS"):
                chave = inf.get("Id")[3:]
        self.banco.atualizar_nota(
            nota_id, status=STATUS_EMITIDA, chave_acesso=chave, numero_nfse=numero, nfse_xml=nfse_xml, mensagem=None
        )

    def sincronizar(self, nota_id: int) -> dict:
        """Confere a nota na SEFIN: se a DPS pendente virou NFS-e e se houve cancelamento/substituição."""
        nota = self._nota_ou_erro(nota_id)
        cliente = self._fabrica_cliente(self.certificado(), nota["ambiente"])
        if nota["chave_acesso"]:
            self._atualizar_por_eventos(nota, cliente)
            return self.obter_nota(nota_id)
        try:
            r = cliente.consultar_dps(nota["id_dps"])
        except ErroSefin as e:
            if e.status_http == 404:
                # O manual não define o 404; a DPS pode ainda não ter sido processada. Não reemita às cegas.
                self.banco.atualizar_nota(
                    nota_id,
                    status=STATUS_ERRO_COMUNICACAO,
                    mensagem="DPS não localizada na SEFIN. Tente sincronizar de novo em alguns minutos antes de reemitir.",
                )
                return self.obter_nota(nota_id)
            raise
        chave = r.get("chaveAcesso")
        if chave:
            r2 = cliente.consultar_nfse(chave)
            r2.setdefault("chaveAcesso", chave)
            self._registrar_autorizacao(nota_id, r2)
        return self.obter_nota(nota_id)

    def _atualizar_por_eventos(self, nota: dict, cliente: Any) -> set[str]:
        """Marca a nota local como cancelada/substituída se a SEFIN tiver o evento (inclusive feito fora do app)."""
        try:
            tipos = tipos_de_evento(cliente.consultar_eventos(nota["chave_acesso"]))
        except ErroSefin:
            return set()
        if TP_EVENTO_CANCELAMENTO_SUBSTITUICAO in tipos and nota["status"] != STATUS_SUBSTITUIDA:
            self.banco.atualizar_nota(nota["id"], status=STATUS_SUBSTITUIDA, mensagem="Substituída por outra NFS-e")
        elif TP_EVENTO_CANCELAMENTO in tipos and nota["status"] not in (STATUS_CANCELADA, STATUS_SUBSTITUIDA):
            self.banco.atualizar_nota(nota["id"], status=STATUS_CANCELADA, mensagem="Cancelamento registrado na SEFIN")
        return tipos

    def consultar(self, chave_acesso: str) -> dict:
        """Consulta a NFS-e e seus eventos na SEFIN e atualiza a cópia local (se existir)."""
        chave = normalizar_chave(chave_acesso)
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
        if local:
            resultado["eventos"] = sorted(self._atualizar_por_eventos(self.obter_nota(local["id"]), cliente))
            resultado["status"] = self.obter_nota(local["id"])["status"]
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
            resposta = cliente.registrar_evento(nota["chave_acesso"], xml)
        except ErroSefin as e:
            # Timeout ou E0840 (evento já existente): o cancelamento pode ter sido registrado. Confere antes.
            codigos = {str(x.get("Codigo") or x.get("codigo") or "") for x in e.erros}
            if e.status_http is None or e.status_http >= 500 or "E0840" in codigos:
                if TP_EVENTO_CANCELAMENTO in self._atualizar_por_eventos(nota, cliente):
                    return self.obter_nota(nota_id)
            raise ErroEmissor(f"Cancelamento não aceito: {e}") from e
        self._guardar_evento(nota["chave_acesso"], resposta)
        self.banco.atualizar_nota(nota_id, status=STATUS_CANCELADA, mensagem=f"Cancelada: {justificativa}")
        return self.obter_nota(nota_id)

    @staticmethod
    def _guardar_evento(chave: str, resposta: Any) -> None:
        """Guarda a resposta do registro de evento (o XML do evento é a prova do cancelamento)."""
        pasta = pasta_dados() / "eventos"
        pasta.mkdir(exist_ok=True)
        (pasta / f"{chave}_{TP_EVENTO_CANCELAMENTO}.json").write_text(json.dumps(resposta, ensure_ascii=False))
        if isinstance(resposta, dict):
            for k, v in resposta.items():
                if k.endswith("XmlGZipB64") and isinstance(v, str):
                    try:
                        (pasta / f"{chave}_{TP_EVENTO_CANCELAMENTO}.xml").write_bytes(de_gzip_b64(v))
                    except Exception:
                        pass

    def consultar_convenio(self, codigo_municipio: str | None = None) -> Any:
        """Parâmetros do convênio do município na SEFIN (padrão: município do prestador)."""
        cod = somente_digitos(codigo_municipio or self.prestador().codigo_municipio)
        cliente = self._fabrica_cliente(self.certificado(), self.ambiente)
        try:
            return cliente.parametros_convenio(cod)
        except ErroSefin as e:
            raise ErroEmissor(str(e)) from e

    def baixar_danfse(self, nota_id: int) -> Path:
        """Gera o DANFSe (PDF) localmente a partir do XML da NFS-e, conforme a NT 008 v1.02.

        A API de DANFSe do ADN foi desativada em 03/08/2026; o documento fiscal é o XML (Cartilha 17.8).
        """
        from .danfse import gerar_danfse

        nota = self._nota_ou_erro(nota_id)
        if not nota["chave_acesso"]:
            raise ErroEmissor("Nota sem chave de acesso (ainda não autorizada).")
        if not nota["nfse_xml"]:
            self.consultar(nota["chave_acesso"])
            nota = self._nota_ou_erro(nota_id)
            if not nota["nfse_xml"]:
                raise ErroEmissor("XML da NFS-e indisponível para gerar o DANFSe.")
        pdf = gerar_danfse(
            nota["nfse_xml"],
            cancelada=nota["status"] == STATUS_CANCELADA,
            substituida=nota["status"] == STATUS_SUBSTITUIDA,
        )
        pasta = pasta_dados() / "danfse"
        pasta.mkdir(exist_ok=True)
        destino = pasta / f"NFSe_{nota['chave_acesso']}.pdf"
        destino.write_bytes(pdf)  # sempre regenera: a situação (cancelada/substituída) pode ter mudado
        return destino

    @staticmethod
    def url_consulta_publica(chave: str) -> str:
        return f"https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave={chave}"

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
            "canceladas": sum(1 for n in notas if n["status"] in (STATUS_CANCELADA, STATUS_SUBSTITUIDA)),
            "rejeitadas": sum(1 for n in notas if n["status"] == STATUS_REJEITADA),
            "pendentes": sum(1 for n in notas if n["status"] in (STATUS_PENDENTE, STATUS_ERRO_COMUNICACAO)),
        }
