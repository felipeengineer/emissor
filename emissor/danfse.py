"""Geração local do DANFSe (Documento Auxiliar da NFS-e) em PDF, conforme a NT 008 SE/CGNFS-e v1.02.

A API de DANFSe do ADN foi desativada em 03/08/2026; desde então cabe ao software emissor renderizar o
PDF a partir do XML da NFS-e. `gerar_danfse` é uma função pura: lê somente o XML da NFS-e (raiz
``NFSe/infNFSe``, com a DPS dentro) e devolve os bytes do PDF, em página única A4 retrato, com os blocos
e as posições do item 2.4.5 e a disposição do Anexo I da NT.

Decisões e desvios em relação à NT 008 (pontos que ela não resolve ou que não dá para seguir à risca):

- Fontes: a NT pede Arial (títulos/labels) e Microsoft Sans Serif (conteúdo). Usamos Helvetica e
  Helvetica-Bold, fontes-padrão do PDF com métricas equivalentes às da Arial, para não depender de
  fontes proprietárias. Tamanhos mínimos e cores (K100, M100/Y100, K35, fundo K5) seguem a NT.
- Logomarca: o PNG oficial não está disponível offline; no lugar dele desenhamos "NFS-e" estilizado.
- Posições: seguimos a ordem e as colunas do modelo do Anexo I, que é obrigatório (§2.2.4), onde ele
  diverge da tabela 2.4.5, cujos tamanhos são só sugestão (§2.1): "Regime de Apuração Tributária pelo SN"
  e os campos da 1ª linha do ISSQN ficam nas colunas do modelo. A altura que sobra (blocos suprimidos e
  linhas ** vazias) vai para "Descrição do Serviço" e "Informações Complementares" (§2.3).
- Prestador: a NT aponta para DPS/infDPS/prest, mas quando o prestador é o emitente (tpEmit = 1) o nome e
  o endereço não vão na DPS; vêm do cadastro e estão em NFSe/infNFSe/emit, que usamos como alternativa
  (é informação do próprio arquivo da NFS-e, §2.1). Com tpEmit 2 ou 3 o emit é outra pessoa e não é usado.
- Totais aproximados (Nota 10): a NT só cita vTotTrib e pTotTrib. A DPS de ME/EPP do Simples traz apenas
  pTotTribSN, e a de MEI, indTotTrib = 0. A linha fixa é mantida com "-" nas três esferas (Nota 12) e, se
  houver pTotTribSN, acrescentamos "; Simples Nacional: X%" para não omitir o valor que está no XML.
- Datas e horas: impressas no fuso informado no próprio XML (a NT só define o formato).
- País em "Local da Prestação" e "Incidência do ISSQN": quando o local é um código IBGE, imprimimos "BR"
  (a tabela do IBGE só tem municípios brasileiros; a NT dá "Ex.: BR"); no exterior, o código ISO do XML.
- tpRetPisCofins: a regra das contribuições sociais e do PIS/COFINS de apuração própria é aplicada como a
  NT escreve, que só trata do código 1. Descrições de códigos vêm do Anexo I v1.01 (inclusive os códigos 0).
- Operação não sujeita ao ISSQN (Nota 4): bloco reduzido quando tribISSQN = 4 (Não Incidência) ou o item
  do cTribNac é 99.
- Destinatário: sem o grupo dest, imprimimos "O DESTINATÁRIO É O PRÓPRIO TOMADOR..." só quando indDest = 0
  está no XML; sem nada, "DESTINATÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e". Aceitamos os caminhos da
  NT 008 (DPS/infDPS/IBSCBS/...) e os da NT 009 (DPS/infDPS/...) para dest, indDest, finNFSe, CST e cClassTrib.
- Caracteres fora do conjunto WinAnsi (que as fontes-padrão do PDF não têm) são trocados pela letra sem
  acento ou por "?"; caracteres de controle viram espaço.
- O canhoto (opcional, Nota 11) é sempre impresso, como no modelo: quadro próprio dentro da borda, rótulos
  em 7 pt. Rótulos seguem a grafia do modelo do Anexo I (ex.: "Contribuição Previdenciária - Retida").
- A URL do QR Code também vai como link clicável (anotação invisível) sobre o próprio QR Code.
"""

from __future__ import annotations

import csv
import functools
import io
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from importlib import resources
from typing import Callable

from lxml import etree
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

__all__ = ["gerar_danfse", "url_consulta_publica", "matriz_qr", "URL_CONSULTA_PUBLICA"]

NS = "http://www.sped.fazenda.gov.br/nfse"
URL_CONSULTA_PUBLICA = "https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave="

TRACO = "-"  # Nota 12: campo sem informação no XML

# --------------------------------------------------------------------------------------------------
# Descrições dos códigos (Anexo I v1.01, aba "LEIAUTE DPS_NFS-e"; tpSusp com o texto pedido pela NT 008)
# --------------------------------------------------------------------------------------------------

TP_AMB = {"1": "Produção", "2": "Homologação"}
AMB_GER = {"1": "Sistema Próprio do Município", "2": "Sefin Nacional NFS-e"}
TP_EMIT = {"1": "Prestador", "2": "Tomador", "3": "Intermediário"}
C_STAT = {
    "100": "NFS-e Gerada",
    "102": "NFS-e de Decisão Judicial ou Administrativa",
    "103": "NFS-e Avulsa",
    "107": "NFS-e MEI",
}
FIN_NFSE = {"0": "NFS-e regular", "1": "NFS-e de crédito", "2": "NFS-e de débito"}  # 1 e 2: NT 009
OP_SIMP_NAC = {
    "1": "Não Optante",
    "2": "Optante - Microempreendedor Individual (MEI)",
    "3": "Optante - Microempresa ou Empresa de Pequeno Porte (ME/EPP)",
}
REG_AP_TRIB_SN = {
    "1": "Regime de apuração dos tributos federais e municipal pelo SN",
    "2": "Regime de apuração dos tributos federais pelo SN e o ISSQN pela NFS-e conforme respectiva "
    "legislação municipal do tributo",
    "3": "Regime de apuração dos tributos federais e municipal pela NFS-e conforme respectivas legislações "
    "federal e municipal de cada tributo",
}
REG_ESP_TRIB = {
    "0": "Nenhum",
    "1": "Ato Cooperado (Cooperativa)",
    "2": "Estimativa",
    "3": "Microempresa Municipal",
    "4": "Notário ou Registrador",
    "5": "Profissional Autônomo",
    "6": "Sociedade de Profissionais",
    "9": "Outros",
}
TRIB_ISSQN = {"1": "Operação Tributável", "2": "Imunidade", "3": "Exportação de Serviço", "4": "Não Incidência"}
TP_IMUNIDADE = {
    "0": "Imunidade (tipo não informado na nota de origem)",
    "1": "Patrimônio, renda ou serviços, uns dos outros (CF88, Art 150, VI, a)",
    "2": "Entidades religiosas e templos de qualquer culto, inclusive suas organizações assistenciais e "
    "beneficentes (CF88, Art 150, VI, b)",
    "3": "Patrimônio, renda ou serviços dos partidos políticos, inclusive suas fundações, das entidades "
    "sindicais dos trabalhadores, das instituições de educação e de assistência social, sem fins "
    "lucrativos, atendidos os requisitos da lei (CF88, Art 150, VI, c)",
    "4": "Livros, jornais, periódicos e o papel destinado a sua impressão (CF88, Art 150, VI, d)",
    "5": "Fonogramas e videofonogramas musicais produzidos no Brasil contendo obras musicais ou "
    "literomusicais de autores brasileiros e/ou obras em geral interpretadas por artistas brasileiros "
    "(CF88, Art 150, VI, e)",
}
TP_SUSP = {"1": "Exigibilidade Suspensa por Decisão Judicial", "2": "Exigibilidade Suspensa por Processo Administrativo"}
TP_RET_ISSQN = {"1": "Não Retido", "2": "Retido pelo Tomador", "3": "Retido pelo Intermediário"}
TP_RET_PIS_COFINS = {
    "0": "PIS/COFINS/CSLL Não Retidos",
    "1": "PIS/COFINS Retido",
    "2": "PIS/COFINS Não Retido",
    "3": "PIS/COFINS/CSLL Retidos",
    "4": "PIS/COFINS Retidos, CSLL Não Retido",
    "5": "PIS Retido, COFINS/CSLL Não Retido",
    "6": "COFINS Retido, PIS/CSLL Não Retido",
    "7": "PIS Não Retido, COFINS/CSLL Retidos",
    "8": "PIS/COFINS Não Retidos, CSLL Retido",
    "9": "COFINS Não Retido, PIS/CSLL Retidos",
}
C_NAO_NIF = {"0": "NIF não informado na nota de origem", "1": "Dispensado do NIF", "2": "Não exigência do NIF"}

