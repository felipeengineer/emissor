"""DANFSe gerado localmente (emissor/danfse.py) conforme a NT 008 SE/CGNFS-e v1.02.

As fixtures em tests/fixtures foram geradas por tests/fixtures/gerar_fixtures.py (DPS do montar_dps) e
validam no XSD oficial da NFS-e. O texto do PDF é conferido com o pdftotext (poppler-utils) e o QR Code é
lido de volta da imagem renderizada pelo pdftoppm.
"""

from __future__ import annotations

import ast
import base64
import functools
import html
import math
import re
import shutil
import subprocess
import tempfile
import zlib
from pathlib import Path

import pytest
from lxml import etree

from emissor import VERSAO_APLICATIVO, danfse
from emissor.assinatura import verificar_assinatura
from emissor.danfse import TRACO, URL_CONSULTA_PUBLICA, gerar_danfse, matriz_qr, url_consulta_publica

FIXTURES = Path(__file__).parent / "fixtures"
ESQUEMAS = Path(danfse.__file__).parent / "schemas" / "1.01"
NS = "http://www.sped.fazenda.gov.br/nfse"
N = {"n": NS}

ME_EPP = "nfse_me_epp_homologacao.xml"  # tpAmb = 2, tomador CPF com endereço
MEI = "nfse_mei_producao.xml"  # tpAmb = 1, sem tomador
LONGOS = "nfse_textos_longos.xml"  # tpAmb = 1, textos no máximo do leiaute, CNPJ alfanumérico
TODAS = [ME_EPP, MEI, LONGOS]

CHAVE_ME_EPP = "35344012211222333000181000000000002726104488123750"

precisa_poppler = pytest.mark.skipif(
    not all(shutil.which(p) for p in ("pdftotext", "pdftoppm", "pdfinfo")), reason="poppler-utils não instalado"
)


# ---------------------------------------------------------------------------------------------- apoio


def xml_de(nome: str) -> bytes:
    return (FIXTURES / nome).read_bytes()


@functools.lru_cache(maxsize=None)
def pdf_de(nome: str, cancelada: bool = False, substituida: bool = False) -> bytes:
    return gerar_danfse(xml_de(nome), cancelada=cancelada, substituida=substituida)


def _poppler(programa: str, pdf: bytes, *args: str) -> bytes:
    with tempfile.TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / "danfse.pdf"
        arquivo.write_bytes(pdf)
        saida = ["-"] if programa == "pdftotext" else []
        return subprocess.run([programa, *args, str(arquivo), *saida], capture_output=True, check=True).stdout


def texto(pdf: bytes, *args: str) -> str:
    return _poppler("pdftotext", pdf, "-enc", "UTF-8", *args).decode("utf-8")


def texto_corrido(pdf: bytes, *args: str) -> str:
    """Texto sem espaços nem quebras: junta as letras da marca d'água diagonal, que o pdftotext separa."""
    return re.sub(r"\s+", "", texto(pdf, "-raw", *args))


def palavras(pdf: bytes) -> list[tuple[float, float, float, float, str]]:
    """(xMin, yMin, xMax, yMax, palavra) de cada palavra, via pdftotext -bbox."""
    saida = _poppler("pdftotext", pdf, "-enc", "UTF-8", "-bbox").decode("utf-8")
    padrao = r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>'
    return [(float(a), float(b), float(c), float(d), html.unescape(w)) for a, b, c, d, w in re.findall(padrao, saida)]


def _mesma_linha_contigua(a, b) -> bool:
    return abs(a[1] - b[1]) < 1.0 and 0 <= b[0] - a[2] < 6


def valores_abaixo(pdf: bytes, rotulo: str) -> list[str]:
    """Conteúdo impresso logo abaixo de cada ocorrência do rótulo inteiro (mesma coluna, linha seguinte)."""
    ws = palavras(pdf)
    alvo = rotulo.split()
    achados = []
    for i in range(len(ws) - len(alvo) + 1):
        trecho = ws[i : i + len(alvo)]
        if [w[4] for w in trecho] != alvo:
            continue
        if i + len(alvo) < len(ws) and _mesma_linha_contigua(trecho[-1], ws[i + len(alvo)]):
            continue  # é só o começo de um rótulo maior
        x0, y_base = trecho[0][0], max(w[3] for w in trecho)
        abaixo = [w for w in ws if abs(w[0] - x0) < 1.0 and y_base < w[1] < y_base + 9]
        if not abaixo:
            continue
        linha = [min(abaixo, key=lambda w: w[1])]
        for w in sorted((w for w in ws if abs(w[1] - linha[0][1]) < 1.0), key=lambda w: w[0]):
            if _mesma_linha_contigua(linha[-1], w):
                linha.append(w)
        achados.append(" ".join(w[4] for w in linha))
    return achados


def conteudo_pagina(pdf: bytes) -> str:
    """Operadores da página (streams descomprimidos)."""
    partes = []
    for dicionario, dados in re.findall(rb"<<([^<>]*)>>\s*stream\r?\n(.*?)endstream", pdf, re.S):
        dados = dados.strip()
        if b"ASCII85Decode" in dicionario:
            dados = base64.a85decode(dados.removesuffix(b"~>"))
        if b"FlateDecode" in dicionario:
            dados = zlib.decompress(dados)
        partes.append(dados.decode("latin-1"))
    return "\n".join(partes)


def alterar(nome: str, ajuste) -> bytes:
    """Cópia da fixture com o XML alterado por `ajuste(infNFSe)` (a assinatura deixa de valer)."""
    raiz = etree.fromstring(xml_de(nome))
    ajuste(raiz.find("n:infNFSe", N))
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")


def nota(nome: str) -> danfse._Nota:
    return danfse._Nota(danfse._ler_inf_nfse(xml_de(nome)))


def campo(bloco: danfse.Bloco, rotulo: str) -> str:
    return next(cp.valor for lin in bloco.linhas for cp in lin.campos if cp.rotulo == rotulo)


# ------------------------------------------------------------------------------------------ fixtures


@functools.lru_cache(maxsize=1)
def esquema_nfse() -> etree.XMLSchema:
    # NFSe_v1.01.xsd (cópia do pacote oficial) inclui os tipos que já estão em emissor/schemas/1.01.
    doc = etree.fromstring((FIXTURES / "NFSe_v1.01.xsd").read_bytes(), base_url=str(ESQUEMAS / "NFSe_v1.01.xsd"))
    return etree.XMLSchema(doc)


