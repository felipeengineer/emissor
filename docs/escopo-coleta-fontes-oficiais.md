# Escopo de coleta: fontes oficiais da NFS-e Nacional

Escopo para um agente com acesso aberto à web (ex.: Grok) coletar nas fontes oficiais o que este
projeto não conseguiu ler (gov.br, DOU, Planalto e portal de Osasco estavam bloqueados no ambiente
de desenvolvimento). Cada pergunta tem um ID; as respostas voltam para este repositório para
corrigir o emissor.

**Como usar**

1. Copie tudo a partir de "PROMPT" e cole no Grok, em modo de pesquisa profunda (DeepSearch).
   Se ele limitar o tamanho da resposta, peça por blocos: "responda só o bloco A", depois B etc.
2. **Baixe os arquivos da Parte 1** (PDF, ZIP, XLSX) pelos links que ele devolver e coloque em
   `docs/oficial/` no repositório. O texto original dos documentos é mais confiável que qualquer
   resumo e permite conferir cada regra direto no código.
3. Salve a resposta do Grok em `docs/oficial/respostas-grok.md` e peça para o Claude aplicar.

---

## PROMPT

### Papel e objetivo

Você é um pesquisador de legislação tributária e documentação técnica fiscal brasileira. Hoje é
08/10/2026. Preciso de informações **exclusivamente das fontes oficiais** sobre a NFS-e de Padrão
Nacional (Sistema Nacional NFS-e) para corrigir um software emissor próprio. Esse software emite
NFS-e via API da SEFIN Nacional para uma ME/EPP optante pelo Simples Nacional sediada em
**Osasco/SP (código IBGE 3534401)** e precisa estar operando em **01/11/2026**, data em que o
Emissor Nacional passa a ser obrigatório para ME/EPP do Simples (Res. CGSN nº 191/2026).

### Regras obrigatórias

1. **Fontes aceitas como resposta:** gov.br/nfse, gov.br/receitafederal, in.gov.br (DOU),
   planalto.gov.br, cgibs.gov.br, www8.receita.fazenda.gov.br/SimplesNacional, Swagger/OpenAPI
   oficial da SEFIN Nacional e do ADN, nfe.osasco.sp.gov.br, osasco.sp.gov.br, sf.osasco.sp.gov.br,
   tce.sp.gov.br. Sites de fornecedores, blogs e fóruns só como **pista**, marcados `[SECUNDÁRIA]`,
   nunca como resposta final.
2. Para cada resposta informe: **URL exata, título do documento, versão, data de publicação,
   seção/página/artigo/código da regra e um trecho literal curto** (até 3 linhas).
3. Procure sempre a **versão mais recente** de cada documento. Liste também versões anteriores
   encontradas e o que mudou entre elas.
4. Se não encontrar, escreva **NÃO ENCONTRADO** e diga onde procurou. Não deduza e não complete com
   conhecimento prévio.
5. Se duas fontes oficiais divergirem, mostre as duas.
6. Responda usando o **mesmo ID** da pergunta. Nos itens com "Assumimos:", diga se a fonte oficial
   **CONFIRMA**, **DIVERGE** (e qual é o valor correto) ou se não encontrou.
7. Se o tempo ou o tamanho da resposta for limitado, siga esta ordem de prioridade:
   A1–A4, B1–B3, C1–C3, D1, E1, F1–F7, H1, G1–G2, I1–I3, J1 e depois o restante.

### Parte 1: documentos (link direto para download)

Para cada documento: link direto do arquivo (PDF/ZIP/XLSX), versão, data e se é a versão vigente.