UF_POR_PREFIXO_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA",
    "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS",
    "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}  # fmt: skip

TEXTO_QR = (
    "A autenticidade desta NFS-e pode ser verificada pela leitura deste código QR ou pela consulta da "
    "chave de acesso no portal nacional da NFS-e"
)


def url_consulta_publica(chave: str) -> str:
    """Conteúdo do QR Code (§2.4.3): URL da Consulta Pública seguida da chave de acesso."""
    return URL_CONSULTA_PUBLICA + chave


# --------------------------------------------------------------------------------------------------
# Tabela de municípios do IBGE (emissor/dados/municipios_ibge.csv), carregada na primeira consulta
# --------------------------------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _municipios() -> dict[str, tuple[str, str]]:
    texto = resources.files("emissor.dados").joinpath("municipios_ibge.csv").read_text(encoding="utf-8")
    return {lin["codigo"]: (lin["nome"], lin["uf"]) for lin in csv.DictReader(io.StringIO(texto), delimiter=";")}


def _nome_municipio(codigo: str) -> str:
    return _municipios().get(codigo, ("", ""))[0]


def _uf_municipio(codigo: str) -> str:
    if not codigo:
        return ""
    return _municipios().get(codigo, ("", ""))[1] or UF_POR_PREFIXO_IBGE.get(codigo[:2], "")


# --------------------------------------------------------------------------------------------------
# Formatação
# --------------------------------------------------------------------------------------------------