@pytest.mark.parametrize("nome", TODAS)
def test_fixtures_validam_no_xsd_oficial_e_tem_assinaturas(nome):
    raiz = etree.fromstring(xml_de(nome))
    esquema = esquema_nfse()
    assert esquema.validate(raiz), [str(e) for e in esquema.error_log]
    assert verificar_assinatura(raiz)
    dps = raiz.find("n:infNFSe/n:DPS", N)
    assert verificar_assinatura(dps)
    assert dps.findtext("n:infDPS/n:verAplic", namespaces=N) == VERSAO_APLICATIVO  # DPS do montar_dps


# ------------------------------------------------------------------------------------- PDF e página


@precisa_poppler
@pytest.mark.parametrize("nome", TODAS)
@pytest.mark.parametrize("marca", [{}, {"cancelada": True}, {"substituida": True}])
def test_pdf_valido_com_uma_pagina_a4(nome, marca):
    pdf = pdf_de(nome, **marca)
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
    assert len(re.findall(rb"/Type /Page\b", pdf)) == 1
    info = _poppler("pdfinfo", pdf).decode()
    assert re.search(r"^Pages:\s+1$", info, re.M)
    assert re.search(r"^Page size:\s+595\.2\d* x 841\.8\d* pts \(A4\)", info, re.M)


def test_so_usa_helvetica():
    # Desvio documentado: Helvetica (métrica da Arial) no lugar de Arial / Microsoft Sans Serif.
    fontes = set(re.findall(rb"/BaseFont /(\S+)", pdf_de(LONGOS, cancelada=True)))
    assert fontes == {b"Helvetica", b"Helvetica-Bold"}


def test_entrada_str_ou_bytes_e_saida_deterministica():
    xml = xml_de(ME_EPP)
    assert gerar_danfse(xml) == gerar_danfse(xml.decode("utf-8")) == gerar_danfse(xml)


def test_xml_sem_nfse_levanta_erro():
    with pytest.raises(ValueError, match="NFSe/infNFSe"):
        gerar_danfse(b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse"/>')


def test_modulo_nao_depende_da_configuracao_do_emissor():
    """Função pura: o gerador só importa biblioteca padrão, lxml e reportlab (nada de banco/serviço)."""
    arvore = ast.parse(Path(danfse.__file__).read_text(encoding="utf-8"))
    modulos = {a.name.split(".")[0] for n in ast.walk(arvore) if isinstance(n, ast.Import) for a in n.names}
    modulos |= {n.module.split(".")[0] for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom) and n.level == 0}
    assert not any(isinstance(n, ast.ImportFrom) and n.level > 0 for n in ast.walk(arvore))
    assert modulos <= {"__future__", "csv", "functools", "io", "math", "re", "unicodedata", "dataclasses",
                       "datetime", "decimal", "importlib", "typing", "lxml", "reportlab"}  # fmt: skip


# ------------------------------------------------------------------------------- conteúdo impresso


@precisa_poppler
def test_cabecalho_e_identificacao():
    t = texto(pdf_de(ME_EPP))
    for esperado in [
        "DANFSe v2.0",
        "Documento Auxiliar da NFS-e",
        "Município: Osasco / SP",
        "Ambiente Gerador: Sefin Nacional NFS-e",
        "Tipo de Ambiente: Homologação",
        CHAVE_ME_EPP,
        "08/10/2026 10:15:03",  # dhProc DD/MM/AAAA hh:mm:ss
        "08/10/2026 10:15:00",  # dhEmi
        "NFS-e Gerada",
        "Prestador",
    ]:
        assert esperado in t, esperado
    assert t.count(CHAVE_ME_EPP) == 2  # identificação e canhoto
    assert "27 / " + CHAVE_ME_EPP in t  # canhoto: nNFSe / chave
    assert valores_abaixo(pdf_de(ME_EPP), "COMPETÊNCIA DA NFS-E") == ["08/10/2026"]


@precisa_poppler
def test_prestador_tomador_e_valores_formatados():
    pdf = pdf_de(ME_EPP)
    t = texto(pdf)
    for esperado in [
        "11.222.333/0001-81",  # CNPJ
        "EXEMPLO TECNOLOGIA E SERVICOS LTDA",  # nome do prestador vem de infNFSe/emit (tpEmit = 1)
        "Avenida dos Autonomistas, 1500, Sala 304, Centro",
        "3534401 / 06.020-010",
        "529.982.247-25",  # CPF do tomador
        "Maria Aparecida dos Santos",
        "Praça da Sé, 100, Conjunto 12, Sé",
        "São Paulo / SP",  # nome do município pela tabela do IBGE
        "3550308 / 01.001-000",
        "(11) 98765-4321",
        "01.07.01 / -",  # cTribNac formatado, sem cTribMun
        "1.1501.30.00",  # NBS
        "Osasco / SP / BR",
        "Suporte técnico em informática, inclusive instalação",  # xTribNac (sem rótulo)
        "Operação Tributável",
        "Nenhum",  # regEspTrib = 0
        "Não Retido",
        "R$ 1.500,50",
        "R$ 50,00",
        "R$ 1.450,50",
        "R$ 29,16",
        "2,01%",
    ]:
        assert esperado in t, esperado
    assert valores_abaixo(pdf, "Simples Nacional na Data de Competência") == ["Optante - Microempresa ou Empresa de..."]
    assert valores_abaixo(pdf, "Regime de Apuração Tributária pelo SN") == [
        "Regime de apuração dos tributos federais e municipal pelo SN"
    ]


@precisa_poppler
def test_rotulos_com_a_pontuacao_do_modelo_do_anexo_i():
    # O modelo (NT 008, p. 25) usa hífen nestes dois rótulos e travessão nos demais.
    t = texto(pdf_de(LONGOS))
    for rotulo in ["Contribuição Previdenciária - Retida", "Alíquota - CBS", "Contribuições Sociais – Retidas",
                   "PIS - Débito Apuração Própria", "Alíquota Efetiva – CBS", "Valor Total Apurado – CBS"]:  # fmt: skip
        assert rotulo in t, rotulo
    assert "Previdenciária – Retida" not in t and "Alíquota – CBS" not in t


CM_PT = 72 / 2.54


