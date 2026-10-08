"""Cálculo da alíquota efetiva do Simples Nacional para serviços (Anexos III, IV e V da LC 123/2006,
redação da LC 155/2016) e da parcela de ISS correspondente.

É uma estimativa para preencher a DPS (pTotTribSN e pAliq). Confira com o seu contador: fator R,
sublimites estaduais e atividades específicas podem alterar o enquadramento.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# (limite superior da faixa de RBT12, alíquota nominal %, parcela a deduzir R$, % do ISS dentro do DAS)
TABELAS: dict[str, list[tuple[Decimal, Decimal, Decimal, Decimal]]] = {
    "III": [
        (Decimal("180000"), Decimal("6.00"), Decimal("0"), Decimal("33.5")),
        (Decimal("360000"), Decimal("11.20"), Decimal("9360"), Decimal("32.0")),
        (Decimal("720000"), Decimal("13.50"), Decimal("17640"), Decimal("32.5")),
        (Decimal("1800000"), Decimal("16.00"), Decimal("35640"), Decimal("32.5")),
        (Decimal("3600000"), Decimal("21.00"), Decimal("125640"), Decimal("33.5")),
        (Decimal("4800000"), Decimal("33.00"), Decimal("648000"), Decimal("0")),
    ],
    "IV": [
        (Decimal("180000"), Decimal("4.50"), Decimal("0"), Decimal("44.5")),
        (Decimal("360000"), Decimal("9.00"), Decimal("8100"), Decimal("40.0")),
        (Decimal("720000"), Decimal("10.20"), Decimal("12420"), Decimal("40.0")),
        (Decimal("1800000"), Decimal("14.00"), Decimal("39780"), Decimal("40.0")),
        (Decimal("3600000"), Decimal("22.00"), Decimal("183780"), Decimal("40.0")),
        (Decimal("4800000"), Decimal("33.00"), Decimal("828000"), Decimal("0")),
    ],
    "V": [
        (Decimal("180000"), Decimal("15.50"), Decimal("0"), Decimal("14.0")),
        (Decimal("360000"), Decimal("18.00"), Decimal("4500"), Decimal("17.0")),
        (Decimal("720000"), Decimal("19.50"), Decimal("9900"), Decimal("19.0")),
        (Decimal("1800000"), Decimal("20.50"), Decimal("17100"), Decimal("21.0")),
        (Decimal("3600000"), Decimal("23.00"), Decimal("62100"), Decimal("23.5")),
        (Decimal("4800000"), Decimal("30.50"), Decimal("540000"), Decimal("0")),
    ],
}

ISS_MINIMO = Decimal("2.00")
ISS_MAXIMO = Decimal("5.00")


def _q(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def anexo_por_fator_r(folha_12_meses, rbt12) -> str:
    """Atividades sujeitas ao fator R: Anexo III se folha/RBT12 >= 28%, senão Anexo V."""
    rbt12 = Decimal(str(rbt12))
    if rbt12 <= 0:
        return "III"
    return "III" if Decimal(str(folha_12_meses)) / rbt12 >= Decimal("0.28") else "V"


def calcular_aliquotas(rbt12, anexo: str = "III") -> dict:
    """Retorna alíquota efetiva total e a parcela de ISS para a receita bruta dos últimos 12 meses."""
    anexo = anexo.upper().strip()
    if anexo not in TABELAS:
        raise ValueError("anexo deve ser III, IV ou V")
    rbt12 = Decimal(str(rbt12))
    if rbt12 < 0:
        raise ValueError("RBT12 não pode ser negativa")
    if rbt12 > TABELAS[anexo][-1][0]:
        raise ValueError("RBT12 acima do limite do Simples Nacional (R$ 4,8 milhões)")

    faixa_idx = next(i for i, f in enumerate(TABELAS[anexo]) if rbt12 <= f[0])
    _, nominal, deduzir, perc_iss = TABELAS[anexo][faixa_idx]

    if rbt12 == 0:  # empresa em início de atividade: aplica-se a alíquota nominal da 1ª faixa
        efetiva = nominal
    else:
        efetiva = (rbt12 * nominal / 100 - deduzir) / rbt12 * 100

    iss = efetiva * perc_iss / 100
    observacao = ""
    if faixa_idx == 5:
        iss = Decimal("0")
        observacao = "6ª faixa: ISS é recolhido fora do DAS, diretamente ao município."
    elif iss > ISS_MAXIMO:
        # Excedente de ISS acima de 5% é redistribuído aos tributos federais; a efetiva total não muda.
        iss = ISS_MAXIMO
        observacao = "Parcela de ISS limitada a 5%; o excedente é transferido aos tributos federais."
    elif iss < ISS_MINIMO:
        observacao = (
            "Parcela de ISS abaixo de 2%: alguns municípios exigem 2% como mínimo; confirme com o contador."
        )

    return {
        "anexo": anexo,
        "faixa": faixa_idx + 1,
        "rbt12": str(_q(rbt12)),
        "aliquota_nominal": str(nominal),
        "parcela_deduzir": str(_q(deduzir)),
        "aliquota_efetiva": str(_q(efetiva)),
        "aliquota_iss": str(_q(iss)),
        "observacao": observacao,
    }