def _limpar(texto: str | None, *, uma_linha: bool = True) -> str:
    """Normaliza o texto do XML para as fontes-padrão do PDF (WinAnsi)."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFC", texto).replace("\r\n", "\n").replace("\r", "\n")
    saida = []
    for ch in texto:
        if ch == "\n":
            saida.append(" " if uma_linha else "\n")
        elif unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") or ch == "\t":
            saida.append(" ")
        else:
            try:
                ch.encode("cp1252")
                saida.append(ch)
            except UnicodeEncodeError:
                base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
                try:
                    base.encode("cp1252")
                    saida.append(base or "?")
                except UnicodeEncodeError:
                    saida.append("?")
    resultado = "".join(saida)
    if uma_linha:
        resultado = re.sub(r"\s+", " ", resultado)
    return resultado.strip()


def _limitar(texto: str, max_chars: int | None) -> str:
    """Corta em `max_chars` caracteres no total, terminando com reticências (tamanhos sugeridos no 2.4.5)."""
    if max_chars and len(texto) > max_chars:
        return texto[: max_chars - 3].rstrip() + "..."
    return texto


def _decimal(valor: str | None) -> Decimal | None:
    if not valor:
        return None
    try:
        return Decimal(valor.strip())
    except InvalidOperation:
        return None


def _numero_br(d: Decimal) -> str:
    return f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _moeda(valor: str | Decimal | None) -> str:
    d = valor if isinstance(valor, Decimal) else _decimal(valor)
    return TRACO if d is None else "R$ " + _numero_br(d)


def _perc(valor: str | None) -> str:
    d = _decimal(valor)
    return TRACO if d is None else _numero_br(d) + "%"


def _soma(*valores: str | None) -> Decimal | None:
    presentes = [d for d in map(_decimal, valores) if d is not None]
    return sum(presentes, Decimal("0")) if presentes else None


def _data(valor: str | None) -> str:
    if not valor:
        return TRACO
    try:
        return date.fromisoformat(valor.strip()[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return valor


def _data_hora(valor: str | None) -> str:
    if not valor:
        return TRACO
    try:
        return datetime.fromisoformat(valor.strip().replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return valor


def _cnpj(v: str) -> str:
    # Por fatiamento: o CNPJ pode ser alfanumérico (IN RFB 2.229/2024).
    return f"{v[:2]}.{v[2:5]}.{v[5:8]}/{v[8:12]}-{v[12:]}" if len(v) == 14 else v


def _cpf(v: str) -> str:
    return f"{v[:3]}.{v[3:6]}.{v[6:9]}-{v[9:]}" if len(v) == 11 else v


def _cep(v: str) -> str:
    return f"{v[:2]}.{v[2:5]}-{v[5:]}" if len(v) == 8 and v.isdigit() else v


def _fone(v: str) -> str:
    if v.isdigit() and len(v) == 11:
        return f"({v[:2]}) {v[2:7]}-{v[7:]}"
    if v.isdigit() and len(v) == 10:
        return f"({v[:2]}) {v[2:6]}-{v[6:]}"
    return v


def _ctrib_nac(v: str) -> str:
    return f"{v[:2]}.{v[2:4]}.{v[4:]}" if len(v) == 6 else v


def _nbs(v: str) -> str:
    return f"{v[0]}.{v[1:5]}.{v[5:7]}.{v[7:]}" if len(v) == 9 else v


def _juntar(*partes: str, sep: str = " / ") -> str:
    """Campo composto: '-' em cada parte ausente, ou '-' sozinho se não houver nenhuma."""
    if not any(partes):
        return TRACO
    return sep.join(p or TRACO for p in partes)


def _municipio_uf(nome: str, uf: str, max_chars: int) -> str:
    """'Município / UF' em até `max_chars`, encurtando só o nome para não perder a sigla da UF."""
    texto = _juntar(nome, uf)
    if len(texto) <= max_chars or not nome:
        return texto
    sufixo = " / " + (uf or TRACO)
    return _limitar(nome, max_chars - len(sufixo)) + sufixo


# --------------------------------------------------------------------------------------------------
# Leitura do XML
# --------------------------------------------------------------------------------------------------


class _Nota:
    """Acesso aos campos da NFS-e por caminhos relativos a infNFSe (ex.: 'DPS/infDPS/tpAmb')."""

    def __init__(self, inf: etree._Element):
        self.inf = inf

    @staticmethod
    @functools.lru_cache(maxsize=512)
    def _xpath(caminho: str) -> str:
        return "/".join(f"n:{p}" for p in caminho.split("/"))

    def el(self, *caminhos: str) -> etree._Element | None:
        for c in caminhos:
            achado = self.inf.find(self._xpath(c), {"n": NS})
            if achado is not None:
                return achado
        return None

    def t(self, *caminhos: str) -> str:
        """Texto do primeiro caminho preenchido, sem espaços nas pontas ('' se nenhum)."""
        for c in caminhos:
            achado = self.inf.find(self._xpath(c), {"n": NS})
            if achado is not None and achado.text and achado.text.strip():
                return achado.text.strip()
        return ""

    def todos(self, caminho: str) -> list[str]:
        return [e.text.strip() for e in self.inf.iterfind(self._xpath(caminho), {"n": NS}) if e.text and e.text.strip()]


def _ler_inf_nfse(nfse_xml: bytes | str) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_comments=True, huge_tree=False)
    if isinstance(nfse_xml, str):
        # lxml não aceita str com declaração de encoding; o texto já está decodificado.
        nfse_xml = re.sub(r"^\s*<\?xml[^>]*\?>", "", nfse_xml.lstrip("\ufeff"))
    raiz = etree.fromstring(nfse_xml, parser)
    nfse = raiz if raiz.tag == f"{{{NS}}}NFSe" else raiz.find(f".//{{{NS}}}NFSe")
    inf = nfse.find(f"{{{NS}}}infNFSe") if nfse is not None else None
    if inf is None:
        raise ValueError("XML não contém NFSe/infNFSe no namespace " + NS)
    return inf


# --------------------------------------------------------------------------------------------------
# Modelo de layout: linhas de campos em colunas (medidas em cm, Y crescendo para baixo)
# --------------------------------------------------------------------------------------------------

PAGINA_L, PAGINA_A = A4  # pt
BORDA = 0.18  # cm da borda do papel (entre 0,15 e 0,20 cm, §2.2.2)
X0, LARGURA = 0.30, 20.40
COL = (0.30, 5.41, 10.51, 15.62)
W1, W2 = 5.09, 10.19
W_ATE_FIM = X0 + LARGURA - COL[1]  # da 2ª coluna até a margem direita
PAD = 0.10  # recuo do texto dentro da célula

Y_TOPO = 0.30
H_CABECALHO = 1.18
H_IDENT = (0.79, 0.69, 0.69, 0.69)  # chave | nº/competência/dhProc | DPS | emitente/situação/finalidade
H_LINHA = 0.645
H_MENSAGEM = 0.40  # mínimo de 0,32 cm (Notas 2, 3 e 4)
H_DESC_TRIB = 0.40
H_VALOR_TOTAL = 0.685
H_TITULO_INFO = 0.41
Y_CANHOTO = 28.10
H_CANHOTO = 0.67

QR_X, QR_Y, QR_LADO = 17.48, 1.67, 1.55  # mínimo 1,52 x 1,52 cm (§2.4.3); zona de silêncio >= 4 módulos
QR_NIVEL = "M"  # correção de erros (a NT não especifica)
QR_TEXTO_X, QR_TEXTO_Y, QR_TEXTO_L = 15.80, 3.36, 4.72  # quadro complemento do QR Code (2.4.5)

FONTE, FONTE_NEGRITO = "Helvetica", "Helvetica-Bold"  # no lugar de Microsoft Sans Serif / Arial (ver docstring)
TAM_CONTEUDO, TAM_ROTULO, TAM_TITULO = 7, 6, 7
ENTRELINHA = 8.0  # pt, para conteúdo de 7 pt

CINZA_FUNDO = (0, 0, 0, 0.05)  # 5% (§2.2.3)
PRETO = (0, 0, 0, 1)  # K100 (§2.4)
VERMELHO = (0, 1, 1, 0)  # M100/Y100 (§2.4.3)
CINZA_MARCA = (0, 0, 0, 0.35)  # K35 (§2.5)


@dataclass
class Campo:
    x: float
    w: float
    rotulo: str
    valor: str
    max_chars: int | None = None
    fundo: bool = False
    rotulo_destaque: bool = False  # 7 pt negrito caixa alta (identificação e valores principais)


@dataclass
class Linha:
    h: float
    campos: list[Campo]
    titulo: str | None = None  # título do bloco, na 1ª coluna, com fundo cinza


@dataclass
class Bloco:
    linhas: list[Linha] = field(default_factory=list)
    mensagem: str | None = None  # bloco reduzido a uma linha (Notas 2, 3 e 4)

    @property
    def altura(self) -> float:
        return H_MENSAGEM if self.mensagem else sum(lin.h for lin in self.linhas)


def _quebrar(texto: str, fonte: str, tamanho: float, largura: float) -> list[str]:
    """Quebra em linhas que cabem em `largura` (pt), respeitando as quebras de linha do texto."""
    linhas: list[str] = []
    for paragrafo in texto.split("\n"):
        atual = ""
        for palavra in paragrafo.split(" "):
            candidato = palavra if not atual else f"{atual} {palavra}"
            if stringWidth(candidato, fonte, tamanho) <= largura:
                atual = candidato
                continue
            if atual:
                linhas.append(atual)
            while stringWidth(palavra, fonte, tamanho) > largura:  # palavra maior que a linha
                k = len(palavra) - 1
                while k > 1 and stringWidth(palavra[:k], fonte, tamanho) > largura:
                    k -= 1
                linhas.append(palavra[:k])
                palavra = palavra[k:]
            atual = palavra
        linhas.append(atual)
    return linhas


def _com_reticencias(texto: str, fonte: str, tamanho: float, largura: float) -> str:
    texto = texto.rstrip()
    while texto and stringWidth(texto + "...", fonte, tamanho) > largura:
        texto = texto[:-1].rstrip()
    return texto + "..."


def _caber(texto: str, fonte: str, tamanho: float, largura: float) -> str:
    """Uma linha: se não couber na largura, corta e termina com reticências."""
    if stringWidth(texto, fonte, tamanho) <= largura:
        return texto
    return _com_reticencias(texto, fonte, tamanho, largura)


def _caber_linhas(texto: str, fonte: str, tamanho: float, largura: float, max_linhas: int) -> list[str]:
    linhas = _quebrar(texto, fonte, tamanho, largura)
    if len(linhas) <= max_linhas:
        return linhas
    if max_linhas <= 0:
        return []
    corte = linhas[:max_linhas]
    corte[-1] = _com_reticencias(corte[-1], fonte, tamanho, largura)
    return corte


# --------------------------------------------------------------------------------------------------
# Página: lista de desenho em duas camadas (fundos cinza, marca d'água, depois linhas e textos)
# --------------------------------------------------------------------------------------------------


class _Pagina:
    def __init__(self, canvas: Canvas):
        self.c = canvas
        self._fundos: list[tuple[float, float, float, float]] = []
        self._frente: list[Callable[[], None]] = []

    @staticmethod
    def y(topo_cm: float, deslocamento_pt: float = 0.0) -> float:
        return PAGINA_A - topo_cm * cm - deslocamento_pt

    def fundo(self, x: float, topo: float, w: float, h: float) -> None:
        self._fundos.append((x, topo, w, h))

    def texto(self, x: float, topo: float, desloc_pt: float, texto: str, fonte: str, tamanho: float,
              cor=PRETO, alinhamento: str = "esquerda") -> None:  # fmt: skip
        def desenhar():
            self.c.setFillColorCMYK(*cor)
            self.c.setFont(fonte, tamanho)
            yy = self.y(topo, desloc_pt)
            if alinhamento == "centro":
                self.c.drawCentredString(x * cm, yy, texto)
            elif alinhamento == "direita":
                self.c.drawRightString(x * cm, yy, texto)
            else:
                self.c.drawString(x * cm, yy, texto)

        self._frente.append(desenhar)

    def linha_h(self, topo: float, x_ini: float = BORDA, x_fim: float = 21.0 - BORDA) -> None:
        def desenhar():
            self.c.setStrokeColorCMYK(*PRETO)
            self.c.setLineWidth(0.5)  # §2.2.3
            self.c.line(x_ini * cm, self.y(topo), x_fim * cm, self.y(topo))

        self._frente.append(desenhar)

    def linha_v(self, x: float, topo: float, h: float) -> None:
        def desenhar():
            self.c.setStrokeColorCMYK(*PRETO)
            self.c.setLineWidth(0.5)
            self.c.line(x * cm, self.y(topo), x * cm, self.y(topo + h))

        self._frente.append(desenhar)

    def depois(self, funcao: Callable[[], None]) -> None:
        self._frente.append(funcao)

    def renderizar(self, marca_dagua: str | None) -> None:
        c = self.c
        c.setFillColorCMYK(*CINZA_FUNDO)
        for x, topo, w, h in self._fundos:
            c.rect(x * cm, self.y(topo + h), w * cm, h * cm, stroke=0, fill=1)
        if marca_dagua:
            _desenhar_marca_dagua(c, marca_dagua)
        for desenhar in self._frente:
            desenhar()
        c.setStrokeColorCMYK(*PRETO)
        c.setLineWidth(1)  # borda da página (§2.2.3)
        c.rect(BORDA * cm, BORDA * cm, PAGINA_L - 2 * BORDA * cm, PAGINA_A - 2 * BORDA * cm, stroke=1, fill=0)

    # ---- células ---------------------------------------------------------------------------------

    def campo(self, cp: Campo, topo: float, h: float) -> None:
        w = min(cp.w, X0 + LARGURA - cp.x)  # 4ª coluna: 15,62 + 5,09 passaria 0,01 cm da área útil (20,70 cm)
        if cp.fundo:
            self.fundo(cp.x, topo, w, h)
        largura = (w - 2 * PAD) * cm
        if cp.rotulo_destaque:
            fonte_r, tam_r, desloc_r, desloc_v = FONTE_NEGRITO, TAM_TITULO, 7.4, 15.6
        else:
            fonte_r, tam_r, desloc_r, desloc_v = FONTE_NEGRITO, TAM_ROTULO, 6.6, 14.6
        if cp.rotulo:
            self.texto(cp.x + PAD, topo, desloc_r, _caber(cp.rotulo, fonte_r, tam_r, largura), fonte_r, tam_r)
        valor = _limitar(cp.valor or TRACO, cp.max_chars)
        self.texto(cp.x + PAD, topo, desloc_v, _caber(valor, FONTE, TAM_CONTEUDO, largura), FONTE, TAM_CONTEUDO)

    def bloco(self, bloco: Bloco, topo: float) -> float:
        self.linha_h(topo)
        if bloco.mensagem:
            self.texto(X0 + LARGURA / 2, topo, H_MENSAGEM * cm / 2 + 2.5, bloco.mensagem, FONTE, TAM_CONTEUDO,
                       alinhamento="centro")  # fmt: skip
            return topo + H_MENSAGEM
        for lin in bloco.linhas:
            if lin.titulo:
                self.fundo(COL[0], topo, W1, lin.h)
                self.texto(COL[0] + PAD, topo, lin.h * cm / 2 + 2.5, lin.titulo, FONTE_NEGRITO, TAM_TITULO)
            for cp in lin.campos:
                self.campo(cp, topo, lin.h)
            topo += lin.h
        return topo


def _desenhar_marca_dagua(c: Canvas, texto: str) -> None:
    """Marca d'água diagonal (§2.5.1/2.5.2): formato normal, >= 50 pt, cinza K35."""
    angulo = math.degrees(math.atan2(PAGINA_A, PAGINA_L))
    diagonal = math.hypot(PAGINA_L, PAGINA_A)
    tamanho = min(110.0, 0.7 * diagonal / (stringWidth(texto, FONTE, 1.0)))
    c.saveState()
    c.setFillColorCMYK(*CINZA_MARCA)
    c.translate(PAGINA_L / 2, PAGINA_A / 2)
    c.rotate(angulo)
    c.setFont(FONTE, tamanho)
    c.drawCentredString(0, -0.35 * tamanho, texto)
    c.restoreState()