def posicoes(ws: list, rotulo: str) -> list[tuple[float, float, float, float]]:
    """bbox (pt, origem no topo) do rótulo inteiro em cada ocorrência (não conta prefixo de rótulo maior)."""
    alvo, achados = rotulo.split(), []
    for i in range(len(ws) - len(alvo) + 1):
        trecho = ws[i : i + len(alvo)]
        if [w[4] for w in trecho] != alvo:
            continue
        if i + len(alvo) < len(ws) and _mesma_linha_contigua(trecho[-1], ws[i + len(alvo)]):
            continue
        achados.append((trecho[0][0], min(w[1] for w in trecho), trecho[-1][2], max(w[3] for w in trecho)))
    return achados


def areas_cinza(pdf: bytes) -> list[tuple[float, float, float, float]]:
    """Retângulos preenchidos com cinza 5% (x0, topo, x1, base), em pt com origem no topo da página."""
    ops = conteudo_pagina(pdf)
    trecho = ops.split("0 0 0 .05 k\n", 1)[1].split("0 0 0 1 k", 1)[0]
    rets = [tuple(map(float, r)) for r in re.findall(r"n ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re f\*", trecho)]
    return [(x, danfse.PAGINA_A - y - h, x + w, danfse.PAGINA_A - y) for x, y, w, h in rets]


@precisa_poppler
def test_sombreamento_5_por_cento_so_onde_a_nt_manda():
    """§2.2.3: cabeçalho, títulos dos blocos, 'Emitente da NFS-e' e 'Valor Líquido + IBS/CBS'; o resto em branco."""
    pdf = pdf_de(LONGOS)  # todos os blocos impressos por inteiro
    cinzas, ws = areas_cinza(pdf), palavras(pdf)
    assert "0 0 0 .05 k" in conteudo_pagina(pdf)
    assert len(cinzas) == 13  # cabeçalho + 9 títulos + Informações Complementares + Emitente + Valor Líquido
    assert all(0.30 * CM_PT - 0.01 <= c[0] and c[2] <= 20.70 * CM_PT + 0.01 for c in cinzas)

    def no_cinza(rotulo: str) -> bool:
        (x0, y0, x1, y1), *_ = posicoes(ws, rotulo) or pytest.fail(rotulo)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return any(c[0] <= cx <= c[2] and c[1] <= cy <= c[3] for c in cinzas)

    sombreados = ["DANFSe v2.0", "Município: Osasco / SP", "PRESTADOR / FORNECEDOR", "TOMADOR / ADQUIRENTE",
                  "DESTINATÁRIO DA OPERAÇÃO", "INTERMEDIÁRIO DA OPERAÇÃO", "SERVIÇO PRESTADO",
                  "TRIBUTAÇÃO MUNICIPAL (ISSQN)", "TRIBUTAÇÃO FEDERAL (EXCETO CBS)", "TRIBUTAÇÃO IBS / CBS",
                  "VALOR TOTAL DA NFS-E", "INFORMAÇÕES COMPLEMENTARES", "EMITENTE DA NFS-E",
                  "VALOR LÍQUIDO DA NFS-e + IBS/CBS"]  # fmt: skip
    brancos = ["CHAVE DE ACESSO DA NFS-E", "SITUAÇÃO DA NFS-E", "FINALIDADE", "CNPJ / CPF / NIF",
               "Nome / Nome Empresarial", "Descrição do Serviço", "VALOR DA OPERAÇÃO / SERVIÇO",
               "VALOR LÍQUIDO DA NFS-e", "Total do IBS/CBS", "DATA CIENTIFICAÇÃO", "Nº NFS-E / CHAVE NFS-E"]  # fmt: skip
    assert [r for r in sombreados if not no_cinza(r)] == []
    assert [r for r in brancos if no_cinza(r)] == []


def test_borda_de_1pt_entre_015_e_020_cm_e_divisorias_de_meio_ponto():
    """§2.2.2 e §2.2.3: margem de 0,15 a 0,20 cm (inclusive em cima e embaixo), borda de 1 pt, linhas de 0,5 pt."""
    ops = conteudo_pagina(pdf_de(ME_EPP))
    x, y, w, h = map(float, re.search(r"\n1 w\nn ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re S", ops).groups())
    for margem in (x, y, danfse.PAGINA_L - (x + w), danfse.PAGINA_A - (y + h)):
        assert 0.15 <= (margem - 0.5) / CM_PT and (margem + 0.5) / CM_PT <= 0.20  # as duas faces do traço de 1 pt
    espessuras = re.findall(r"(?m)^([\d.]+) w$", ops)
    assert espessuras.count("1") == 1 and set(espessuras) == {".5", "1"}


@precisa_poppler
def test_ordem_e_posicao_dos_blocos_como_no_anexo_i():
    ws = palavras(pdf_de(LONGOS))
    titulos = ["CHAVE DE ACESSO DA NFS-E", "PRESTADOR / FORNECEDOR", "TOMADOR / ADQUIRENTE", "DESTINATÁRIO DA OPERAÇÃO",
               "INTERMEDIÁRIO DA OPERAÇÃO", "SERVIÇO PRESTADO", "Descrição do Serviço", "TRIBUTAÇÃO MUNICIPAL (ISSQN)",
               "TRIBUTAÇÃO FEDERAL (EXCETO CBS)", "TRIBUTAÇÃO IBS / CBS", "VALOR TOTAL DA NFS-E",
               "INFORMAÇÕES COMPLEMENTARES", "DATA CIENTIFICAÇÃO"]  # fmt: skip
    achados = [posicoes(ws, t) for t in titulos]
    assert all(len(a) == 1 for a in achados), titulos
    topos = [a[0][1] for a in achados]
    assert topos == sorted(topos)
    assert all(abs(a[0][0] - (danfse.X0 + danfse.PAD) * CM_PT) < 0.5 for a in achados)  # 1ª coluna
    # Posições da tabela 2.4.5 enquanto não há bloco suprimido (topo do bloco, em cm).
    for rotulo, topo_cm in (("CNPJ / CPF / NIF", 4.34), ("Indicador Municipal (Inscrição)", 4.34)):
        assert abs(posicoes(ws, rotulo)[0][1] / CM_PT - topo_cm) < 0.15, rotulo
    tomador = posicoes(ws, "TOMADOR / ADQUIRENTE")[0]
    assert abs(tomador[3] / CM_PT - (6.92 + 0.645 / 2)) < 0.2  # título centrado na 1ª linha do bloco (6,92 cm)
    colunas = {"Código de Tributação Nacional / Municipal": 5.41, "Código da NBS": 10.51,
               "Local da Prestação / Sigla UF / País": 15.62, "Regime de Apuração Tributária pelo SN": 5.41,
               "Município / Sigla UF / País de Incidência do ISSQN": 10.51, "Tipo de Tributação do ISSQN": 5.41}  # fmt: skip
    for rotulo, x_cm in colunas.items():
        assert abs(posicoes(ws, rotulo)[0][0] / CM_PT - (x_cm + danfse.PAD)) < 0.02, rotulo


