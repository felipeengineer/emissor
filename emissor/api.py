"""Cliente das APIs do Sistema Nacional NFS-e (SEFIN Nacional e ADN), com TLS mútuo via certificado A1."""

from __future__ import annotations

import base64
import gzip
import os
from dataclasses import dataclass, field
from typing import Any

import requests

from .assinatura import Certificado
from .dps import AMBIENTE_PRODUCAO

# A produção restrita usa o prefixo /API/ (página gov.br "APIs – Prod. Restrita e Produção", citada pelo
# levantamento; os manuais baixados não trazem a URL base). Pode ser sobrescrita pelas variáveis
# EMISSOR_SEFIN_URL_PRODUCAO e EMISSOR_SEFIN_URL_HOMOLOGACAO.
URLS = {
    AMBIENTE_PRODUCAO: {
        "sefin": "https://sefin.nfse.gov.br/SefinNacional",
        "adn": "https://adn.nfse.gov.br",
    },
    2: {
        "sefin": "https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional",
        "adn": "https://adn.producaorestrita.nfse.gov.br",
    },
}
_VARIAVEIS_URL = {AMBIENTE_PRODUCAO: "EMISSOR_SEFIN_URL_PRODUCAO", 2: "EMISSOR_SEFIN_URL_HOMOLOGACAO"}


def url_base(ambiente: int, servico: str = "sefin") -> str:
    if servico == "sefin" and os.environ.get(_VARIAVEIS_URL[ambiente]):
        return os.environ[_VARIAVEIS_URL[ambiente]].rstrip("/")
    return URLS[ambiente][servico]


def gzip_b64(xml: bytes) -> str:
    return base64.b64encode(gzip.compress(xml)).decode()


def de_gzip_b64(dados: str) -> bytes:
    return gzip.decompress(base64.b64decode(dados))


@dataclass
class ErroSefin(Exception):
    """Rejeição ou falha de comunicação com a SEFIN Nacional."""

    mensagem: str
    status_http: int | None = None
    erros: list[dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        if not self.erros:
            return self.mensagem
        detalhes = "; ".join(
            f"{e.get('Codigo') or e.get('codigo', '')}: {e.get('Descricao') or e.get('descricao', '')}"
            + (f" ({e.get('Complemento') or e.get('complemento')})" if e.get("Complemento") or e.get("complemento") else "")
            for e in self.erros
        )
        return f"{self.mensagem} — {detalhes}"


class ClienteSefin:
    def __init__(self, certificado: Certificado, ambiente: int, timeout: float = 60.0, sessao: requests.Session | None = None):
        if ambiente not in URLS:
            raise ValueError("ambiente deve ser 1 (produção) ou 2 (homologação)")
        self.certificado = certificado
        self.ambiente = ambiente
        self.timeout = timeout
        self.sessao = sessao or requests.Session()

    def _requisitar(self, metodo: str, servico: str, caminho: str, json: dict | None = None) -> requests.Response:
        url = url_base(self.ambiente, servico) + caminho
        with self.certificado.arquivos_pem() as (cert, chave):
            try:
                return self.sessao.request(
                    metodo,
                    url,
                    json=json,
                    cert=(cert, chave),
                    timeout=self.timeout,
                    headers={"Accept": "application/json"},
                )
            except requests.RequestException as e:
                raise ErroSefin(f"Falha de comunicação com {url}: {e}") from e

    @staticmethod
    def _json_ou_erro(resp: requests.Response, contexto: str) -> Any:
        try:
            corpo = resp.json()
        except ValueError:
            corpo = None
        if resp.ok and isinstance(corpo, (dict, list)):
            return corpo
        erros: list[dict[str, Any]] = []
        if isinstance(corpo, dict):
            # A SEFIN usa "erros" ou "erro" (singular na emissão e no evento), com lista ou objeto.
            erros = corpo.get("erros") or corpo.get("Erros") or corpo.get("erro") or corpo.get("Erro") or []
            if isinstance(erros, dict):
                erros = [erros]
            if not erros and (corpo.get("mensagem") or corpo.get("message")):
                erros = [{"Descricao": corpo.get("mensagem") or corpo.get("message")}]
        elif resp.text:
            erros = [{"Descricao": resp.text[:500]}]
        raise ErroSefin(f"{contexto}: HTTP {resp.status_code}", resp.status_code, erros)

    def emitir(self, dps_assinada: bytes) -> dict[str, Any]:
        """POST /nfse — envia a DPS e devolve a resposta (chaveAcesso, nfseXmlGZipB64, alertas...)."""
        resp = self._requisitar("POST", "sefin", "/nfse", json={"dpsXmlGZipB64": gzip_b64(dps_assinada)})
        return self._json_ou_erro(resp, "DPS rejeitada")

    def consultar_nfse(self, chave_acesso: str) -> dict[str, Any]:
        resp = self._requisitar("GET", "sefin", f"/nfse/{chave_acesso}")
        return self._json_ou_erro(resp, "Consulta de NFS-e")

    def consultar_dps(self, id_dps: str) -> dict[str, Any]:
        """GET /dps/{id} — devolve a chave da NFS-e gerada a partir de uma DPS (útil após timeout)."""
        resp = self._requisitar("GET", "sefin", f"/dps/{id_dps}")
        return self._json_ou_erro(resp, "Consulta de DPS")

    def registrar_evento(self, chave_acesso: str, pedido_assinado: bytes) -> dict[str, Any]:
        resp = self._requisitar(
            "POST",
            "sefin",
            f"/nfse/{chave_acesso}/eventos",
            json={"pedidoRegistroEventoXmlGZipB64": gzip_b64(pedido_assinado)},
        )
        return self._json_ou_erro(resp, "Evento rejeitado")

    def consultar_eventos(self, chave_acesso: str) -> Any:
        """GET /nfse/{chave}/eventos — eventos vinculados (cancelamento, substituição...). 404 = nenhum."""
        resp = self._requisitar("GET", "sefin", f"/nfse/{chave_acesso}/eventos")
        if resp.status_code == 404:
            return []
        return self._json_ou_erro(resp, "Consulta de eventos")

    def parametros_convenio(self, codigo_municipio: str) -> Any:
        """GET /parametros_municipais/{municipio}/convenio — situação do convênio do município.

        Campos citados na Cartilha 19.6: aderenteEmissorNacional (0 = ME/EPP rejeitada por E0039) e
        situacaoEmissaoPadraoContribuintesRFB (0 = exige cadastro no CNC, senão E0084).
        """
        resp = self._requisitar("GET", "sefin", f"/parametros_municipais/{codigo_municipio}/convenio")
        return self._json_ou_erro(resp, "Consulta de convênio municipal")