# --------------------------------------------------------------------------------------------------
# Montagem dos blocos a partir da NFS-e
# --------------------------------------------------------------------------------------------------


@dataclass
class _Pessoa:
    documento: str = TRACO
    im: str = TRACO
    fone: str = TRACO
    nome: str = TRACO
    municipio_uf: str = TRACO
    ibge_cep: str = TRACO
    endereco: str = TRACO
    email: str = TRACO


def _documento(nota: _Nota, base: str) -> str:
    if v := nota.t(base + "/CNPJ"):
        return _cnpj(v)
    if v := nota.t(base + "/CPF"):
        return _cpf(v)
    if v := nota.t(base + "/NIF"):
        return _limpar(v)
    if v := nota.t(base + "/cNaoNIF"):
        return C_NAO_NIF.get(v, v)
    return TRACO


def _pessoa(nota: _Nota, base: str, *, emit_alternativo: bool = False) -> _Pessoa:
    """Dados de prest/toma/interm/dest. Com `emit_alternativo`, campos ausentes vêm de infNFSe/emit."""
    p = _Pessoa(documento=_documento(nota, base))
    emit = "emit" if emit_alternativo else None

    def campo(nome: str) -> str:
        return _limpar(nota.t(f"{base}/{nome}", *([f"{emit}/{nome}"] if emit else [])))

    p.im = campo("IM") or TRACO
    p.fone = _fone(campo("fone")) or TRACO
    p.nome = campo("xNome") or TRACO
    p.email = campo("email") or TRACO

    end = f"{base}/end"
    if nota.el(end) is not None:
        logradouro = [_limpar(nota.t(f"{end}/{t}")) for t in ("xLgr", "nro", "xCpl", "xBairro")]
        if c_mun := nota.t(f"{end}/endNac/cMun"):
            p.municipio_uf = _juntar(_nome_municipio(c_mun), _uf_municipio(c_mun))
            p.ibge_cep = _juntar(c_mun, _cep(nota.t(f"{end}/endNac/CEP")))
        elif nota.el(f"{end}/endExt") is not None:
            p.municipio_uf = _juntar(_limpar(nota.t(f"{end}/endExt/xCidade")), _limpar(nota.t(f"{end}/endExt/xEstProvReg")))
            p.ibge_cep = _juntar("", _limpar(nota.t(f"{end}/endExt/cEndPost")))
    elif emit and nota.el("emit/enderNac") is not None:
        logradouro = [_limpar(nota.t(f"emit/enderNac/{t}")) for t in ("xLgr", "nro", "xCpl", "xBairro")]
        c_mun = nota.t("emit/enderNac/cMun")
        p.municipio_uf = _juntar(_nome_municipio(c_mun), nota.t("emit/enderNac/UF") or _uf_municipio(c_mun))
        p.ibge_cep = _juntar(c_mun, _cep(nota.t("emit/enderNac/CEP")))
    else:
        logradouro = []
    p.endereco = ", ".join(x for x in logradouro if x) or TRACO
    return p


def _linhas_pessoa(titulo: str, p: _Pessoa, *, com_im: bool = True) -> list[Linha]:
    return [
        Linha(H_LINHA, titulo=titulo, campos=[
            Campo(COL[1], W1, "CNPJ / CPF / NIF", p.documento, 40),
            *([Campo(COL[2], W1, "Indicador Municipal (Inscrição)", p.im, 15)] if com_im else []),
            Campo(COL[3], W1, "Telefone", p.fone, 20),
        ]),
        Linha(H_LINHA, campos=[
            Campo(COL[0], W2, "Nome / Nome Empresarial", p.nome, 80),
            Campo(COL[2], W1, "Município / Sigla UF", p.municipio_uf, 37),
            Campo(COL[3], W1, "Código IBGE / CEP", p.ibge_cep, 21),
        ]),
        Linha(H_LINHA, campos=[  # Nota 1: suprimível; mantida, como no modelo
            Campo(COL[0], W2, "Endereço", p.endereco, 80),
            Campo(COL[2], W2, "E-mail", p.email, 80),
        ]),
    ]  # fmt: skip


def _local_pais(nome: str, cod_ibge: str, pais_iso: str) -> str:
    uf = _uf_municipio(cod_ibge) if cod_ibge else ""
    pais = pais_iso or ("BR" if cod_ibge else "")
    return _juntar(_limpar(nome), uf, pais)


def _bloco_prestador(nota: _Nota) -> Bloco:
    # Prestador emitente (tpEmit = 1): nome/endereço/contatos do cadastro estão em infNFSe/emit.
    p = _pessoa(nota, "DPS/infDPS/prest", emit_alternativo=nota.t("DPS/infDPS/tpEmit") == "1")
    reg = "DPS/infDPS/prest/regTrib/"
    op = nota.t(reg + "opSimpNac")
    ap = nota.t(reg + "regApTribSN")
    linhas = _linhas_pessoa("PRESTADOR / FORNECEDOR", p)
    linhas.append(Linha(H_LINHA, campos=[
        Campo(COL[0], W1, "Simples Nacional na Data de Competência", OP_SIMP_NAC.get(op, op), 40),
        Campo(COL[1], W_ATE_FIM, "Regime de Apuração Tributária pelo SN", REG_AP_TRIB_SN.get(ap, ap), 80),
    ]))  # fmt: skip
    return Bloco(linhas)


def _bloco_tomador(nota: _Nota) -> Bloco:
    if nota.el("DPS/infDPS/toma") is None:
        return Bloco(mensagem="TOMADOR/ADQUIRENTE DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")
    return Bloco(_linhas_pessoa("TOMADOR / ADQUIRENTE", _pessoa(nota, "DPS/infDPS/toma")))


def _bloco_destinatario(nota: _Nota) -> Bloco:
    for base in ("DPS/infDPS/dest", "DPS/infDPS/IBSCBS/dest"):  # NT 009 §2.11 / NT 008
        if nota.el(base) is not None:
            return Bloco(_linhas_pessoa("DESTINATÁRIO DA OPERAÇÃO", _pessoa(nota, base), com_im=False))
    if nota.t("DPS/infDPS/indDest", "DPS/infDPS/IBSCBS/indDest") == "0":
        return Bloco(mensagem="O DESTINATÁRIO É O PRÓPRIO TOMADOR/ADQUIRENTE DA OPERAÇÃO")
    return Bloco(mensagem="DESTINATÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")


