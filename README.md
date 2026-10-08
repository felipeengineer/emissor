# Emissor NFS-e · Simples Nacional

Aplicativo para emitir **NFS-e no Sistema Nacional (Padrão Nacional / Emissor Nacional, gov.br/nfse)**
voltado a empresas optantes pelo **Simples Nacional** (MEI e ME/EPP). Tem três formas de uso, todas
sobre a mesma base local (SQLite):

- **Interface web** (Flask): emissão, tomadores, consulta, DANFSe, cancelamento, configurações e calculadora do Simples.
- **MCP server integrado**: as mesmas operações como ferramentas para assistentes de IA (Claude Desktop, Claude Code etc.).
- **CLI**: `emissor web`, `emissor mcp`, `emissor status`.

## Como funciona

As regras abaixo foram conferidas nos documentos oficiais (Anexo I v1.01, Anexo II, NT 008 v1.02, NT 009,
Cartilha de Perguntas e Respostas v1.1, Res. CGSN 191/2026). Os códigos de rejeição citados são do Anexo I.

1. Monta o XML da **DPS** no **leiaute nacional 1.01**, com o grupo `regTrib` do Simples Nacional:
   `opSimpNac` (2 = MEI, 3 = ME/EPP) e `regApTribSN` (só ME/EPP). Optantes do SN não informam tributos
   federais (`tribFed`), que vão no DAS.
   - **Tributos aproximados:** ME/EPP envia `pTotTribSN` com a **alíquota nominal** da faixa do Simples
     (Cartilha 20.5; `indTotTrib` é proibido, E0712). MEI envia `indTotTrib = 0` (E0710).
   - **Alíquota do ISS (`pAliq`):** para ME/EPP com ISS no DAS, vai **só quando o ISS é retido** pelo tomador,
     com mínimo de 1,80% (E0621/E0625). Com ISS fora do DAS (sublimite), só em município não conveniado
     (E0635/E0640). MEI nunca envia (E0600).
   - **Retenção:** MEI não pode ter ISS retido (E0583); retenção exige tomador com endereço (E0204/E0237);
     retenção pelo intermediário não é suportada (E0264).
   - **Série:** de 1 a 49999, a faixa da API (E0010).
   - **CNPJ alfanumérico:** aceito para prestador e tomador (em produção desde 10/08/2026).
2. **Valida o XML contra os esquemas XSD oficiais** (pacote de 27/07/2026, em `emissor/schemas/1.01`) antes
   de enviar; a pré-visualização mostra o resultado.
3. Confere se o **certificado A1** é do próprio prestador (E0718) e assina a DPS (XMLDSig enveloped,
   RSA-SHA1, C14N).
4. Envia à **API da SEFIN Nacional** (`POST /nfse`, XML em GZip+Base64) com TLS mútuo.
5. Guarda a chave de acesso, o número e o XML da NFS-e e **gera o DANFSe localmente** (PDF da NT 008 v1.02):
   a API de DANFSe do ADN foi desativada em 03/08/2026. O documento fiscal é o XML.
6. Cancela via evento `e101101` (`POST /nfse/{chave}/eventos`) e consulta os eventos da nota
   (`GET /nfse/{chave}/eventos`) para detectar cancelamentos ou substituições feitos fora do app.

| Ambiente | SEFIN (URL base) |
|---|---|
| Homologação (produção restrita) — **padrão** | `https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional` |
| Produção | `https://sefin.nfse.gov.br/SefinNacional` |

A URL da produção restrita (com `/API/`) não está nos manuais baixados; veio da página gov.br de APIs
citada no levantamento. Se o primeiro teste der 404, ajuste com `EMISSOR_SEFIN_URL_HOMOLOGACAO`
(ou `EMISSOR_SEFIN_URL_PRODUCAO`).

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
2. **Certificado A1**: o e-CNPJ **da própria empresa** (o do contador ou de filial é rejeitado, E0718).
   Envie o `.pfx` e a senha (ou use `EMISSOR_CERT_PFX` e `EMISSOR_CERT_SENHA`).
3. **Serviço padrão**: código de tributação nacional (`cTribNac`, 6 dígitos; ex.: `010701`), descrição e a
   **alíquota nominal do Simples** da sua faixa. A **calculadora** mostra a nominal (para `pTotTribSN`), a
   efetiva e a parcela de ISS (Anexos III, IV e V, com fator R).
4. **Ambiente e numeração**: comece em homologação. Série entre 1 e 49999. Se já emitiu DPS por outro
   sistema, informe o último número usado. Em produção, informe a **data de autorização do Emissor
   Nacional** (primeira competência aceita; padrão para ME/EPP: 01/11/2026). Notas de competência anterior
   devem sair pelo sistema da prefeitura (E0025; a Cartilha 5.3 proíbe os dois sistemas na mesma competência).