| ID | Documento |
|---|---|
| DOC1 | Pacote de esquemas **XSD** vigente da NFS-e (DPS, NFSe, pedRegEvento, evento). Existe versão posterior à 1.01? |
| DOC2 | **Anexo I**: leiaute e **regras de validação** da DPS/NFS-e (planilha), versão vigente. Há referências a "ANEXO_I-SEFIN_ADN-DPS_NFSe-SNNFSe-v1.00-20251216" e a um "Anexo I v1.01 20260101" |
| DOC3 | Anexo/leiaute e regras de validação dos **eventos** (pedRegEvento, e101101) |
| DOC4 | **Manual Contribuintes – Emissor Público API** (v1.2 out/2025 ou posterior). URL conhecida: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-emissor-publico-api-sistema-nacional-nfs-e-v1-2-out2025.pdf |
| DOC5 | **Manual Contribuintes – APIs ADN**. URL conhecida: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-apis-adn-sistema-nacional-nfse.pdf |
| DOC6 | **Swagger/OpenAPI** oficial da SEFIN Nacional e do ADN (produção e produção restrita) |
| DOC7 | **Notas Técnicas** SE/CGNFS-e 007/2026, 008/2026 (todas as versões, incluindo a v1.02 de 14/07/2026 ou posterior, com o Anexo I do DANFSe), 009/2026 e qualquer NT posterior (010 em diante) |
| DOC8 | Tabelas do leiaute: lista nacional de serviços (cTribNac), municípios (Anexo V), NBS 2.0 (Anexo B), Anexo VI (IBSCBS), Anexo VII (cIndOp), CST e cClassTrib de IBS/CBS, correspondência CNAE x cTribNac |
| DOC9 | **Cartilha Perguntas e Respostas da NFS-e** v1.1 (22/09/2026) ou posterior. URL conhecida: https://www.gov.br/nfse/pt-br/perguntas-frequentes/perguntas-e-respostas-nfs-e-v-1-1-20260922.pdf |
| DOC10 | **Resolução CGSN nº 191/2026**, texto integral no DOU. URLs conhecidas: https://www.in.gov.br/web/dou/-/resolucao-cgsn-n-191-de-4-de-agosto-de-2026-724399487 e https://economia.df.gov.br/documents/d/seec/resol-cgsn-n-191-2026-pdf |
| DOC11 | **Ato Conjunto RFB/CGIBS nº 4/2026**. URL conhecida: https://www.cgibs.gov.br/upload/arquivos/202607/31091735-20260730-16h30-ato-conjunto-rfb-cgibs-na-c2-ba-4-260731-090909.pdf |
| DOC12 | Página oficial de **municípios aderentes** e painel de monitoramento (https://www.gov.br/nfse/pt-br/municipios-aderentes/municipios-aderentes e https://www.gov.br/nfse/pt-br/municipios/monitoramento-adesoes) |
| DOC13 | **Portal NFS-e de Osasco**: notícias, avisos, FAQ e manuais publicados desde 11/08/2026 (https://nfe.osasco.sp.gov.br/EissnfeWebApp/portal/Noticias.aspx, .../AvisosImportantes.aspx, .../Manuais.aspx, .../Sistema/FAQ/FAQ.aspx) |
| DOC14 | NT ou esquema da NFS-e Nacional que trate de **CNPJ alfanumérico**, se existir |

### Parte 2: perguntas

#### A. Obrigatoriedade e prazo (Simples Nacional)

- **A1.** Transcreva o art. 59, §§ 1º, 1º-A, 1º-B, 1º-C, 1º-D e 1º-E, e o art. 79, II, da Res. CGSN
  nº 140/2018 com a redação da Res. CGSN nº 191/2026, além dos arts. 2º e 3º da 191. Basta usar
  **um** dos canais (web **ou** API)? Um software próprio que envia a DPS à API da SEFIN Nacional
  cumpre a obrigação? O aplicativo móvel conta como canal? Qual é o "art. 12" citado no § 1º-A?
  *Assumimos: web ou API; software próprio via API cumpre.*
- **A2.** Depois de 10/08/2026 saiu alguma resolução (195/2026 ou outra) ou comunicado oficial que
  mude a data de **01/11/2026**? Verifique o DOU e as notícias da RFB e do gov.br/nfse até hoje.
- **A3.** Em 01/11/2026 todas as ME/EPP ficam **habilitadas automaticamente** nos emissores
  públicos, "independentemente da opção adotada pelo município"? Vale também para município que não
  parametrizou o convênio? Existe prazo (ex.: até 24 h) para o cadastro chegar ao ambiente nacional?
- **A4.** Transcreva as regras **E0025** (competência da DPS anterior à autorização de uso no CNC),
  **E0037**, **E0038**, **E0039** e **E0093**. Como emitir, depois de 01/11, uma nota de
  **competência até 31/10**?
- **A5.** O que acontece se a ME/EPP continuar emitindo pelo sistema municipal depois de 01/11:
  validade da nota, exclusão do Simples (Res. 140, art. 84, IV, "j"; LC 123, art. 29), multas
  (LC 123, art. 38-B; redução de 50% até 2026 e 60% a partir de 2027 pela LC 227/2026)?
- **A6.** ME/EPP pode entrar no Emissor Nacional com conta gov.br (prata/ouro) do responsável, ou
  só com certificado digital ou "primeiro acesso"? A API aceita procuração eletrônica do e-CAC?
- **A7.** Como a ME/EPP com opção **pendente** (§ 1º-A) informa `opSimpNac`? Existe um valor novo
  (NT 009)? A SEFIN confere `opSimpNac` com o cadastro do CNPJ (regra E0160)?

#### B. Osasco (IBGE 3534401)

- **B1.** Situação de Osasco na lista oficial ("Conveniado e Ativo" ou "Conveniado porém ainda não
  ativo") em **produção** e em **produção restrita**; data do termo de adesão; modalidade (emissor
  próprio com envio ao ADN, ou Emissor Nacional).
  *Assumimos: conveniado, com emissor próprio (ISS/NF-E, plataforma E-Governe) enviando ao ADN.*
- **B2.** O convênio de Osasco permite os emissores públicos para ME/EPP? Osasco usou a
  antecipação do Painel Administrativo Municipal (comunicado do gov.br/nfse de 28/09/2026)?
- **B3.** Comunicados de Osasco posteriores a **11/08/2026**: o sistema ISS/NF-E será bloqueado para
  o Simples em 01/11? Haverá consulta e emissão retroativa para competências até 31/10, e até
  quando? O que acontece com os métodos `Emitir`/`EmitirEmLote` do Web Service?
- **B4.** Decreto ou ato municipal posterior ao Decreto 14.010/2023 sobre a migração do Simples, o
  fim da importação de RPS (01/01/2027) ou IBS/CBS (IOMO de junho a outubro de 2026).
- **B5.** Osasco exige `cTribMun` ou NBS na DPS? Há alíquota de ISS parametrizada por serviço?
- **B6.** Osasco está entre os 14 municípios paulistas sem adesão do Comunicado SDG 72/2025 do
  TCE-SP (ver o anexo)?

#### C. API da SEFIN Nacional e do ADN

- **C1.** URL base exata em produção e em produção restrita. O path é `/SefinNacional` ou
  `/sefinnacional`, e o servidor diferencia maiúsculas? Há prefixo de versão?
  *Assumimos: https://sefin.nfse.gov.br/SefinNacional, https://sefin.producaorestrita.nfse.gov.br/SefinNacional,
  https://adn.nfse.gov.br e https://adn.producaorestrita.nfse.gov.br.*
- **C2.** `POST /nfse`: nome do campo JSON (`dpsXmlGZipB64`), se é GZip e depois Base64 do XML
  assinado, se o XML pode ter a declaração `<?xml ...?>`, Content-Type exigido, status HTTP de
  sucesso e campos da resposta (`chaveAcesso`, `nfseXmlGZipB64`, `idDps`, `alertas`,
  `dataHoraProcessamento`).
- **C3.** Estrutura do corpo de **erro**: chave `erro` ou `erros`, lista ou objeto, capitalização de
  `Codigo`/`Descricao`/`Complemento`, status HTTP das rejeições. Um 5xx pode significar que a nota
  foi processada?
- **C4.** `GET /dps/{id}` (existe `HEAD`?): o que retorna e o que significa 404 (não processada ou
  ainda em processamento)?
- **C5.** `GET /nfse/{chave}`: o que retorna? Como saber se a nota foi cancelada (ex.:
  `GET /nfse/{chave}/eventos`)?
- **C6.** `POST /nfse/{chave}/eventos`: nome do campo (`pedidoRegistroEventoXmlGZipB64`) e da
  resposta (`eventoXmlGZipB64`?).
- **C7.** TLS mútuo: o certificado precisa ser e-CNPJ do próprio prestador (CNPJ completo ou raiz)?
  Aceita e-CPF? Precisa enviar a cadeia? Só chaves RSA?
- **C8.** Cabeçalhos exigidos, versão mínima de TLS, limites de requisição e timeouts recomendados.
- **C9.** Existe API de **parâmetros municipais** (convênio ativo, alíquotas por serviço, serviços
  habilitados)? Paths e autenticação.
- **C10.** `tpAmb` divergente do host gera rejeição (E0006)? A produção restrita exige cadastro
  separado?

#### D. Assinatura digital

- **D1.** Algoritmo exigido: RSA-SHA1 com digest SHA-1, ou RSA-SHA256? Há data prevista para
  desativar o SHA-1? A regra é a mesma para DPS e para pedido de evento?
  *Assumimos: RSA-SHA1, digest SHA-1, PKCS#1 v1.5.*
- **D2.** Canonicalização C14N 1.0 inclusiva ou exclusiva; transforms (enveloped + C14N);
  `Reference URI="#Id"`; `Signature` como último filho de `DPS`/`pedRegEvento`; `KeyInfo` só com o
  certificado do signatário ou com a cadeia.
  *Assumimos: C14N 1.0 inclusiva, enveloped + C14N, só o certificado folha.*

#### E. Leiaute e XSD

- **E1.** Versão do leiaute aceita hoje em produção (1.00, 1.01 ou posterior)? Terceiros citam
  "1.6": é versão do leiaute ou do documento? Datas de vigência e de desativação da versão anterior.
  *Assumimos: `versao="1.01"`.*
- **E2.** Padrão oficial de `TSSerieDPS` no XSD (o arquivo que temos traz `^0{0,4}\d{1,5}$`).
- **E3.** Id da DPS: "DPS" + cLocEmi(7) + tipo de inscrição(1: 1 = CPF, 2 = CNPJ) + inscrição(14)
  + série(5) + nDPS(15) = 45 posições, com zeros à esquerda. Confirme.
- **E4.** Faixas de **série** por tipo de emissor (`procEmi`): API (00001–49999?), web
  (70000–79999?), app, transcrição. Texto da regra E0010. A série "1" é aceita via API?
- **E5.** `nDPS`: lacunas na numeração são permitidas? Pode reaproveitar o número de uma DPS
  rejeitada? Regra de duplicidade. Na migração do sistema municipal, a numeração continua ou
  reinicia?
- **E6.** Composição da chave de acesso de 50 dígitos; o Id do `infNFSe` é "NFS" + chave?
- **E7.** Com `tpEmit = 1`, `xNome` e `end` do prestador são proibidos? `IM`, `fone` e `email`
  são permitidos? A IM precisa coincidir com o cadastro municipal?
- **E8.** `dhEmi`: texto da E0008 e tolerância; limite de atraso. `dCompet`: pode ser futura?
  Qual o limite de retroatividade?

#### F. Regras de validação (texto exato e código)

- **F1.** **E0712**: ME/EPP não pode informar `indTotTrib`; é obrigatório informar `pTotTribSN`?
  Aceita `vTotTrib`/`pTotTrib`? *Assumimos: ME/EPP sempre envia `pTotTribSN`.*
- **F2.** **E0710**: MEI não pode informar `pTotTribSN`? *Assumimos: MEI envia `indTotTrib = 0`.*
- **F3.** `pTotTribSN` pode ser 0? Deve ser a alíquota efetiva do DAS ou a carga aproximada da
  Lei 12.741/2012?
- **F4.** **E0162/E0166**: `regApTribSN` obrigatório para ME/EPP e proibido para MEI? Como a SEFIN
  valida os valores 2 e 3 (sublimite)?
- **F5.** **E0160**: situação no Simples divergente do cadastro do CNPJ.
- **F6.** `pAliq` para ME/EPP: quando é proibido, opcional ou obrigatório (município conveniado,
  `regApTribSN = 1`, ISS retido, município de incidência fora do sistema)? Faixa aceita (2% a 5%)?
  *Assumimos: só é enviado se o usuário informar; em município conveniado o sistema preenche.*
- **F7.** **E0235** (tomador com CNPJ exige endereço: só endereço nacional? só quando
  `tpEmit = 1`?) e **E0240** (CEP x município do tomador).
- **F8.** `tpRetISSQN = 3` (retido pelo intermediário) exige o grupo `interm`? MEI pode ter ISS
  retido? Retenção exige `pAliq`?
- **F9.** `tribISSQN = 1`, ausência de `tribFed` e `regEspTrib = 0` são aceitos para MEI e ME/EPP?
- **F10.** O `cTribNac` precisa estar habilitado no município de incidência? `cNBS` passou a ser
  obrigatório em 2026?
- **F11.** Transcreva **todas** as regras (código + texto) que envolvem `opSimpNac`, `regApTribSN`,
  `totTrib`, `pAliq`, `toma`, `dCompet` e `serie`.

#### G. Eventos e cancelamento

- **G1.** Id do pedido de evento: "PRE" + chave(50) + tpEvento(6) = 59 posições, **sem**
  `nPedRegEvento`? *Assumimos: sim.*
- **G2.** Códigos de `cMotivo` (1, 2, 9?), tamanho de `xMotivo` (15–255?), **prazo** para cancelar
  sem análise fiscal (e101103) e impedimentos ao cancelamento.
- **G3.** `CNPJAutor` deve ser o prestador e coincidir com o certificado? Regras de `dhEvento`.

#### H. DANFSe

- **H1.** Versão vigente da NT 008. A API `GET {adn}/danfse/{chave}` está suspensa desde
  03/08/2026? Foi substituída por outro endpoint? O contribuinte passa a ser obrigado a gerar o
  DANFSe localmente?
- **H2.** Leiaute oficial do DANFSe (Anexo I da NT 008): blocos, tamanhos mínimos de fonte, QR Code
  (conteúdo e URL de consulta pública), tarjas ("NFS-e SEM VALIDADE JURÍDICA" em homologação,
  cancelada, substituída) e se saiu NT de DANFSe para IBS/CBS.

#### I. IBS/CBS (reforma tributária)

- **I1.** Ato Conjunto RFB/CGIBS nº 4/2026: o marco de 01/01/2027 vale para **todos** os optantes
  do Simples? Confirme as datas de 01/10/2026 e 01/12/2026 para os demais contribuintes.
- **I2.** Até quando a SEFIN aceita DPS sem o grupo `IBSCBS`? A partir de quando passa a rejeitar?
- **I3.** NT 009: foi implementada ou adiada? Cronograma; campos novos do Simples para IBS/CBS;
  novo valor de `opSimpNac`.
- **I4.** Campos mínimos do grupo `IBSCBS` para ME/EPP em 2027 (finNFSe, cIndOp, indDest, CST,
  cClassTrib) e tabelas oficiais.
- **I5.** NT 007: locação, cessão e arrendamento (códigos 99.xx) só podem ser autorizados pelos
  emissores públicos?
- **I6.** Res. CGSN nº 190/2026: altera as tabelas dos Anexos III, IV e V ou a partilha do ISS
  a partir de 2027?

#### J. CNPJ alfanumérico

- **J1.** Existe NT ou XSD da NFS-e Nacional que aceite CNPJ alfanumérico? Desde quando vale? Como
  ficam o Id da DPS, a chave de acesso e o dígito verificador? (O XSD 1.01 exige `[0-9]{14}`.)

#### K. Cálculo do Simples Nacional (LC 123/2006 no Planalto)

- **K1.** Confirme, para 2026, alíquotas nominais e parcelas a deduzir dos Anexos III, IV e V e o
  percentual de ISS por faixa. *Assumimos: ISS de 33,5 / 32 / 32,5 / 32,5 / 33,5 / 0 (Anexo III),
  44,5 / 40 / 40 / 40 / 40 / 0 (Anexo IV) e 14 / 17 / 19 / 21 / 23,5 / 0 (Anexo V).*
- **K2.** Teto de 5% da parcela de ISS com redistribuição do excedente; piso de 2%; limiar do
  fator R (28%); cálculo no início de atividade (art. 18, § 2º); sublimite de R$ 3,6 milhões.

#### L. MEI (contexto)

- **L1.** A LC 214/2025 alterou o art. 26 da LC 123 para obrigar o MEI a emitir NFS-e também para
  tomador pessoa física a partir de 2027? Qual dispositivo?

### Formato da resposta

Para cada ID:

```
### <ID> — <título curto>
Status: CONFIRMA | DIVERGE | NOVO | NÃO ENCONTRADO
Resposta: ...
Fonte: <título>, <versão>, <data>, <URL>, <seção/página/artigo/código da regra>
Trecho: "<citação literal>"
Observações: ...
```

Ao final, inclua:

1. Tabela DOC1–DOC14 com link direto, versão, data e se é a vigente.
2. Lista de **mudanças publicadas desde 01/01/2026** que afetam quem emite via API (NTs, novas
   versões de XSD, regras de validação novas ou alteradas, endpoints suspensos).
3. Lista do que **não foi possível verificar**, com o motivo.