def _bloco_intermediario(nota: _Nota) -> Bloco:
    if nota.el("DPS/infDPS/interm") is None:
        return Bloco(mensagem="INTERMEDIÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")
    return Bloco(_linhas_pessoa("INTERMEDIÁRIO DA OPERAÇÃO", _pessoa(nota, "DPS/infDPS/interm")))


def _bloco_servico(nota: _Nota) -> Bloco:
    cserv = "DPS/infDPS/serv/cServ/"
    c_nac, c_mun = nota.t(cserv + "cTribNac"), nota.t(cserv + "cTribMun")
    c_nbs = nota.t(cserv + "cNBS")
    local = _local_pais(
        nota.t("xLocPrestacao"),
        nota.t("DPS/infDPS/serv/locPrest/cLocPrestacao"),
        nota.t("DPS/infDPS/serv/locPrest/cPaisPrestacao"),
    )
    return Bloco([Linha(H_LINHA, titulo="SERVIÇO PRESTADO", campos=[
        Campo(COL[1], W1, "Código de Tributação Nacional / Municipal", _juntar(_ctrib_nac(c_nac), c_mun), 14),
        Campo(COL[2], W1, "Código da NBS", _nbs(c_nbs) or TRACO, 12),
        Campo(COL[3], W1, "Local da Prestação / Sigla UF / País", local, 42),
    ])])  # fmt: skip


def _bloco_issqn(nota: _Nota) -> Bloco:
    trib = "DPS/infDPS/valores/trib/tribMun/"
    trib_issqn = nota.t(trib + "tribISSQN")
    if trib_issqn == "4" or nota.t("DPS/infDPS/serv/cServ/cTribNac").startswith("99"):
        return Bloco(mensagem="TRIBUTAÇÃO MUNICIPAL (ISSQN) - OPERAÇÃO NÃO SUJEITA AO ISSQN")  # Nota 4

    incid = _local_pais(nota.t("xLocIncid"), nota.t("cLocIncid"), nota.t(trib + "cPaisResult"))
    reg_esp = nota.t("DPS/infDPS/prest/regTrib/regEspTrib")
    imun = nota.t(trib + "tpImunidade")
    susp = nota.t(trib + "exigSusp/tpSusp")
    tp_bm = nota.t("valores/tpBM")
    calc_bm = nota.t("valores/vCalcBM", trib + "BM/vRedBCBM")
    ded_red = _soma(nota.t("DPS/infDPS/valores/vDedRed/vDR", "valores/vCalcDR"), nota.t("IBSCBS/valores/vCalcReeRepRes"))
    desc_incond = nota.t("DPS/infDPS/valores/vDescCondIncond/vDescIncond")

    linhas = [Linha(H_LINHA, titulo="TRIBUTAÇÃO MUNICIPAL (ISSQN)", campos=[
        Campo(COL[1], W1, "Tipo de Tributação do ISSQN", TRIB_ISSQN.get(trib_issqn, trib_issqn), 21),
        Campo(COL[2], W2, "Município / Sigla UF / País de Incidência do ISSQN", incid, 42),
    ])]  # fmt: skip
    # Linhas ** (Nota 5): suprimidas quando todos os campos estão vazios no XML.
    if any((reg_esp, imun, susp, nota.t(trib + "exigSusp/nProcesso"))):
        linhas.append(Linha(H_LINHA, campos=[
            Campo(COL[0], W1, "Regime Especial de Tributação do ISSQN", REG_ESP_TRIB.get(reg_esp, reg_esp), 27),
            Campo(COL[1], W1, "Tipo de Imunidade do ISSQN", TP_IMUNIDADE.get(imun, imun), 40),
            Campo(COL[2], W1, "Suspensão da Exigibilidade do ISSQN", TP_SUSP.get(susp, susp), 40),
            Campo(COL[3], W1, "Número Processo Suspensão", nota.t(trib + "exigSusp/nProcesso"), 30),
        ]))  # fmt: skip
    if any((tp_bm, calc_bm, ded_red is not None, desc_incond)):
        linhas.append(Linha(H_LINHA, campos=[
            Campo(COL[0], W1, "Benefício Municipal", _descricao_bm(nota, tp_bm), 40),
            Campo(COL[1], W1, "Cálculo do BM", _moeda(calc_bm)),
            Campo(COL[2], W1, "Total Deduções/Reduções", _moeda(ded_red)),
            Campo(COL[3], W1, "Desconto Incondicionado", _moeda(desc_incond)),
        ]))  # fmt: skip
    ret = nota.t(trib + "tpRetISSQN")
    linhas.append(Linha(H_LINHA, campos=[
        Campo(COL[0], W1, "BC ISSQN", _moeda(nota.t("valores/vBC"))),
        Campo(COL[1], W1, "Alíquota Aplicada", _perc(nota.t("valores/pAliqAplic"))),
        Campo(COL[2], W1, "Retenção do ISSQN", TP_RET_ISSQN.get(ret, ret), 25),
        Campo(COL[3], W1, "ISSQN Apurado", _moeda(nota.t("valores/vISSQN"))),
    ]))  # fmt: skip
    return Bloco(linhas)


def _descricao_bm(nota: _Nota, tp_bm: str) -> str:
    # Anexo I: 2) "Redução da BC em 'ppBM' %"; 3) "Redução da BC em R$ 'vInfoBM'"; 4) "Alíquota Diferenciada
    # de 'aliqDifBM' %". Os valores entre aspas são preenchidos só quando estão no XML.
    bm = "DPS/infDPS/valores/trib/tribMun/BM/"
    if tp_bm == "1":
        return "Isenção"
    if tp_bm == "2":
        p = nota.t(bm + "pRedBCBM")
        return f"Redução da BC em {_perc(p)}" if p else "Redução da BC"
    if tp_bm == "3":
        v = nota.t(bm + "vRedBCBM")
        return f"Redução da BC em {_moeda(v)}" if v else "Redução da BC"
    if tp_bm == "4":
        a = nota.t("valores/pAliqAplic")
        return f"Alíquota Diferenciada de {_perc(a)}" if a else "Alíquota Diferenciada"
    return tp_bm


def _bloco_federal(nota: _Nota) -> Bloco:
    fed = "DPS/infDPS/valores/trib/tribFed/"
    tp_ret = nota.t(fed + "piscofins/tpRetPisCofins")
    v_pis, v_cofins, v_csll = nota.t(fed + "piscofins/vPis"), nota.t(fed + "piscofins/vCofins"), nota.t(fed + "vRetCSLL")
    retido = tp_ret == "1"  # NT 008 v1.02 só define a regra para o código 1
    contrib = _soma(v_csll, v_pis, v_cofins) if retido else _decimal(v_csll)
    linhas = [Linha(H_LINHA, titulo="TRIBUTAÇÃO FEDERAL (EXCETO CBS)", campos=[
        Campo(COL[1], W1, "IRRF", _moeda(nota.t(fed + "vRetIRRF"))),
        Campo(COL[2], W1, "Contribuição Previdenciária - Retida", _moeda(nota.t(fed + "vRetCP"))),  # hífen, como no Anexo I
        Campo(COL[3], W1, "Contribuições Sociais – Retidas", _moeda(contrib)),
    ])]  # fmt: skip
    # Linha *** (Nota 6): só para competência até o fim de 2026.
    try:
        ate_2026 = date.fromisoformat(nota.t("DPS/infDPS/dCompet")) <= date(2026, 12, 31)
    except ValueError:
        ate_2026 = True
    if ate_2026:
        linhas.append(Linha(H_LINHA, campos=[
            Campo(COL[0], W1, "PIS - Débito Apuração Própria", _moeda("0") if retido else _moeda(v_pis)),
            Campo(COL[1], W1, "COFINS - Débito Apuração Própria", _moeda("0") if retido else _moeda(v_cofins)),
            Campo(COL[2], W2, "Descrição Contrib. Sociais – Retidas", TP_RET_PIS_COFINS.get(tp_ret, tp_ret), 35),
        ]))  # fmt: skip
    return Bloco(linhas)