def _rotulo_e_tamanho(ops: str, rotulo_pdf: str) -> float:
    """Corpo da fonte (Tf) usado no texto `rotulo_pdf` (como aparece no stream, com escapes octais)."""
    achado = re.search(r"BT /F2 ([\d.]+) Tf [\d.]+ TL ET\nBT [^\n]*\(" + re.escape(rotulo_pdf), ops)
    assert achado, rotulo_pdf
    return float(achado.group(1))


def test_canhoto_em_quadro_proprio_com_rotulos_de_7pt():
    """Anexo I: canhoto em quadro de 20,40 cm dentro da borda, divisórias nas colunas 2 e 3, rótulos 7 pt."""
    ops = conteudo_pagina(pdf_de(ME_EPP))
    cm_pt = 72 / 2.54
    topo = danfse.PAGINA_A - danfse.Y_CANHOTO * cm_pt
    base = topo - danfse.H_CANHOTO * cm_pt
    segmentos = [tuple(map(float, s)) for s in re.findall(r"n ([\d.]+) ([\d.]+) m ([\d.]+) ([\d.]+) l S", ops)]

    def perto(a: float, b: float) -> bool:
        return abs(a - b) < 0.1

    x_ini, x_fim = danfse.X0 * cm_pt, (danfse.X0 + danfse.LARGURA) * cm_pt
    horizontais = [s for s in segmentos if perto(s[1], s[3]) and (perto(s[1], topo) or perto(s[1], base))]
    assert len(horizontais) == 2
    assert all(perto(s[0], x_ini) and perto(s[2], x_fim) for s in horizontais)  # não encosta na borda da página
    verticais = sorted(s[0] for s in segmentos if perto(s[0], s[2]) and perto(max(s[1], s[3]), topo))
    assert [round(x / cm_pt, 2) for x in verticais] == [0.30, 5.39, 10.49, 20.70]
    for rotulo in (r"DATA CIENTIFICA\307\303O", r"IDENTIFICA\307\303O E ASSINATURA", r"N\272 NFS-E / CHAVE NFS-E"):
        assert _rotulo_e_tamanho(ops, rotulo) == 7


@precisa_poppler
def test_texto_do_qr_code_em_tres_linhas_no_quadro_complemento():
    # Quadro complemento do QR Code (2.4.5): 4,72 x 0,68 cm em X 15,80 / Y 3,36; 3 linhas de 6 pt (2.4.3).
    assert danfse.QR_TEXTO_L == 4.72
    cm_pt = 72 / 2.54
    ws = [w for w in palavras(pdf_de(ME_EPP)) if w[1] > 3.3 * cm_pt and w[3] < 4.3 * cm_pt and w[0] > 15.7 * cm_pt]
    assert " ".join(w[4] for w in ws) == danfse.TEXTO_QR
    assert len({round(w[1]) for w in ws}) == 3
    assert min(w[0] for w in ws) >= 15.80 * cm_pt - 0.5
    assert max(w[2] for w in ws) <= (15.80 + 4.72) * cm_pt


@precisa_poppler
def test_municipio_do_cabecalho_mantem_a_uf_quando_encurtado():
    assert danfse._municipio_uf("Osasco", "SP", 37) == "Osasco / SP"
    assert danfse._municipio_uf("", "", 37) == TRACO
    assert danfse._municipio_uf("", "SP", 37) == "- / SP"
    longo = danfse._municipio_uf("São José do Vale do Rio Preto Municipal Longo", "SP", 37)
    assert len(longo) == 37 and longo.endswith("... / SP")

    def municipio_longo(inf):
        inf.find("n:xLocEmi", N).text = "São José do Vale do Rio Preto Municipal Longo"

    t = re.sub(r"\s+", " ", texto(gerar_danfse(alterar(ME_EPP, municipio_longo))))
    assert "Município: São José do Vale do Rio Preto... / SP" in t


@precisa_poppler
def test_tarja_sem_validade_juridica_so_em_homologacao():
    assert "NFS-e SEM VALIDADE JURÍDICA" in texto(pdf_de(ME_EPP))  # tpAmb = 2
    assert "0 1 1 0 k" in conteudo_pagina(pdf_de(ME_EPP))  # vermelho M100/Y100
    for nome in (MEI, LONGOS):  # tpAmb = 1
        assert "SEM VALIDADE" not in texto(pdf_de(nome))
        assert "0 1 1 0 k" not in conteudo_pagina(pdf_de(nome))
    assert "Tipo de Ambiente: Produção" in texto(pdf_de(MEI))


@precisa_poppler
def test_marca_dagua_cancelada_e_substituida_na_diagonal():
    assert "CANCELADA" in texto_corrido(pdf_de(ME_EPP, cancelada=True))
    assert "SUBSTITUÍDA" in texto_corrido(pdf_de(LONGOS, substituida=True))
    for nome in TODAS:
        corrido = texto_corrido(pdf_de(nome))
        assert "CANCELADA" not in corrido and "SUBSTITUÍDA" not in corrido
    # Diagonal: some quando o pdftotext descarta o texto diagonal.
    assert "CANCELADA" not in texto_corrido(pdf_de(ME_EPP, cancelada=True), "-nodiag")
    # As duas situações: prevalece a substituição (cancelamento por substituição).
    ambas = texto_corrido(gerar_danfse(xml_de(MEI), cancelada=True, substituida=True))
    assert "SUBSTITUÍDA" in ambas and "CANCELADA" not in ambas


