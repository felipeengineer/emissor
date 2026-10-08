# Emissor NFS-e · Simples Nacional

Aplicativo para emitir **NFS-e no Sistema Nacional (Padrão Nacional / Emissor Nacional, gov.br/nfse)**
voltado a empresas optantes pelo **Simples Nacional** (MEI e ME/EPP). Tem três formas de uso, todas
sobre a mesma base local (SQLite):

- **Interface web** (Flask): emissão, tomadores, consulta, DANFSe, cancelamento, configurações e calculadora do Simples.
- **MCP server integrado**: as mesmas operações como ferramentas para assistentes de IA (Claude Desktop, Claude Code etc.).
- **CLI**: `emissor web`, `emissor mcp`, `emissor status`.

## Como funciona

1. Monta o XML da **DPS** (Declaração de Prestação de Serviço) no **leiaute nacional 1.01**
   (vigente desde 01/01/2026), com o grupo `regTrib` do Simples Nacional:
   `opSimpNac` (2 = MEI, 3 = ME/EPP), `regApTribSN` e, para ME/EPP, `pTotTribSN` (alíquota efetiva do SN).
   MEI usa `indTotTrib = 0`. Optantes do SN não informam tributos federais (`tribFed`), que vão no DAS.
   A alíquota de ISS (`pAliq`) só deve ser informada quando o município de incidência **não** é conveniado
   ao Sistema Nacional; nos conveniados, o próprio sistema a preenche.
2. **Valida o XML contra os esquemas XSD oficiais** (em `emissor/schemas/1.01`) antes de enviar; a
   pré-visualização mostra o resultado dessa validação.
3. Assina a DPS (XMLDSig enveloped, RSA-SHA1, C14N) com o **certificado A1 ICP-Brasil** (.pfx).
4. Envia à **API da SEFIN Nacional** (`POST /nfse`, XML em GZip+Base64) com TLS mútuo usando o mesmo certificado.
5. Guarda a chave de acesso, o número e o XML da NFS-e; baixa o **DANFSe** (PDF) pelo ADN.
6. Cancela via evento `e101101` (`POST /nfse/{chave}/eventos`).

| Ambiente | SEFIN | ADN (DANFSe) |
|---|---|---|
| Homologação (produção restrita) — **padrão** | `sefin.producaorestrita.nfse.gov.br/SefinNacional` | `adn.producaorestrita.nfse.gov.br` |
| Produção | `sefin.nfse.gov.br/SefinNacional` | `adn.nfse.gov.br` |

## Instalação

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Os dados ficam em `~/.emissor` (altere com `EMISSOR_HOME`).

## Primeiros passos

```bash
emissor web          # http://127.0.0.1:8000
```

Em **Configurações**:

1. **Prestador**: CNPJ, código IBGE do município, situação no Simples (MEI ou ME/EPP) e forma de apuração.
   A empresa precisa estar habilitada no Emissor Nacional (o município tem de ter aderido ao convênio).
2. **Certificado A1**: envie o `.pfx` e a senha (ou use `EMISSOR_CERT_PFX` e `EMISSOR_CERT_SENHA`).
3. **Serviço padrão**: código de tributação nacional (`cTribNac`, 6 dígitos — item, subitem e desdobro da
   LC 116; ex.: `010701`), descrição e alíquota efetiva do SN. A **calculadora do Simples** estima a alíquota
   efetiva e a parcela de ISS pelos Anexos III, IV e V (com fator R) a partir da receita dos últimos 12 meses.
4. **Ambiente e numeração**: comece em homologação. Se já emitiu DPS por outro sistema, informe o último
   número usado na série para continuar a sequência.

Depois, **Nova NFS-e** → *Pré-visualizar DPS* → *Emitir NFS-e*.

## MCP server

O MCP server usa o mesmo banco e a mesma configuração da interface web.

```bash
emissor mcp                 # stdio
emissor mcp --http          # streamable HTTP em http://127.0.0.1:8001/mcp
```

**Claude Code** (`.mcp.json` no projeto ou `claude mcp add`):