def _bloco_ibscbs(nota: _Nota) -> Bloco:
    dps, gera = "DPS/infDPS/IBSCBS/", "IBSCBS/"
    cst = nota.t(dps + "valores/trib/gIBSCBS/CST", dps + "valores/trib/CST")  # NT 008 / NT 009 §2.16
    ccl = nota.t(dps + "valores/trib/gIBSCBS/cClassTrib", dps + "valores/trib/cClassTrib")
    c_loc = nota.t(gera + "cLocalidadeIncid")
    ind_op = _juntar(nota.t(dps + "cIndOp"), c_loc, _limpar(nota.t(gera + "xLocalidadeIncid")),
                     _uf_municipio(c_loc) if c_loc else "")  # fmt: skip
    # Somatórios só quando a NFS-e traz o grupo IBSCBS calculado (senão seriam valores do ISSQN, sem IBS/CBS).
    tem_ibscbs = nota.el("IBSCBS") is not None
    exclusoes = (
        _soma(
            nota.t("DPS/infDPS/valores/vDescCondIncond/vDescIncond"),
            nota.t(gera + "valores/vCalcReeRepRes"),
            nota.t("valores/vISSQN"),
            nota.t("DPS/infDPS/valores/trib/tribFed/piscofins/vPis"),
            nota.t("DPS/infDPS/valores/trib/tribFed/piscofins/vCofins"),
        )
        if tem_ibscbs
        else None
    )
    v = gera + "valores/"
    red = [nota.t(v + "uf/pRedAliqUF"), nota.t(v + "mun/pRedAliqMun"), nota.t(v + "fed/pRedAliqCBS")]
    aliq = [nota.t(v + "uf/pIBSUF"), nota.t(v + "mun/pIBSMun")]
    tot = gera + "totCIBS/"

    def percs(vals: list[str]) -> str:
        return _juntar(*(_perc(x) if x else "" for x in vals))

    return Bloco([
        Linha(H_LINHA, titulo="TRIBUTAÇÃO IBS / CBS", campos=[
            Campo(COL[1], W1, "CST / cClassTrib", _juntar(cst, ccl), 12),
            Campo(COL[2], W2, "Indicador de Operação / Código IBGE Incidência / Município Incidência / Sigla UF",
                  ind_op, 56),
        ]),
        Linha(H_LINHA, campos=[
            Campo(COL[0], W1, "Exclusões e Reduções da Base de Cálculo", _moeda(exclusoes)),
            Campo(COL[1], W1, "Base de Cálculo Após Exclusões e Reduções", _moeda(nota.t(v + "vBC"))),
            Campo(COL[2], W1, "Red. Alíquota IBS / Red. Alíquota CBS", percs(red)),
            Campo(COL[3], W1, "Alíquota – IBS UF / IBS Mun", percs(aliq)),
        ]),
        Linha(H_LINHA, campos=[
            Campo(COL[0], W1, "Alíq. Efetiva Municipal – IBS", _perc(nota.t(v + "mun/pAliqEfetMun"))),
            Campo(COL[1], W1, "Valor Apurado Municipal – IBS", _moeda(nota.t(tot + "gIBS/gIBSMunTot/vIBSMun"))),
            Campo(COL[2], W1, "Alíq. Efetiva Estadual – IBS", _perc(nota.t(v + "uf/pAliqEfetUF"))),
            Campo(COL[3], W1, "Valor Apurado Estadual – IBS", _moeda(nota.t(tot + "gIBS/gIBSUFTot/vIBSUF"))),
        ]),
        Linha(H_LINHA, campos=[
            Campo(COL[0], W1, "Valor Total Apurado – IBS", _moeda(nota.t(tot + "gIBS/vIBSTot"))),
            Campo(COL[1], W1, "Alíquota - CBS", _perc(nota.t(v + "fed/pCBS"))),  # hífen, como no Anexo I
            Campo(COL[2], W1, "Alíquota Efetiva – CBS", _perc(nota.t(v + "fed/pAliqEfetCBS"))),
            Campo(COL[3], W1, "Valor Total Apurado – CBS", _moeda(nota.t(tot + "gCBS/vCBS"))),
        ]),
    ])  # fmt: skip


def _bloco_valor_total(nota: _Nota) -> Bloco:
    desc = "DPS/infDPS/valores/vDescCondIncond/"
    tot = "IBSCBS/totCIBS/"
    return Bloco([
        Linha(H_VALOR_TOTAL, titulo="VALOR TOTAL DA NFS-E", campos=[
            Campo(COL[1], W1, "VALOR DA OPERAÇÃO / SERVIÇO", _moeda(nota.t("DPS/infDPS/valores/vServPrest/vServ")),
                  rotulo_destaque=True),
            Campo(COL[2], W1, "Desconto Incondicionado", _moeda(nota.t(desc + "vDescIncond"))),
            Campo(COL[3], W1, "Desconto Condicionado", _moeda(nota.t(desc + "vDescCond"))),
        ]),
        Linha(H_VALOR_TOTAL, campos=[
            Campo(COL[0], W1, "Total das Retenções (ISSQN / Federais)", _moeda(nota.t("valores/vTotalRet"))),
            Campo(COL[1], W1, "VALOR LÍQUIDO DA NFS-e", _moeda(nota.t("valores/vLiq")), rotulo_destaque=True),
            Campo(COL[2], W1, "Total do IBS/CBS", _moeda(_soma(nota.t(tot + "gIBS/vIBSTot"), nota.t(tot + "gCBS/vCBS")))),
            Campo(COL[3], W1, "VALOR LÍQUIDO DA NFS-e + IBS/CBS", _moeda(nota.t(tot + "vTotNF")), fundo=True,
                  rotulo_destaque=True),
        ]),
    ])  # fmt: skip


MAX_INFO = 2000  # "Utilizar reticências (...), caso a descrição supere 1997 caracteres"


def _itens_info(nota: _Nota) -> list[tuple[str, str, bool]]:
    """Itens de Informações Complementares na ordem do 2.4.5: (rótulo, valor, texto livre?)."""
    serv = "DPS/infDPS/serv/"
    itens = [
        ("Inf. Cont.:", nota.t(serv + "infoCompl/xInfComp"), True),
        ("NFS-e Subst.:", nota.t("DPS/infDPS/subst/chSubstda"), False),  # Nota 7
        ("Doc. Ref.:", nota.t(serv + "infoCompl/docRef"), True),
        ("Cod. Obra:", nota.t(serv + "obra/cObra"), False),  # Nota 8
        ("Insc. Imob.:", nota.t(serv + "obra/inscImobFisc", "DPS/infDPS/IBSCBS/imovel/inscImobFisc"), False),
        ("Cod. Evt.:", nota.t(serv + "atvEvento/idAtvEvt"), False),  # Nota 9
        ("Doc. Tec.:", nota.t(serv + "infoCompl/idDocTec"), False),
        ("Núm. Ped.:", nota.t(serv + "infoCompl/xPed"), False),
        ("Item Ped.:", ", ".join(nota.todos(serv + "infoCompl/gItemPed/xItemPed")), True),
        ("Inf. A. T. Mun.:", nota.t("xOutInf"), True),
    ]
    return [(rot, _limpar(valor, uma_linha=False), livre) for rot, valor, livre in itens if valor]


def _compor_info(itens: list[tuple[str, str, bool]], cabe: Callable[[str], bool] | None = None) -> str:
    """Une os itens com ' | ' em até MAX_INFO caracteres e, se dado, no espaço aceito por `cabe`.

    Quando não cabe, encurta (com reticências) só os textos livres (Inf. Cont., Doc. Ref., Item Ped.,
    Inf. A. T. Mun.), para não perder os itens que as Notas 7 a 9 mandam constar; se nem assim couber,
    corta o texto inteiro, como no 2.4.5.
    """

    def compor(limite: int | None) -> str:
        partes = []
        for rotulo, valor, livre in itens:
            if livre and limite is not None and len(valor) > limite:
                valor = valor[: max(limite - 3, 0)].rstrip() + "..."
            partes.append(f"{rotulo} {valor}")
        return " | ".join(partes)

    def serve(texto: str) -> bool:
        return len(texto) <= MAX_INFO and (cabe is None or cabe(texto))

    texto = compor(None)
    if serve(texto):
        return texto
    livres = [len(valor) for _, valor, livre in itens if livre]
    melhor, ini, fim = None, 3, max(livres, default=0)
    while ini <= fim:  # maior limite por texto livre que ainda cabe
        meio = (ini + fim) // 2
        candidato = compor(meio)
        if serve(candidato):
            melhor, ini = candidato, meio + 1
        else:
            fim = meio - 1
    return melhor if melhor is not None else _limitar(compor(3 if livres else None), MAX_INFO)


