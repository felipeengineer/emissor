import base64
import gzip
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
from cryptography.x509.oid import NameOID

from emissor.api import ErroSefin, de_gzip_b64
from emissor.banco import Banco
from emissor.servico import Emissor

CNPJ_PRESTADOR = "11222333000181"
CPF_TOMADOR = "52998224725"
CHAVE = "3550308" + "2" + "11222333000181" + "0" * 27 + "1"  # 50 dígitos fictícios


@pytest.fixture
def pfx(tmp_path):
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EMPRESA TESTE LTDA:11222333000181")])
    agora = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - timedelta(days=1))
        .not_valid_after(agora + timedelta(days=365))
        .sign(chave, hashes.SHA256())
    )
    caminho = tmp_path / "teste.pfx"
    caminho.write_bytes(pkcs12.serialize_key_and_certificates(b"teste", chave, cert, None, BestAvailableEncryption(b"1234")))
    return caminho


class ClienteFalso:
    """Simula a SEFIN Nacional."""

    def __init__(self):
        self.enviados = []
        self.eventos = []
        self.eventos_externos = []
        self.erro: ErroSefin | None = None
        self.erro_evento: ErroSefin | None = None

    def emitir(self, xml: bytes):
        self.enviados.append(xml)
        if self.erro:
            raise self.erro
        nfse = (
            '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">'
            f'<infNFSe Id="NFS{CHAVE}"><nNFSe>42</nNFSe></infNFSe></NFSe>'
        ).encode()
        return {"chaveAcesso": CHAVE, "nfseXmlGZipB64": base64.b64encode(gzip.compress(nfse)).decode(), "alertas": []}

    def consultar_dps(self, id_dps):
        return {"chaveAcesso": CHAVE}

    def consultar_nfse(self, chave):
        return self.emitir(b"")

    def registrar_evento(self, chave, xml):
        if self.erro_evento:
            erro, self.erro_evento = self.erro_evento, None
            self.eventos.append((chave, xml))  # simula: a SEFIN registrou, mas a resposta se perdeu
            raise erro
        self.eventos.append((chave, xml))
        return {"eventoXmlGZipB64": ""}

    def consultar_eventos(self, chave):
        return [{"tipoEvento": "101101"} for c, _ in self.eventos if c == chave] + self.eventos_externos

    def parametros_convenio(self, cod):
        return {"codigoMunicipio": cod, "aderenteEmissorNacional": 0}


@pytest.fixture
def cliente_falso():
    return ClienteFalso()


@pytest.fixture
def emissor(tmp_path, monkeypatch, pfx, cliente_falso):
    monkeypatch.setenv("EMISSOR_HOME", str(tmp_path / "dados"))
    monkeypatch.delenv("EMISSOR_CERT_SENHA", raising=False)
    monkeypatch.delenv("EMISSOR_CERT_PFX", raising=False)
    em = Emissor(Banco(tmp_path / "teste.db"), fabrica_cliente=lambda cert, amb: cliente_falso)
    em.salvar_prestador(
        {"documento": CNPJ_PRESTADOR, "razao_social": "Empresa Teste", "codigo_municipio": "3550308", "opcao_simples": 3}
    )
    em.salvar_parametros(
        certificado_caminho=str(pfx),
        certificado_senha="1234",
        servico_padrao={"codigo_tributacao_nacional": "010701", "descricao": "Suporte técnico", "aliquota_simples": "6.00"},
    )
    return em


@pytest.fixture
def tomador():
    return {
        "documento": CPF_TOMADOR,
        "nome": "Fulano de Tal",
        "email": "fulano@example.com",
        "endereco": {
            "codigo_municipio": "3550308",
            "cep": "01001000",
            "logradouro": "Praça da Sé",
            "numero": "1",
            "bairro": "Sé",
        },
    }


def xml_enviado(cliente) -> bytes:
    return cliente.enviados[-1]


__all__ = ["de_gzip_b64", "xml_enviado"]