def test_marca_dagua_fonte_normal_50pt_ou_mais_cinza_k35():
    ops = conteudo_pagina(pdf_de(ME_EPP, cancelada=True))
    bloco = re.search(r"0 0 0 \.35 k\n(\S+) (\S+) (\S+) (\S+) [\d.]+ [\d.]+ cm\nBT /F1 ([\d.]+) Tf.*?\(CANCELADA\) Tj", ops, re.S)
    assert bloco, "marca d'água não encontrada"
    a, b = float(bloco.group(1)), float(bloco.group(2))
    assert 30 < math.degrees(math.atan2(b, a)) < 70  # diagonal
    assert float(bloco.group(5)) >= 50
    assert re.search(r"/BaseFont /Helvetica /Encoding /WinAnsiEncoding /Name /F1\b", pdf_de(ME_EPP).decode("latin-1"))


@precisa_poppler
@pytest.mark.parametrize("nome", TODAS)
def test_qr_code_le_a_url_da_consulta_publica(nome, tmp_path):
    from PIL import Image

    raiz = etree.fromstring(xml_de(nome))
    chave = raiz.find("n:infNFSe", N).get("Id")[3:]
    url = url_consulta_publica(chave)
    assert url == "https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave=" + chave == URL_CONSULTA_PUBLICA + chave
    pdf = pdf_de(nome)
    assert f"/URI ({url})".encode() in pdf  # link clicável sobre o QR Code

    # Renderiza só a região do QR Code a 600 dpi e lê os módulos de volta.
    dpi, margem = 600, 0.1
    px = lambda centimetros: round(centimetros / 2.54 * dpi)  # noqa: E731
    (tmp_path / "d.pdf").write_bytes(pdf)
    lado_px = px(danfse.QR_LADO + 2 * margem)
    subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-gray", "-png", "-singlefile", "-x", str(px(danfse.QR_X - margem)),
         "-y", str(px(danfse.QR_Y - margem)), "-W", str(lado_px), "-H", str(lado_px), str(tmp_path / "d.pdf"),
         str(tmp_path / "qr")],
        check=True,
    )  # fmt: skip
    imagem = Image.open(tmp_path / "qr.png").convert("L")
    pixels = imagem.load()
    escuros = [(x, y) for y in range(imagem.height) for x in range(imagem.width) if pixels[x, y] < 128]
    x0, x1 = min(p[0] for p in escuros), max(p[0] for p in escuros)
    y0, y1 = min(p[1] for p in escuros), max(p[1] for p in escuros)
    assert (x1 - x0) / dpi * 2.54 >= 1.52 - 0.01  # tamanho mínimo do QR Code (§2.4.3)
    # Coordenadas do §2.4.3 (X 17,48 cm e Y 1,67 cm): o primeiro módulo escuro está no canto do quadro.
    assert (danfse.QR_X, danfse.QR_Y) == (17.48, 1.67)
    assert abs(x0 / dpi * 2.54 - margem) < 0.02 and abs(y0 / dpi * 2.54 - margem) < 0.02

    def ler(n: int) -> list[list[bool]]:
        passo_x, passo_y = (x1 - x0 + 1) / n, (y1 - y0 + 1) / n
        return [[pixels[int(x0 + (c + 0.5) * passo_x), int(y0 + (lin + 0.5) * passo_y)] < 128 for c in range(n)]
                for lin in range(n)]  # fmt: skip

    esperada = matriz_qr(url)
    assert ler(len(esperada)) == esperada
    for outra in (url[:-1] + ("1" if url[-1] != "1" else "2"), url.replace("tpc=1", "tpc=2")):
        errada = matriz_qr(outra)
        assert ler(len(errada)) != errada


@precisa_poppler
def test_campos_sem_informacao_no_xml_recebem_traco():
    pdf = pdf_de(MEI)
    for rotulo in [
        "Regime de Apuração Tributária pelo SN",  # MEI não tem regApTribSN
        "Indicador Municipal (Inscrição)",
        "Telefone",
        "E-mail",
        "FINALIDADE",  # sem grupo IBSCBS
        "BC ISSQN",
        "Alíquota Aplicada",
        "ISSQN Apurado",
        "IRRF",
        "CST / cClassTrib",
        "Total do IBS/CBS",
        "VALOR LÍQUIDO DA NFS-e + IBS/CBS",
    ]:
        achados = valores_abaixo(pdf, rotulo)
        assert achados and all(v == TRACO for v in achados), (rotulo, achados)
    assert valores_abaixo(pdf, "VALOR LÍQUIDO DA NFS-e") == ["R$ 80,00"]


@precisa_poppler
def test_blocos_reduzidos_sem_tomador_destinatario_e_intermediario():
    t = texto(pdf_de(MEI))
    assert "TOMADOR/ADQUIRENTE DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e" in t
    assert "DESTINATÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e" in t
    assert "INTERMEDIÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e" in t
    assert "TOMADOR / ADQUIRENTE" not in t
    assert "NFS-e MEI" in t  # cStat 107
    assert "JOAO DA SILVA BARBEARIA" in t


@precisa_poppler
def test_destinatario_e_intermediario_impressos():
    t = texto(pdf_de(LONGOS))
    for esperado in [
        "DESTINATÁRIO DA OPERAÇÃO",
        "123.456.789-09",
        "Carlos Eduardo Pereira",
        "Campinas / SP",
        "INTERMEDIÁRIO DA OPERAÇÃO",
        "11.444.777/0001-61",
        "INTERMEDIADORA DE SERVICOS DIGITAIS S.A.",
        "Rio de Janeiro / RJ",
        "3304557 / 20.040-002",
    ]:
        assert esperado in t, esperado
    assert "NÃO IDENTIFICADO" not in t


@precisa_poppler
def test_destinatario_e_o_proprio_tomador():
    def ajuste(inf):
        ibs = inf.find("n:DPS/n:infDPS/n:IBSCBS", N)
        ibs.remove(ibs.find("n:dest", N))
        ibs.find("n:indDest", N).text = "0"

    assert "O DESTINATÁRIO É O PRÓPRIO TOMADOR/ADQUIRENTE DA OPERAÇÃO" in texto(gerar_danfse(alterar(LONGOS, ajuste)))


@precisa_poppler
def test_cnpj_alfanumerico_formatado_por_fatiamento():
    assert "12.ABC.345/01DE-35" in texto(pdf_de(LONGOS))
    assert danfse._cnpj("12ABC34501DE35") == "12.ABC.345/01DE-35"