def _totais_aproximados(nota: _Nota) -> str:
    """Linha fixa e obrigatória da Lei 12.741/2012 (Nota 10)."""
    tot = "DPS/infDPS/valores/trib/totTrib/"
    if nota.el(tot + "vTotTrib") is not None:
        esferas = [_moeda(nota.t(tot + f"vTotTrib/vTotTrib{e}")) for e in ("Fed", "Est", "Mun")]
    elif nota.el(tot + "pTotTrib") is not None:
        esferas = [_perc(nota.t(tot + f"pTotTrib/pTotTrib{e}")) for e in ("Fed", "Est", "Mun")]
    else:  # indTotTrib = 0 (MEI) ou pTotTribSN (ME/EPP): sem valores por esfera no XML
        esferas = [TRACO] * 3
    totais = (
        "Totais Aproximados dos Tributos cfe. Lei nº 12.741/2012: "
        f"Federais: {esferas[0]} ; Estaduais: {esferas[1]} ; Municipais: {esferas[2]}"
    )
    if sn := nota.t(tot + "pTotTribSN"):
        # A NT 008 não trata do pTotTribSN; ele é impresso como está no XML, sem rateio por esfera.
        totais += f" ; Simples Nacional: {_perc(sn)}"
    return totais


# --------------------------------------------------------------------------------------------------
# Desenho
# --------------------------------------------------------------------------------------------------


def _desenhar_logomarca(pag: _Pagina) -> None:
    # Substituto da logomarca oficial (PNG indisponível offline): "NFS-e" estilizado em 0,85 x 4,00 cm.
    def desenhar():
        c = pag.c
        x, base = 0.49 * cm, pag.y(0.44 + 0.85) + 0.17 * cm
        c.setFillColorCMYK(*PRETO)
        c.setFont(FONTE_NEGRITO, 22)
        c.drawString(x, base, "NFS")
        x += stringWidth("NFS", FONTE_NEGRITO, 22)
        c.setFont(FONTE_NEGRITO, 15)
        c.drawString(x + 0.5, base, "-e")
        x += stringWidth("-e", FONTE_NEGRITO, 15) + 3
        c.setFont(FONTE, 6.5)
        c.drawString(x, base + 9, "Nota Fiscal de")
        c.drawString(x, base + 1.5, "Serviço Eletrônica")

    pag.depois(desenhar)


def _desenhar_cabecalho(pag: _Pagina, nota: _Nota) -> None:
    pag.fundo(X0, Y_TOPO, LARGURA, H_CABECALHO)
    _desenhar_logomarca(pag)
    centro = COL[1] + W2 / 2
    pag.texto(centro, Y_TOPO, 10, "DANFSe v2.0", FONTE_NEGRITO, 9, alinhamento="centro")
    pag.texto(centro, Y_TOPO, 20, "Documento Auxiliar da NFS-e", FONTE_NEGRITO, 9, alinhamento="centro")
    if nota.t("DPS/infDPS/tpAmb") == "2":  # produção restrita (§2 e §2.4.3)
        pag.texto(centro, Y_TOPO, 30, "NFS-e SEM VALIDADE JURÍDICA", FONTE_NEGRITO, 9, VERMELHO, "centro")

    x, largura = COL[3] + PAD, (W1 - PAD) * cm
    if not nota.t("DPS/infDPS/serv/cServ/cTribNac").startswith("99"):  # não exibir no item 99
        municipio = _municipio_uf(_limpar(nota.t("xLocEmi")), nota.t("emit/enderNac/UF"), 37)
        for i, lin in enumerate(_caber_linhas("Município: " + municipio, FONTE, 8, largura, 2)):
            pag.texto(x, Y_TOPO, 8.2 + i * 8.6, lin, FONTE, 8)
    amb_ger, tp_amb = nota.t("ambGer"), nota.t("DPS/infDPS/tpAmb")
    pag.texto(x, 0.97, 5.6, _caber("Ambiente Gerador: " + (AMB_GER.get(amb_ger, amb_ger) or TRACO), FONTE, 6, largura),
              FONTE, 6)  # fmt: skip
    pag.texto(x, 1.22, 5.6, "Tipo de Ambiente: " + (TP_AMB.get(tp_amb, tp_amb) or TRACO), FONTE, 6)


def matriz_qr(conteudo: str) -> list[list[bool]]:
    """Módulos do QR Code (True = escuro), nível de correção M e menor versão que comporta o conteúdo."""
    widget = QrCodeWidget(conteudo, barLevel=QR_NIVEL)
    widget.qr.make()
    return [[bool(m) for m in linha] for linha in widget.qr.modules]


def _desenhar_qr(c: Canvas, url: str) -> None:
    # Desenhado módulo a módulo no próprio canvas (sem renderPDF, que acrescentaria a fonte Times-Roman).
    matriz = matriz_qr(url)
    lado = QR_LADO * cm
    modulo = lado / len(matriz)
    x0, topo = QR_X * cm, _Pagina.y(QR_Y)
    c.setFillColorCMYK(*PRETO)
    for i, linha in enumerate(matriz):
        j = 0
        while j < len(linha):
            if not linha[j]:
                j += 1
                continue
            k = j
            while k < len(linha) and linha[k]:
                k += 1
            c.rect(x0 + j * modulo, topo - (i + 1) * modulo, (k - j) * modulo, modulo, stroke=0, fill=1)
            j = k
    c.linkURL(url, (x0, topo - lado, x0 + lado, topo), relative=0, thickness=0)  # link clicável no PDF


def _desenhar_identificacao(pag: _Pagina, nota: _Nota, chave: str, topo: float) -> float:
    pag.linha_h(topo)
    dps = "DPS/infDPS/"
    tp_emit, c_stat, fin = nota.t(dps + "tpEmit"), nota.t("cStat"), nota.t(dps + "finNFSe", dps + "IBSCBS/finNFSe")
    linhas = [
        Linha(H_IDENT[0], [Campo(COL[0], 15.30, "CHAVE DE ACESSO DA NFS-E", chave, rotulo_destaque=True)]),
        Linha(H_IDENT[1], [
            Campo(COL[0], W1, "NÚMERO DA NFS-E", nota.t("nNFSe"), 13, rotulo_destaque=True),
            Campo(COL[1], W1, "COMPETÊNCIA DA NFS-E", _data(nota.t(dps + "dCompet")), 10, rotulo_destaque=True),
            Campo(COL[2], W1, "DATA E HORA DA EMISSÃO DA NFS-E", _data_hora(nota.t("dhProc")), 19,
                  rotulo_destaque=True),
        ]),
        Linha(H_IDENT[2], [
            Campo(COL[0], W1, "NÚMERO DA DPS", nota.t(dps + "nDPS"), 15, rotulo_destaque=True),
            Campo(COL[1], W1, "SÉRIE DA DPS", nota.t(dps + "serie"), 5, rotulo_destaque=True),
            Campo(COL[2], W1, "DATA E HORA DA EMISSÃO DA DPS", _data_hora(nota.t(dps + "dhEmi")), 19,
                  rotulo_destaque=True),
        ]),
        Linha(H_IDENT[3], [
            Campo(COL[0], W1, "EMITENTE DA NFS-E", TP_EMIT.get(tp_emit, tp_emit), 13, fundo=True, rotulo_destaque=True),
            Campo(COL[1], W1, "SITUAÇÃO DA NFS-E", C_STAT.get(c_stat, c_stat), 40, rotulo_destaque=True),
            Campo(COL[2], W1, "FINALIDADE", FIN_NFSE.get(fin, fin), 40, rotulo_destaque=True),
        ]),
    ]  # fmt: skip
    for lin in linhas:
        for cp in lin.campos:
            pag.campo(cp, topo, lin.h)
        topo += lin.h

    if chave:
        pag.depois(lambda: _desenhar_qr(pag.c, url_consulta_publica(chave)))
    for i, lin in enumerate(_caber_linhas(TEXTO_QR, FONTE, 6, QR_TEXTO_L * cm, 3)):
        pag.texto(QR_TEXTO_X, QR_TEXTO_Y, 6 + i * 6.8, lin, FONTE, 6)
    return topo