```bash
claude mcp add emissor-nfse -- /caminho/para/.venv/bin/emissor mcp
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "emissor-nfse": {
      "command": "/caminho/para/.venv/bin/emissor",
      "args": ["mcp"],
      "env": { "EMISSOR_CERT_SENHA": "senha-do-certificado" }
    }
  }
}
```

Ferramentas disponíveis:

| Ferramenta | O que faz |
|---|---|
| `status_emissor` | Ambiente, prestador, certificado, próxima DPS e pendências |
| `configurar_prestador` / `configurar_parametros` | Cadastro da empresa, ambiente, série, certificado, serviço padrão |
| `calcular_aliquota_simples` | Alíquota efetiva do SN e parcela de ISS (Anexos III/IV/V, fator R) |
| `cadastrar_tomador` / `listar_tomadores` | Clientes |
| `pre_visualizar_nfse` | Gera a DPS sem assinar/enviar |
| `emitir_nfse` | Assina e envia a DPS; retorna chave e número da NFS-e |
| `listar_notas` / `obter_nota` / `resumo_faturamento` | Consultas locais |
| `consultar_nfse` / `sincronizar_nota` | Consulta na SEFIN (inclui recuperar nota após timeout) |
| `baixar_danfse` | Salva o PDF do DANFSe |
| `cancelar_nfse` | Evento de cancelamento (marcado como destrutivo) |

Exemplo de pedido ao assistente: *"Emita uma nota de R$ 1.500 para a ACME (CNPJ 11.222.333/0001-81)
pelo suporte técnico de setembro."*

## Situações das notas

- `emitida`: autorizada pela SEFIN.
- `rejeitada`: a SEFIN recusou a DPS (a mensagem traz os códigos de erro). Corrija e emita de novo; o número
  de DPS rejeitado não é reaproveitado (lacunas são permitidas no Padrão Nacional).
- `erro_comunicacao`: não houve resposta. Use *Consultar situação na SEFIN* / `sincronizar_nota` antes de reemitir,
  para não duplicar a nota.
- `cancelada`.

## Testes

```bash
pytest
```

Os testes geram um certificado autoassinado e simulam a SEFIN; nada é enviado ao governo. Todos os
cenários de DPS (ME/EPP, MEI, com e sem tomador) e o pedido de cancelamento são validados contra os XSDs
oficiais do leiaute 1.01.

## Limitações e cuidados

- **Ainda não testado contra a SEFIN real.** O XML confere com os esquemas oficiais, mas a SEFIN aplica
  regras de negócio além do esquema (cadastro do contribuinte, parametrização do município, códigos de
  tributação). Emita primeiro em homologação.
- Grupo IBS/CBS da reforma tributária (opcional no leiaute 1.01) ainda não é preenchido.
- CNPJ alfanumérico (emitido a partir de julho/2026) ainda não é aceito: o próprio esquema 1.01 da
  NFS-e Nacional exige CNPJ com 14 dígitos numéricos.
- Uma nota cancelada continua sendo devolvida pela consulta da SEFIN como autorizada; o cancelamento é
  um evento à parte. O app registra o cancelamento localmente quando o evento é aceito.
- Tomador no exterior, intermediário, deduções/reduções e substituição de NFS-e ainda não são suportados.
- A calculadora do Simples é uma estimativa; confirme o enquadramento com seu contador.
- A senha do certificado salva pela interface fica no banco local; em máquinas compartilhadas, prefira
  `EMISSOR_CERT_SENHA`.

## Licença

O código é aberto para leitura, estudo e uso não comercial sob a
[PolyForm Noncommercial License 1.0.0](LICENSE).

**Uso comercial requer licença paga: US$ 100 por assento, por ano.** Isso inclui emitir notas de
qualquer empresa ou MEI (inclusive a sua), incorporar o código em produtos ou serviços e atender
terceiros com ele. Veja os termos e como adquirir em [LICENCA-COMERCIAL.md](LICENCA-COMERCIAL.md).
