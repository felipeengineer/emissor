"""Modelos de domínio e validações (CPF/CNPJ, códigos, valores)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import IntEnum


class ErroValidacao(ValueError):
    """Dados inválidos para montar a DPS."""


class OpcaoSimplesNacional(IntEnum):
    """opSimpNac do leiaute da DPS."""

    NAO_OPTANTE = 1
    MEI = 2
    ME_EPP = 3


class RegimeApuracaoSN(IntEnum):
    """regApTribSN: só se aplica a ME/EPP (opSimpNac=3)."""

    TRIBUTOS_FEDERAIS_E_ISS_PELO_SN = 1
    FEDERAIS_PELO_SN_ISS_FORA = 2  # sublimite excedido: ISS apurado pelo município
    FEDERAIS_E_ISS_FORA = 3


class RetencaoISS(IntEnum):
    """tpRetISSQN."""

    NAO_RETIDO = 1
    RETIDO_PELO_TOMADOR = 2
    RETIDO_PELO_INTERMEDIARIO = 3


def somente_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def normalizar_documento(valor: str | None) -> str:
    """CPF/CNPJ sem máscara. Mantém letras (CNPJ alfanumérico, em produção desde 10/08/2026)."""
    return re.sub(r"[^0-9A-Z]", "", (valor or "").upper())


def cpf_valido(cpf: str) -> bool:
    cpf = somente_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        dv = (soma * 10) % 11 % 10
        if dv != int(cpf[tamanho]):
            return False
    return True


def cnpj_valido(cnpj: str) -> bool:
    """CNPJ numérico ou alfanumérico: 12 posições [0-9A-Z] + 2 DVs numéricos.

    O DV usa o valor ASCII − 48 de cada caractere (igual ao dígito para 0–9) e os pesos do módulo 11.
    """
    cnpj = normalizar_documento(cnpj)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", cnpj) or cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum((ord(c) - 48) * p for c, p in zip(cnpj[:pos], pesos))
        resto = soma % 11
        dv = 0 if resto < 2 else 11 - resto
        if dv != int(cnpj[pos]):
            return False
    return True


def validar_documento(doc: str, campo: str = "documento") -> str:
    """Retorna o CPF/CNPJ normalizado (sem máscara), ou levanta ErroValidacao."""
    d = normalizar_documento(doc)
    if len(d) == 11 and cpf_valido(d):
        return d
    if len(d) == 14 and cnpj_valido(d):
        return d
    raise ErroValidacao(f"{campo}: CPF/CNPJ inválido ({doc!r})")


def decimal2(valor, campo: str = "valor") -> Decimal:
    try:
        d = Decimal(str(valor).replace(",", ".")) if not isinstance(valor, Decimal) else valor
    except InvalidOperation as e:
        raise ErroValidacao(f"{campo}: número inválido ({valor!r})") from e
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def formatar_decimal(d: Decimal) -> str:
    return f"{d:.2f}"


@dataclass
class Endereco:
    codigo_municipio: str  # IBGE, 7 dígitos
    cep: str
    logradouro: str
    numero: str
    bairro: str
    complemento: str = ""

    def validar(self, prefixo: str = "endereco") -> None:
        if len(somente_digitos(self.codigo_municipio)) != 7:
            raise ErroValidacao(f"{prefixo}.codigo_municipio deve ter 7 dígitos (código IBGE)")
        if len(somente_digitos(self.cep)) != 8:
            raise ErroValidacao(f"{prefixo}.cep deve ter 8 dígitos")
        for nome in ("logradouro", "numero", "bairro"):
            if not getattr(self, nome).strip():
                raise ErroValidacao(f"{prefixo}.{nome} é obrigatório")


@dataclass
class Prestador:
    """Empresa emitente (optante pelo Simples Nacional)."""

    documento: str  # CNPJ (ou CPF para MEI/autônomo)
    razao_social: str
    codigo_municipio: str  # município do estabelecimento emissor (cLocEmi)
    opcao_simples: OpcaoSimplesNacional = OpcaoSimplesNacional.ME_EPP
    regime_apuracao_sn: RegimeApuracaoSN = RegimeApuracaoSN.TRIBUTOS_FEDERAIS_E_ISS_PELO_SN
    inscricao_municipal: str = ""
    telefone: str = ""
    email: str = ""

    def validar(self) -> None:
        self.documento = validar_documento(self.documento, "prestador.documento")
        if len(somente_digitos(self.codigo_municipio)) != 7:
            raise ErroValidacao("prestador.codigo_municipio deve ter 7 dígitos (código IBGE)")
        self.opcao_simples = OpcaoSimplesNacional(int(self.opcao_simples))
        self.regime_apuracao_sn = RegimeApuracaoSN(int(self.regime_apuracao_sn))
        if self.opcao_simples == OpcaoSimplesNacional.NAO_OPTANTE:
            raise ErroValidacao("Este emissor é voltado a optantes do Simples Nacional (MEI ou ME/EPP)")


@dataclass
class Tomador:
    documento: str  # CPF ou CNPJ
    nome: str
    endereco: Endereco | None = None
    email: str = ""
    telefone: str = ""
    inscricao_municipal: str = ""

    def validar(self) -> None:
        self.documento = validar_documento(self.documento, "tomador.documento")
        if not self.nome.strip():
            raise ErroValidacao("tomador.nome é obrigatório")
        if self.endereco:
            self.endereco.validar("tomador.endereco")

    @classmethod
    def de_dict(cls, d: dict) -> "Tomador":
        end = d.get("endereco")
        return cls(
            documento=d["documento"],
            nome=d["nome"],
            endereco=Endereco(**end) if end else None,
            email=d.get("email") or "",
            telefone=d.get("telefone") or "",
            inscricao_municipal=d.get("inscricao_municipal") or "",
        )

    def para_dict(self) -> dict:
        return asdict(self)


@dataclass
class Servico:
    codigo_tributacao_nacional: str  # cTribNac: 6 dígitos (item, subitem, desdobro) da LC 116
    descricao: str
    valor: Decimal
    codigo_municipio_prestacao: str  # cLocPrestacao (IBGE)
    codigo_tributacao_municipal: str = ""  # cTribMun (3 dígitos), opcional
    codigo_nbs: str = ""  # cNBS, opcional
    retencao_iss: RetencaoISS = RetencaoISS.NAO_RETIDO
    aliquota_iss: Decimal | None = None  # pAliq (%): ver dps.deve_informar_paliq (regras E0621 a E0640)
    aliquota_simples: Decimal | None = None  # pTotTribSN (%): alíquota NOMINAL da faixa do SN (Cartilha 20.5)
    desconto_incondicionado: Decimal = field(default_factory=lambda: Decimal("0"))
    # Convênio do município de incidência ativo no Sistema Nacional (quase todos, inclusive Osasco).
    municipio_incidencia_conveniado: bool = True

    def validar(self) -> None:
        self.codigo_tributacao_nacional = somente_digitos(self.codigo_tributacao_nacional)
        if len(self.codigo_tributacao_nacional) != 6:
            raise ErroValidacao("servico.codigo_tributacao_nacional deve ter 6 dígitos (ex.: 010701)")
        if not self.descricao.strip():
            raise ErroValidacao("servico.descricao é obrigatória")
        if len(self.descricao) > 2000:
            raise ErroValidacao("servico.descricao: máximo de 2000 caracteres")
        self.valor = decimal2(self.valor, "servico.valor")
        if self.valor <= 0:
            raise ErroValidacao("servico.valor deve ser maior que zero")
        if len(somente_digitos(self.codigo_municipio_prestacao)) != 7:
            raise ErroValidacao("servico.codigo_municipio_prestacao deve ter 7 dígitos (código IBGE)")
        self.retencao_iss = RetencaoISS(int(self.retencao_iss))
        if self.aliquota_iss is not None:
            self.aliquota_iss = decimal2(self.aliquota_iss, "servico.aliquota_iss")
            if not Decimal("0") <= self.aliquota_iss <= Decimal("5"):
                raise ErroValidacao("servico.aliquota_iss deve estar entre 0 e 5%")
        if self.aliquota_simples is not None:
            self.aliquota_simples = decimal2(self.aliquota_simples, "servico.aliquota_simples")
            if not Decimal("0") < self.aliquota_simples < Decimal("100"):
                raise ErroValidacao("servico.aliquota_simples deve ser maior que 0 e menor que 100%")
        self.desconto_incondicionado = decimal2(self.desconto_incondicionado, "servico.desconto_incondicionado")
        if self.desconto_incondicionado < 0 or self.desconto_incondicionado >= self.valor:
            raise ErroValidacao("servico.desconto_incondicionado inválido")