@precisa_poppler
def test_tributacao_ibs_cbs_e_retencao():
    t = texto(pdf_de(LONGOS))
    for esperado in [
        "000 / 000001",  # CST / cClassTrib
        "100301 / 3550308 / São Paulo / SP",  # cIndOp / cLocalidadeIncid / xLocalidadeIncid / UF
        "R$ 240,00",  # exclusões (vISSQN) e total de retenções
        "R$ 11.760,00",
        "0,10% / 0,00%",
        "R$ 105,84",
        "R$ 117,60",  # vIBSTot + vCBS
        "Retido pelo Tomador",
        "NFS-e regular",
    ]:
        assert esperado in t, esperado


@precisa_poppler
def test_truncamento_com_reticencias():
    nome = etree.fromstring(xml_de(LONGOS)).findtext("n:infNFSe/n:DPS/n:infDPS/n:toma/n:xNome", namespaces=N)
    assert len(nome) > 250
    pdf = pdf_de(LONGOS)
    t = texto(pdf)
    # Nome do tomador: no máximo 80 caracteres (77 + "...") e o que couber na largura do campo.
    impresso = valores_abaixo(pdf, "Nome / Nome Empresarial")[1]  # prestador, tomador, destinatário...
    assert impresso.endswith("...") and len(impresso) <= 80
    assert nome.startswith(impresso[:-3]) and len(impresso) > 40
    assert "FIM-DO-NOME" not in t
    # Descrição do serviço (2000 caracteres) e informações complementares não cabem inteiras.
    assert "FIM-TXT" not in t
    layout = texto(pdf, "-layout")
    descricao = layout.split("Descrição do Serviço", 1)[1].split("Tipo de Tributação do ISSQN", 1)[0].strip()
    assert descricao.startswith("Contrato 2026/0042. Etapa 1:") and descricao.endswith("...")
    info = t.split("INFORMAÇÕES COMPLEMENTARES", 1)[1]
    assert "..." in info
    # Os itens obrigatórios (Nota 7) e a linha de totais (Nota 10) não são cortados.
    assert "NFS-e Subst.: 35344012211222333000181000000000003026091002003004" in info
    assert "Totais Aproximados dos Tributos cfe. Lei nº 12.741/2012" in info
    # Ordem e separador do 2.4.5.
    plano = re.sub(r"\s+", " ", info)
    ordem = ["Inf. Cont.:", "NFS-e Subst.:", "Doc. Ref.:", "Doc. Tec.:", "Núm. Ped.:", "Item Ped.: 10, 20, 30",
             "Inf. A. T. Mun.:", "Totais Aproximados"]  # fmt: skip
    posicoes = [plano.index(item) for item in ordem]
    assert posicoes == sorted(posicoes)
    assert " | NFS-e Subst.:" in plano


def test_limite_de_2000_caracteres_preserva_itens_curtos():
    itens = [("Inf. Cont.:", "x" * 3000, True), ("NFS-e Subst.:", "1" * 50, False), ("Inf. A. T. Mun.:", "y" * 2000, True)]
    texto_info = danfse._compor_info(itens)
    assert len(texto_info) <= 2000
    assert "NFS-e Subst.: " + "1" * 50 in texto_info
    assert texto_info.count("...") == 2
    curto = danfse._compor_info([("Doc. Ref.:", "abc", True), ("Núm. Ped.:", "9", False)])
    assert curto == "Doc. Ref.: abc | Núm. Ped.: 9"


@precisa_poppler
def test_totais_aproximados_dos_tributos():
    assert (
        "Totais Aproximados dos Tributos cfe. Lei nº 12.741/2012: Federais: - ; Estaduais: - ; Municipais: - ; "
        "Simples Nacional: 6,00%"
    ) in texto(pdf_de(ME_EPP))  # ME/EPP: pTotTribSN
    mei = texto(pdf_de(MEI))  # MEI: indTotTrib = 0
    assert "Totais Aproximados dos Tributos cfe. Lei nº 12.741/2012: Federais: - ; Estaduais: - ; Municipais: -" in mei
    assert "Simples Nacional:" not in mei

    def valores_monetarios(inf):
        tot = inf.find("n:DPS/n:infDPS/n:valores/n:trib/n:totTrib", N)
        for filho in list(tot):
            tot.remove(filho)
        v = etree.SubElement(tot, f"{{{NS}}}vTotTrib")
        for tag, valor in (("vTotTribFed", "10.00"), ("vTotTribEst", "0.00"), ("vTotTribMun", "3.50")):
            etree.SubElement(v, f"{{{NS}}}{tag}").text = valor

    t = texto(gerar_danfse(alterar(ME_EPP, valores_monetarios)))
    assert "Federais: R$ 10,00 ; Estaduais: R$ 0,00 ; Municipais: R$ 3,50" in t


def _sub(pai, tag: str, valor: str | None = None):
    el = etree.SubElement(pai, f"{{{NS}}}{tag}")
    el.text = valor
    return el


def _tudo_preenchido(inf):
    """LONGOS com todos os grupos opcionais: tomador no exterior, imunidade, suspensão, BM, retenções
    federais (tpRetPisCofins = 1), obra, evento e totais em R$ (a ordem do XSD não importa ao DANFSe)."""
    dps = inf.find("n:DPS/n:infDPS", N)
    toma = dps.find("n:toma", N)
    for filho in list(toma):
        toma.remove(filho)
    _sub(toma, "NIF", "DE1234567890123456789012345678901234567")
    _sub(toma, "xNome", "Müller & Söhne GmbH – Zweigniederlassung Düsseldorf")
    end = _sub(toma, "end")
    ext = _sub(end, "endExt")
    for tag, valor in (("cPais", "DE"), ("cEndPost", "40213"), ("xCidade", "Düsseldorf"),
                       ("xEstProvReg", "Nordrhein-Westfalen")):  # fmt: skip
        _sub(ext, tag, valor)
    _sub(end, "xLgr", "Königsallee")
    _sub(end, "nro", "92a")
    interm = dps.find("n:interm", N)
    for filho in list(interm):
        interm.remove(filho)
    _sub(interm, "cNaoNIF", "1")
    _sub(interm, "xNome", "Intermediario Exterior Ltd.")
    trib = dps.find("n:valores/n:trib", N)
    mun = trib.find("n:tribMun", N)
    mun.find("n:tribISSQN", N).text = "2"
    _sub(mun, "tpImunidade", "3")
    susp = _sub(mun, "exigSusp")
    _sub(susp, "tpSusp", "2")
    _sub(susp, "nProcesso", "1" * 30)
    bm = _sub(mun, "BM")
    _sub(bm, "nBM", "35503080400001")
    _sub(bm, "vRedBCBM", "100.00")
    _sub(inf.find("n:valores", N), "tpBM", "3")
    _sub(inf.find("n:valores", N), "vCalcBM", "100.00")
    fed = _sub(trib, "tribFed")
    pc = _sub(fed, "piscofins")
    for tag, valor in (("CST", "01"), ("vPis", "78.00"), ("vCofins", "360.00"), ("tpRetPisCofins", "1")):
        _sub(pc, tag, valor)
    for tag, valor in (("vRetCP", "1320.00"), ("vRetIRRF", "180.00"), ("vRetCSLL", "120.00")):
        _sub(fed, tag, valor)
    tot = trib.find("n:totTrib", N)
    for filho in list(tot):
        tot.remove(filho)
    v = _sub(tot, "vTotTrib")
    for tag, valor in (("vTotTribFed", "1234.56"), ("vTotTribEst", "0.00"), ("vTotTribMun", "240.00")):
        _sub(v, tag, valor)
    serv = dps.find("n:serv", N)
    obra = _sub(serv, "obra")
    _sub(obra, "cObra", "OBRA-9988776655")
    _sub(obra, "inscImobFisc", "IMOB-12345")
    _sub(_sub(serv, "atvEvento"), "idAtvEvt", "EVT-2026-0001")
    _sub(serv.find("n:cServ", N), "cTribMun", "001")


