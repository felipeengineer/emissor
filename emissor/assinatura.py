"""Certificado digital ICP-Brasil (A1/.pfx) e assinatura XMLDSig enveloped (RSA-SHA1, C14N)."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

DS = "http://www.w3.org/2000/09/xmldsig#"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
RSA_SHA1 = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
SHA1 = "http://www.w3.org/2000/09/xmldsig#sha1"


class ErroCertificado(Exception):
    pass


@dataclass
class Certificado:
    chave: rsa.RSAPrivateKey
    certificado: x509.Certificate
    cadeia: list[x509.Certificate]

    @classmethod
    def carregar_pfx(cls, caminho: str | os.PathLike, senha: str) -> "Certificado":
        try:
            dados = Path(caminho).read_bytes()
        except OSError as e:
            raise ErroCertificado(f"Não foi possível ler o certificado: {e}") from e
        try:
            chave, cert, cadeia = pkcs12.load_key_and_certificates(dados, senha.encode() if senha else None)
        except ValueError as e:
            raise ErroCertificado("Senha do certificado incorreta ou arquivo .pfx inválido") from e
        if chave is None or cert is None:
            raise ErroCertificado("O arquivo .pfx não contém chave privada e certificado")
        if not isinstance(chave, rsa.RSAPrivateKey):
            raise ErroCertificado("Somente certificados com chave RSA são suportados")
        return cls(chave, cert, list(cadeia or []))

    @property
    def titular(self) -> str:
        cn = self.certificado.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
        return cn[0].value if cn else self.certificado.subject.rfc4514_string()

    @property
    def documento_titular(self) -> str | None:
        """CNPJ (OtherName 2.16.76.1.3.3) ou CPF (2.16.76.1.3.1) do titular ICP-Brasil.

        Sem a extensão, usa o sufixo ":<documento>" do CN. A SEFIN exige que o documento do
        certificado seja idêntico ao do emitente da DPS (E0718, Cartilha 17.2).
        """
        try:
            san = self.certificado.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        except x509.ExtensionNotFound:
            san = None
        if san is not None:
            valores = {o.type_id.dotted_string: o.value for o in san.get_values_for_type(x509.OtherName)}
            if m := re.search(rb"[0-9A-Z]{14}", valores.get("2.16.76.1.3.3", b"")):
                return m.group().decode()
            if m := re.search(rb"[0-9]{19}", valores.get("2.16.76.1.3.1", b"")):
                return m.group().decode()[8:]  # data de nascimento (8) + CPF (11)
        m = re.search(r":([0-9A-Z]{14}|[0-9]{11})$", self.titular)
        return m.group(1) if m else None

    @property
    def validade(self) -> datetime:
        return self.certificado.not_valid_after_utc

    @property
    def vencido(self) -> bool:
        return self.validade < datetime.now(timezone.utc)

    def der_base64(self) -> str:
        return base64.b64encode(self.certificado.public_bytes(serialization.Encoding.DER)).decode()

    @contextlib.contextmanager
    def arquivos_pem(self):
        """Grava cert/chave em arquivos temporários (0600) para TLS mútuo com `requests`; apaga ao sair."""
        pasta = tempfile.mkdtemp(prefix="emissor-tls-")
        cert_path = os.path.join(pasta, "cert.pem")
        key_path = os.path.join(pasta, "key.pem")
        try:
            pem_cert = self.certificado.public_bytes(serialization.Encoding.PEM) + b"".join(
                c.public_bytes(serialization.Encoding.PEM) for c in self.cadeia
            )
            pem_key = self.chave.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
            for caminho, conteudo in ((cert_path, pem_cert), (key_path, pem_key)):
                fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as f:
                    f.write(conteudo)
            yield cert_path, key_path
        finally:
            for caminho in (cert_path, key_path):
                with contextlib.suppress(FileNotFoundError):
                    os.remove(caminho)
            with contextlib.suppress(OSError):
                os.rmdir(pasta)


def _c14n(el: etree._Element) -> bytes:
    return etree.tostring(el, method="c14n", exclusive=False, with_comments=False)


def assinar(raiz: etree._Element, certificado: Certificado, id_elemento_filho: str | None = None) -> etree._Element:
    """Assina (enveloped) o primeiro filho de `raiz` que tenha atributo Id; a <Signature> vai ao final da raiz."""
    alvo = None
    for filho in raiz:
        if filho.get("Id") and (id_elemento_filho is None or filho.get("Id") == id_elemento_filho):
            alvo = filho
            break
    if alvo is None:
        raise ValueError("Elemento com atributo Id não encontrado para assinar")
    ref_id = alvo.get("Id")

    digest = base64.b64encode(hashlib.sha1(_c14n(alvo)).digest()).decode()

    sig = etree.SubElement(raiz, f"{{{DS}}}Signature", nsmap={None: DS})
    si = etree.SubElement(sig, f"{{{DS}}}SignedInfo")
    etree.SubElement(si, f"{{{DS}}}CanonicalizationMethod", Algorithm=C14N)
    etree.SubElement(si, f"{{{DS}}}SignatureMethod", Algorithm=RSA_SHA1)
    ref = etree.SubElement(si, f"{{{DS}}}Reference", URI=f"#{ref_id}")
    trs = etree.SubElement(ref, f"{{{DS}}}Transforms")
    etree.SubElement(trs, f"{{{DS}}}Transform", Algorithm=ENVELOPED)
    etree.SubElement(trs, f"{{{DS}}}Transform", Algorithm=C14N)
    etree.SubElement(ref, f"{{{DS}}}DigestMethod", Algorithm=SHA1)
    etree.SubElement(ref, f"{{{DS}}}DigestValue").text = digest

    valor = certificado.chave.sign(_c14n(si), padding.PKCS1v15(), hashes.SHA1())
    etree.SubElement(sig, f"{{{DS}}}SignatureValue").text = base64.b64encode(valor).decode()
    ki = etree.SubElement(sig, f"{{{DS}}}KeyInfo")
    x509d = etree.SubElement(ki, f"{{{DS}}}X509Data")
    etree.SubElement(x509d, f"{{{DS}}}X509Certificate").text = certificado.der_base64()
    return raiz


def verificar_assinatura(raiz: etree._Element) -> bool:
    """Confere digest e assinatura de um XML assinado por `assinar` (útil em testes e diagnósticos)."""
    sig = raiz.find(f"{{{DS}}}Signature")
    if sig is None:
        return False
    si = sig.find(f"{{{DS}}}SignedInfo")
    uri = si.find(f"{{{DS}}}Reference").get("URI").lstrip("#")
    alvo = next((f for f in raiz if f.get("Id") == uri), None)
    if alvo is None:
        return False
    digest = base64.b64encode(hashlib.sha1(_c14n(alvo)).digest()).decode()
    if digest != si.find(f".//{{{DS}}}DigestValue").text:
        return False
    der = base64.b64decode(sig.find(f".//{{{DS}}}X509Certificate").text)
    pub = x509.load_der_x509_certificate(der).public_key()
    try:
        pub.verify(
            base64.b64decode(sig.find(f"{{{DS}}}SignatureValue").text),
            _c14n(si),
            padding.PKCS1v15(),
            hashes.SHA1(),
        )
    except Exception:
        return False
    return True