def _desenhar_descricao(pag: _Pagina, topo: float, altura: float, texto: str) -> None:
    pag.texto(X0 + PAD, topo, 6.6, "Descrição do Serviço", FONTE_NEGRITO, TAM_ROTULO)
    max_linhas = int((altura * cm - _DESC_TOPO) // ENTRELINHA)
    for i, lin in enumerate(_caber_linhas(texto, FONTE, TAM_CONTEUDO, (LARGURA - 2 * PAD) * cm, max_linhas)):
        pag.texto(X0 + PAD, topo, _DESC_TOPO + 6.0 + i * ENTRELINHA, lin, FONTE, TAM_CONTEUDO)


def _linhas_info(itens: list[tuple[str, str, bool]], totais: str, max_linhas: int) -> list[str]:
    largura = (LARGURA - 2 * PAD) * cm
    linhas_tot = _quebrar(totais, FONTE, TAM_CONTEUDO, largura)  # linha fixa, nunca cortada
    vagas = max_linhas - len(linhas_tot)
    if not itens or vagas <= 0:
        return linhas_tot
    texto = _compor_info(itens, lambda t: len(_quebrar(t, FONTE, TAM_CONTEUDO, largura)) <= vagas)
    return _caber_linhas(texto, FONTE, TAM_CONTEUDO, largura, vagas) + linhas_tot


# Descrição do Serviço: rótulo e, abaixo, linhas de 8 pt; a i-ésima linha ocupa de _DESC_TOPO + 8i até
# _DESC_TOPO + 8(i + 1) pt a partir do topo do quadro. Informações Complementares: idem, com _INFO_TOPO.
_DESC_TOPO = 8.6
_INFO_TOPO = 1.6


def _altura_necessaria_descricao(texto: str) -> float:
    n = len(_quebrar(texto, FONTE, TAM_CONTEUDO, (LARGURA - 2 * PAD) * cm))
    return (_DESC_TOPO + n * ENTRELINHA + 1.0) / cm


def _altura_necessaria_info(itens: list[tuple[str, str, bool]], totais: str) -> float:
    largura = (LARGURA - 2 * PAD) * cm
    n = len(_quebrar(totais, FONTE, TAM_CONTEUDO, largura))
    if itens:
        n += len(_quebrar(_compor_info(itens), FONTE, TAM_CONTEUDO, largura))
    return (_INFO_TOPO + n * ENTRELINHA + 1.0) / cm


def _dividir_altura(total: float, precisa_desc: float, precisa_info: float) -> tuple[float, float]:
    """Reparte a altura livre entre Descrição do Serviço e Informações Complementares (§2.3).

    Base: 40%/60%, proporção aproximada do modelo do Anexo I; o que um não usa vai para o outro.
    """
    base_desc = max(0.64, total * 0.40)
    base_info = total - base_desc
    if precisa_desc > base_desc and precisa_info < base_info:
        desc = min(precisa_desc, total - max(precisa_info, 1.0))
        return max(desc, base_desc), total - max(desc, base_desc)
    if precisa_info > base_info and precisa_desc < base_desc:
        desc = max(0.64, precisa_desc, total - precisa_info)
        return desc, total - desc
    return base_desc, base_info


def _desenhar_canhoto(pag: _Pagina, nota: _Nota, chave: str) -> None:
    # Bloco opcional (Nota 11), impresso como no modelo do Anexo I: quadro próprio de 20,40 x 0,67 cm (dentro
    # da borda da página), divisórias nas colunas 2 e 3 e rótulos em 7 pt, negrito e caixa alta.
    topo, fim = Y_CANHOTO, X0 + LARGURA
    pag.linha_h(topo, X0, fim)
    pag.linha_h(topo + H_CANHOTO, X0, fim)
    for x in (X0, COL[1] - 0.02, COL[2] - 0.02, fim):
        pag.linha_v(x, topo, H_CANHOTO)
    for x, rotulo in ((COL[0], "DATA CIENTIFICAÇÃO"), (COL[1], "IDENTIFICAÇÃO E ASSINATURA")):
        pag.texto(x + PAD, topo, 7.4, rotulo, FONTE_NEGRITO, TAM_TITULO)
    chave_nfse = _juntar(nota.t("nNFSe"), chave)
    pag.campo(Campo(COL[2], W2, "Nº NFS-E / CHAVE NFS-E", chave_nfse, 66, rotulo_destaque=True), topo, H_CANHOTO)


def gerar_danfse(nfse_xml: bytes | str, *, cancelada: bool = False, substituida: bool = False) -> bytes:
    """Gera o PDF do DANFSe (NT 008 v1.02) a partir do XML da NFS-e autorizada.

    Lê somente o XML (nada da configuração do emissor). `cancelada` e `substituida` acrescentam a marca
    d'água "CANCELADA" ou "SUBSTITUÍDA" (§2.5); com as duas, prevalece "SUBSTITUÍDA", porque a substituição
    é um cancelamento com nota substituta. Levanta ValueError se o XML não tiver NFSe/infNFSe.
    """
    nota = _Nota(_ler_inf_nfse(nfse_xml))
    ident = nota.inf.get("Id") or ""
    chave = ident[3:] if ident.startswith("NFS") else ident

    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4, invariant=1, pageCompression=1)
    c.setTitle(f"DANFSe {chave}".strip())
    c.setSubject("Documento Auxiliar da NFS-e (NT 008 SE/CGNFS-e v1.02)")
    c.setCreator("emissor-nfse")
    pag = _Pagina(c)

    _desenhar_cabecalho(pag, nota)
    topo = _desenhar_identificacao(pag, nota, chave, Y_TOPO + H_CABECALHO)

    pessoas = [_bloco_prestador(nota), _bloco_tomador(nota), _bloco_destinatario(nota), _bloco_intermediario(nota)]
    servico = _bloco_servico(nota)
    depois_desc = [_bloco_issqn(nota), _bloco_federal(nota), _bloco_ibscbs(nota), _bloco_valor_total(nota)]

    desc_trib = _limitar(_limpar(nota.t("xTribMun") or nota.t("xTribNac")) or TRACO, 170)
    desc_serv = _limitar(_limpar(nota.t("DPS/infDPS/serv/cServ/xDescServ"), uma_linha=False) or TRACO, 1300)
    info_itens, totais = _itens_info(nota), _totais_aproximados(nota)

    fixo = sum(b.altura for b in pessoas) + servico.altura + H_DESC_TRIB
    fixo += sum(b.altura for b in depois_desc) + H_TITULO_INFO
    livre = Y_CANHOTO - topo - fixo
    h_desc, h_info = _dividir_altura(
        livre, _altura_necessaria_descricao(desc_serv), _altura_necessaria_info(info_itens, totais)
    )

    for bloco in pessoas:
        topo = pag.bloco(bloco, topo)
    topo = pag.bloco(servico, topo)
    largura_util = (LARGURA - 2 * PAD) * cm
    pag.texto(X0 + PAD, topo, 7.6, _caber(desc_trib, FONTE, TAM_CONTEUDO, largura_util), FONTE, TAM_CONTEUDO)
    topo += H_DESC_TRIB
    _desenhar_descricao(pag, topo, h_desc, desc_serv)
    topo += h_desc
    for bloco in depois_desc:
        topo = pag.bloco(bloco, topo)

    pag.linha_h(topo)
    # O desenho do Anexo I deixa este título sem fundo, mas o §2.2.3 manda sombrear o título de todo bloco.
    pag.fundo(X0, topo, LARGURA, H_TITULO_INFO)
    pag.texto(X0 + PAD, topo, H_TITULO_INFO * cm / 2 + 2.5, "INFORMAÇÕES COMPLEMENTARES", FONTE_NEGRITO, TAM_TITULO)
    topo += H_TITULO_INFO
    max_linhas = int((h_info * cm - _INFO_TOPO) // ENTRELINHA)
    for i, lin in enumerate(_linhas_info(info_itens, totais, max_linhas)):
        pag.texto(X0 + PAD, topo, _INFO_TOPO + 6.0 + i * ENTRELINHA, lin, FONTE, TAM_CONTEUDO)

    _desenhar_canhoto(pag, nota, chave)

    marca = "SUBSTITUÍDA" if substituida else "CANCELADA" if cancelada else None
    pag.renderizar(marca)
    c.showPage()
    c.save()
    return buf.getvalue()