@precisa_poppler
def test_nota_com_todos_os_grupos_opcionais():
    pdf = gerar_danfse(alterar(LONGOS, _tudo_preenchido))
    assert len(re.findall(rb"/Type /Page\b", pdf)) == 1
    t = re.sub(r"\s+", " ", texto(pdf))
    for esperado in [
        "DE1234567890",  # NIF (cortado pela largura)
        "Düsseldorf / Nordrhein-Westfalen",  # endExt: xCidade / xEstProvReg
        "- / 40213",  # endExt: sem código IBGE / cEndPost
        "Dispensado do NIF",  # cNaoNIF
        "01.07.01 / 001",  # cTribNac / cTribMun
        "Imunidade",
        "Patrimônio, renda ou serviços dos par...",  # tpImunidade em 40 caracteres
        "Exigibilidade Suspensa por Processo A...",  # tpSusp em 40 caracteres
        "1" * 30,  # nProcesso
        "Redução da BC em R$ 100,00",  # tpBM 3 com vRedBCBM
    ]:
        assert esperado in t, esperado
    # tpRetPisCofins = 1: Contribuições Sociais = vRetCSLL + vPis + vCofins; PIS/COFINS próprios = 0,00.
    assert valores_abaixo(pdf, "Contribuições Sociais – Retidas") == ["R$ 558,00"]
    assert valores_abaixo(pdf, "PIS - Débito Apuração Própria") == ["R$ 0,00"]
    assert valores_abaixo(pdf, "COFINS - Débito Apuração Própria") == ["R$ 0,00"]
    assert valores_abaixo(pdf, "Descrição Contrib. Sociais – Retidas") == ["PIS/COFINS Retido"]
    assert valores_abaixo(pdf, "IRRF") == ["R$ 180,00"]
    assert valores_abaixo(pdf, "Contribuição Previdenciária - Retida") == ["R$ 1.320,00"]
    # IBS/CBS: exclusões = vDescIncond + vCalcReeRepRes + vISSQN + vPis + vCofins (240 + 78 + 360).
    assert valores_abaixo(pdf, "Exclusões e Reduções da Base de Cálculo") == ["R$ 678,00"]
    # Notas 8 e 9 e Nota 10 com valores monetários.
    for esperado in ["Cod. Obra: OBRA-9988776655", "Insc. Imob.: IMOB-12345", "Cod. Evt.: EVT-2026-0001",
                     "Federais: R$ 1.234,56 ; Estaduais: R$ 0,00 ; Municipais: R$ 240,00"]:  # fmt: skip
        assert esperado in t, esperado


@precisa_poppler
@pytest.mark.parametrize("nome", [*TODAS, "todos os grupos"])
def test_textos_nao_se_sobrepoem_nem_saem_da_area_util(nome):
    pdf = gerar_danfse(alterar(LONGOS, _tudo_preenchido)) if nome == "todos os grupos" else pdf_de(nome)
    cm_pt, folga = 72 / 2.54, 1.2
    ws = palavras(pdf)
    assert len(ws) > 400
    # Área útil: 0,30 a 20,70 cm na horizontal; do topo do cabeçalho até a base do canhoto.
    fora = [w for w in ws if w[0] < 0.30 * cm_pt - 0.5 or w[2] > 20.70 * cm_pt + 0.5 or w[1] < 0.30 * cm_pt
            or w[3] > (danfse.Y_CANHOTO + danfse.H_CANHOTO) * cm_pt]  # fmt: skip
    assert not fora
    sobrepostas = [(a[4], b[4]) for i, a in enumerate(ws) for b in ws[i + 1 :]
                   if a[0] + folga < b[2] and b[0] + folga < a[2] and a[1] + folga < b[3] and b[1] + folga < a[3]]  # fmt: skip
    assert not sobrepostas


@precisa_poppler
def test_linha_pis_cofins_so_ate_competencia_2026():
    assert "PIS - Débito Apuração Própria" in texto(pdf_de(ME_EPP))

    def competencia_2027(inf):
        inf.find("n:DPS/n:infDPS/n:dCompet", N).text = "2027-01-04"

    t = texto(gerar_danfse(alterar(ME_EPP, competencia_2027)))
    assert "PIS - Débito Apuração Própria" not in t
    assert "Descrição Contrib. Sociais" not in t
    assert "TRIBUTAÇÃO FEDERAL (EXCETO CBS)" in t


@precisa_poppler
def test_operacao_nao_sujeita_ao_issqn():
    def nao_incidencia(inf):
        inf.find("n:DPS/n:infDPS/n:valores/n:trib/n:tribMun/n:tribISSQN", N).text = "4"

    t = texto(gerar_danfse(alterar(ME_EPP, nao_incidencia)))
    assert "TRIBUTAÇÃO MUNICIPAL (ISSQN) - OPERAÇÃO NÃO SUJEITA AO ISSQN" in t
    assert "Tipo de Tributação do ISSQN" not in t


