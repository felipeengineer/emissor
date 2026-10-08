# Conferência com os documentos oficiais (08/10/2026)

Resultado da comparação do emissor com o pacote de documentos oficiais coletado pelo usuário
(gov.br/nfse, DOU, Planalto, Prefeitura de Osasco). Cada mudança no código foi conferida por um
segundo leitor na fonte citada. A resposta do Grok foi usada só como pista e checada contra os
documentos.

## Fontes principais

| Documento | Versão |
|---|---|
| Esquemas XSD `esquemas-nfse-rtc-v1-01-20260727` (produção restrita, CNPJ alfanumérico) | 27/07/2026 |
| Esquemas XSD `nfse-esquemas_xsd-v1-01-20260209` | 09/02/2026 |
| Anexo I – leiaute e regras da DPS/NFS-e (produção e produção restrita) | v1.01, 09/02/2026 |
| Anexo II – pedido de registro de evento | v1.01, 22/01/2026 |
| Manual Contribuintes – Emissor Público API / APIs ADN | v1.2 out/2025 / v1.0 fev/2026 |
| NT 008 (DANFSe) | v1.02, 14/07/2026 |
| NT 009 (reforma tributária, novos campos do Simples) | v1.01, 11/09/2026 |
| NT 007, NT 010 | v1.0 |
| Cartilha Perguntas e Respostas da NFS-e | v1.1, 22/09/2026 |
| Res. CGSN 191/2026 (DOU 10/08/2026), Ato Conjunto RFB/CGIBS 4/2026 | — |
| Lista de municípios aderentes | 28/09/2026 |
| Portal NFS-e de Osasco (avisos até 01/10/2026) | — |

## Mudanças aplicadas no código

| Tema | Antes | Agora | Fonte |
|---|---|---|---|
| `pAliq` (ME/EPP) | enviado sempre que preenchido | só com ISS retido (mín. 1,80%); com ISS fora do DAS, só em município não conveniado | Anexo I, E0595, E0600, E0621, E0625, E0628, E0631, E0635, E0640 |
| `pTotTribSN` | alíquota efetiva | alíquota **nominal** da faixa | Cartilha 20.5 |
| Retenção de ISS | aceita para MEI e pelo intermediário | MEI proibido; intermediário bloqueado; retenção exige endereço do tomador | E0583, E0264/E0293, E0237 |
| Série | 1 a 5 dígitos | 1 a 49999 (faixa da API) | Anexo I, E0010; Cartilha 18.2 |
| CNPJ alfanumérico | rejeitado | aceito (prestador, tomador, Ids, chave) com DV ASCII−48 | NT 009 §2.1; Atualizações (produção 10/08/2026); XSD 27/07/2026 |
| XSD local | 09/02/2026 com padrão de série ajustado | pacote oficial 27/07/2026 sem alterações | — |
| Certificado | só validade | documento do certificado deve ser idêntico ao do prestador | E0718; Cartilha 17.2 |
| Competência de outubro emitida em novembro | sem aviso | recusada em produção antes da data de autorização (configurável) | E0025; Cartilha 5.3 |
| DANFSe | baixado do ADN | gerado localmente | NT 008 v1.02; Atualizações 03/08/2026; Cartilha 17.8 |
| Cancelamento/substituição feitos fora do app | não detectados | consulta `GET /nfse/{chave}/eventos` | Manual API v1.2 |
| Timeout no cancelamento | erro | reconciliado pela consulta de eventos | Anexo II (evento único, E0840) |
| URL da produção restrita | `/SefinNacional` | `/API/SefinNacional` (configurável) | página gov.br citada no levantamento; não está nos manuais |
| Rejeições na migração | só o código | mensagem com orientação (E0025, E0039, E0084, E0718…) | Anexo I; Cartilha |

## Confirmado sem mudança

- Endpoints `POST /nfse`, `GET /nfse/{chave}`, `GET /dps/{id}`, `POST /nfse/{chave}/eventos`; processamento
  síncrono; DPS compactada em Base64, UTF-8, sem prefixo de namespace.
- Id da DPS (45 posições) e do pedido de evento ("PRE" + chave + 101101, sem `nPedRegEvento`).
- Grupo `e101101`: `xDesc` "Cancelamento de NFS-e", motivos 1/2/9, justificativa de 15 a 255 caracteres.
- Ordem dos campos, `tpAmb` = 2 para produção restrita, MEI pode usar a API com certificado.
- ME/EPP acessa o Emissor Nacional com certificado ou "primeiro acesso" (gov.br só para MEI).

## Pontos em aberto

- **Credenciamento para API** no Portal do Contribuinte: citado só pela página gov.br do serviço
  (23/02/2026); os manuais não explicam o procedimento.
- **Osasco**: lista oficial de 28/09/2026 com "AderenteEmissorNacional = Não"; sem comunicado sobre
  bloqueio do sistema municipal, emissão retroativa ou numeração após 01/11.
- **Nomes dos campos JSON** da API (`dpsXmlGZipB64`, `pedidoRegistroEventoXmlGZipB64`, resposta e erros):
  só no Swagger, que não foi baixado. Confirmar no primeiro teste em produção restrita.
- **IBS/CBS**: obrigatório para o Simples a partir de 01/01/2027; a estrutura da NT 009 ainda não tem XSD
  publicado. Implementar quando houver.
- **Optante pendente** (`opSimpNac = 4`): previsto na NT 009 e na Res. CGSN 191, sem XSD publicado.
- **Algoritmo de assinatura**: os documentos exigem só "XML Digital Signature"; o RSA-SHA1 segue a
  biblioteca de referência validada em homologação.