### Checklist da migração (ME/EPP, prazo 01/11/2026)

- Credenciar o uso da API no **Portal do Contribuinte** (exigido pela página gov.br do serviço) e fazer o
  primeiro acesso também na produção restrita.
- Testar uma emissão e um cancelamento em **homologação** antes de 01/11 (Osasco liberou testes do Simples
  em produção restrita em 01/10/2026).
- Até 31/10, emitir pelo sistema da prefeitura as notas com competência de outubro.
- Em Osasco, a lista oficial de 28/09/2026 mostra "AderenteEmissorNacional = Não": antes de 01/11 a emissão
  em produção tende a ser rejeitada (E0039). A ferramenta `consultar_convenio_municipio` consulta a situação.

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
| `calcular_aliquota_simples` | Alíquota nominal (para `pTotTribSN`), efetiva e parcela de ISS (Anexos III/IV/V, fator R) |
| `cadastrar_tomador` / `listar_tomadores` | Clientes |
| `pre_visualizar_nfse` | Gera a DPS sem assinar/enviar |
| `emitir_nfse` | Assina e envia a DPS; retorna chave e número da NFS-e |
| `listar_notas` / `obter_nota` / `resumo_faturamento` | Consultas locais |
| `consultar_nfse` / `sincronizar_nota` | Consulta na SEFIN: recupera nota após timeout e detecta cancelamento/substituição |
| `baixar_danfse` | Gera o PDF do DANFSe localmente e devolve o link da Consulta Pública |
| `consultar_convenio_municipio` | Parâmetros do convênio do município na SEFIN |
| `cancelar_nfse` | Evento de cancelamento (marcado como destrutivo) |

Exemplo de pedido ao assistente: *"Emita uma nota de R$ 1.500 para a ACME (CNPJ 11.222.333/0001-81)
pelo suporte técnico de setembro."*

## Situações das notas

- `emitida`: autorizada pela SEFIN.
- `rejeitada`: a SEFIN recusou a DPS (a mensagem traz os códigos de erro). Corrija e emita de novo; o número
  de DPS rejeitado não é reaproveitado (lacunas são permitidas no Padrão Nacional).
- `erro_comunicacao`: não houve resposta. Use *Consultar situação na SEFIN* / `sincronizar_nota` antes de reemitir,
  para não duplicar a nota.
- `cancelada` / `substituida`: inclusive quando feito fora do app (detectado ao atualizar a situação).

## Testes

```bash
pytest
```

Os testes geram um certificado autoassinado e simulam a SEFIN; nada é enviado ao governo. Todos os
cenários de DPS (ME/EPP, MEI, com e sem tomador) e o pedido de cancelamento são validados contra os XSDs
oficiais do leiaute 1.01.

## Limitações e cuidados

- **Ainda não testado contra a SEFIN real.** O XML confere com os esquemas oficiais e com as regras do
  Anexo I implementadas, mas a URL da produção restrita e os nomes dos campos JSON da API só serão
  confirmados no primeiro teste (os manuais baixados não os trazem).
- **IBS/CBS:** o grupo `IBSCBS` ainda não é gerado. Para optantes do Simples ele passa a ser obrigatório em
  01/01/2027 (Ato Conjunto RFB/CGIBS 4/2026); a NT 009 muda a estrutura e ainda não está em produção.
- **Optante pendente** (`opSimpNac = 4`, NT 009) ainda não é aceito por nenhum XSD publicado.
- Intermediário, tomador no exterior, deduções, substituição de NFS-e e solicitação de análise fiscal de
  cancelamento (e101103) ainda não são suportados.
- O DANFSe usa Helvetica no lugar de Arial/Microsoft Sans Serif e um logotipo em texto.
- A calculadora do Simples é uma estimativa; confirme o enquadramento com seu contador.
- A senha do certificado salva pela interface fica no banco local; em máquinas compartilhadas, prefira
  `EMISSOR_CERT_SENHA`.

## Licença

O código é aberto para leitura, estudo e uso não comercial sob a
[PolyForm Noncommercial License 1.0.0](LICENSE).

**Uso comercial requer licença paga: US$ 100 por assento, por ano.** Isso inclui emitir notas de
qualquer empresa ou MEI (inclusive a sua), incorporar o código em produtos ou serviços e atender
terceiros com ele. Veja os termos e como adquirir em [LICENCA-COMERCIAL.md](LICENCA-COMERCIAL.md).
