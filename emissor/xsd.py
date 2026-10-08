"""Validação local dos XMLs contra os esquemas XSD oficiais da NFS-e Nacional."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lxml import etree

from .modelos import ErroValidacao

PASTA_ESQUEMAS = Path(__file__).parent / "schemas"


@lru_cache(maxsize=None)
def _esquema(versao: str, nome: str) -> etree.XMLSchema:
    caminho = PASTA_ESQUEMAS / versao / f"{nome}_v{versao}.xsd"
    if not caminho.exists():
        raise ErroValidacao(f"Esquema {caminho.name} não disponível para o leiaute {versao}")
    return etree.XMLSchema(etree.parse(str(caminho)))


def erros_esquema(doc: etree._Element, nome: str) -> list[str]:
    """Lista de mensagens de erro de validação (vazia se o XML for válido)."""
    esquema = _esquema(doc.get("versao", ""), nome)
    if esquema.validate(doc):
        return []
    return [f"linha {e.line}: {e.message}" for e in esquema.error_log]


def validar_esquema(doc: etree._Element, nome: str) -> None:
    erros = erros_esquema(doc, nome)
    if erros:
        raise ErroValidacao(f"XML não confere com o esquema oficial {nome} {doc.get('versao')}: " + "; ".join(erros))