def test_linhas_suprimiveis_do_issqn():
    # Nota 5: "Benefício Municipal..." só aparece com dados (desconto incondicionado na ME/EPP).
    assert any(cp.rotulo == "Benefício Municipal" for lin in danfse._bloco_issqn(nota(ME_EPP)).linhas for cp in lin.campos)
    assert not any(cp.rotulo == "Benefício Municipal" for lin in danfse._bloco_issqn(nota(MEI)).linhas for cp in lin.campos)


def test_prestador_so_usa_emit_quando_ele_e_o_emitente():
    bloco = danfse._bloco_prestador(nota(ME_EPP))
    assert campo(bloco, "Nome / Nome Empresarial") == "EXEMPLO TECNOLOGIA E SERVICOS LTDA"
    assert campo(bloco, "Município / Sigla UF") == "Osasco / SP"

    def emitido_pelo_tomador(inf):
        inf.find("n:DPS/n:infDPS/n:tpEmit", N).text = "2"

    outra = danfse._Nota(danfse._ler_inf_nfse(alterar(ME_EPP, emitido_pelo_tomador)))
    bloco = danfse._bloco_prestador(outra)
    assert campo(bloco, "Nome / Nome Empresarial") == TRACO  # emit seria o tomador, não o prestador
    assert campo(bloco, "Endereço") == TRACO
    assert campo(bloco, "CNPJ / CPF / NIF") == "11.222.333/0001-81"


@precisa_poppler
def test_xml_minimo_sai_com_tracos():
    chave = "3550308" + "2" + "11222333000181" + "0" * 27 + "1"
    xml = f'<NFSe xmlns="{NS}" versao="1.00"><infNFSe Id="NFS{chave}"><nNFSe>42</nNFSe></infNFSe></NFSe>'
    pdf = gerar_danfse(xml)
    assert len(re.findall(rb"/Type /Page\b", pdf)) == 1
    t = texto(pdf)
    assert chave in t and "42 / " + chave in t
    assert valores_abaixo(pdf, "NÚMERO DA NFS-E") == ["42"]
    assert valores_abaixo(pdf, "COMPETÊNCIA DA NFS-E") == [TRACO]
    assert valores_abaixo(pdf, "Nome / Nome Empresarial") == [TRACO]


@precisa_poppler
def test_xml_nao_resolve_entidades_externas(tmp_path):
    segredo = tmp_path / "segredo.txt"
    segredo.write_text("CONTEUDO-SECRETO")
    xml = xml_de(MEI).decode("utf-8").replace(
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<?xml version="1.0"?><!DOCTYPE NFSe [<!ENTITY x SYSTEM "file://{segredo}">]>',
    )
    xml = xml.replace("<xNome>JOAO DA SILVA BARBEARIA</xNome>", "<xNome>&x;</xNome>")
    assert "CONTEUDO-SECRETO" not in texto(gerar_danfse(xml.encode("utf-8")))


# ------------------------------------------------------------------------------------ formatação


def test_formatadores():
    assert danfse._moeda("1234567.8") == "R$ 1.234.567,80"
    assert danfse._moeda("0") == "R$ 0,00"
    assert danfse._moeda(None) == TRACO
    assert danfse._perc("2.01") == "2,01%"
    assert danfse._cpf("52998224725") == "529.982.247-25"
    assert danfse._cep("01001000") == "01.001-000"
    assert danfse._nbs("115013000") == "1.1501.30.00"
    assert danfse._ctrib_nac("010701") == "01.07.01"
    assert danfse._data("2026-10-08") == "08/10/2026"
    assert danfse._data_hora("2026-10-08T10:15:03-03:00") == "08/10/2026 10:15:03"
    assert danfse._data_hora("2026-10-08T13:15:03Z") == "08/10/2026 13:15:03"
    assert danfse._juntar("", "") == TRACO
    assert danfse._juntar("São Paulo", "") == "São Paulo / -"
    assert danfse._limitar("x" * 50, 40) == "x" * 37 + "..."
    assert danfse._limpar("Água \U0001f600 中 ő\x01b") == "Água ? ? o b"


def test_municipios_ibge_empacotados():
    tabela = danfse._municipios()
    assert len(tabela) == 5571  # 5.570 municípios + "Águas Marítimas"
    assert tabela["3550308"] == ("São Paulo", "SP")
    assert tabela["3534401"] == ("Osasco", "SP")
    assert tabela["5300108"] == ("Brasília", "DF")
    assert danfse._uf_municipio("2100055") == "MA"  # linha sem sigla na planilha oficial
    assert danfse._uf_municipio("") == ""


def test_descricoes_cobrem_todos_os_codigos_do_xsd():
    xs = "{http://www.w3.org/2001/XMLSchema}"
    tipos = etree.parse(str(ESQUEMAS / "tiposSimples_v1.01.xsd")).getroot()

    def valores(nome: str) -> set[str]:
        tipo = tipos.find(f"{xs}simpleType[@name='{nome}']")
        return {e.get("value") for e in tipo.iter(f"{xs}enumeration")}

    pares = {
        "TSTipoAmbiente": danfse.TP_AMB,
        "TSAmbGeradorNFSe": danfse.AMB_GER,
        "TSEmitenteDPS": danfse.TP_EMIT,
        "TStat": danfse.C_STAT,
        "TSRTCFinNFSe": danfse.FIN_NFSE,
        "TSOpSimpNac": danfse.OP_SIMP_NAC,
        "TSRegimeApuracaoSimpNac": danfse.REG_AP_TRIB_SN,
        "TSRegEspTrib": danfse.REG_ESP_TRIB,
        "TSTribISSQN": danfse.TRIB_ISSQN,
        "TSTipoImunidadeISSQN": danfse.TP_IMUNIDADE,
        "TSOpExigSuspensa": danfse.TP_SUSP,
        "TSTipoRetISSQN": danfse.TP_RET_ISSQN,
        "TSTipoRetPISCofins": danfse.TP_RET_PIS_COFINS,
        "TSCodNaoNIF": danfse.C_NAO_NIF,
    }
    for tipo, mapa in pares.items():
        assert valores(tipo) <= set(mapa), tipo
    assert valores("TBMISSQN") == {"1", "2", "3", "4"}
    descricoes_bm = [danfse._descricao_bm(nota(MEI), codigo) for codigo in "1234"]
    assert descricoes_bm == ["Isenção", "Redução da BC", "Redução da BC", "Alíquota Diferenciada"]
