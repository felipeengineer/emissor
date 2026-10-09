# Escopo de coleta: fontes oficiais da NFS-e Nacional

Escopo para um agente com acesso aberto à web (ex.: Grok) coletar nas fontes oficiais o que este
projeto não conseguiu ler: gov.br, DOU, Planalto e o portal de Osasco estavam bloqueados no
ambiente de desenvolvimento. Cada pergunta tem um ID; as respostas voltam para este repositório
para corrigir o emissor.

**Como usar**

1. Copie tudo a partir de "PROMPT" e cole no Grok em modo de pesquisa profunda (DeepSearch).
   Se ele limitar o tamanho da resposta, peça por blocos, nesta ordem: "responda só o bloco DOC",
   depois A, B, C, D, X, F, G, H, I, J, K, L, M.
2. **Baixe os arquivos do bloco DOC** (PDF, ZIP, XLSX) pelos links que ele devolver e coloque em
   `docs/oficial/` no repositório. O texto original dos documentos é mais confiável que qualquer
   resumo e permite conferir cada regra direto no código.
3. Salve a resposta do Grok em `docs/oficial/respostas-grok.md` e peça ao Claude para aplicar.

---

## PROMPT

### Papel e objetivo

Você é um pesquisador de legislação tributária e de documentação técnica fiscal brasileira. Hoje é
08/10/2026. Preciso de informações **das fontes oficiais** sobre a NFS-e de Padrão Nacional
(Sistema Nacional NFS-e) para corrigir um software emissor próprio. O software emite NFS-e pela API
da SEFIN Nacional para uma ME/EPP optante pelo Simples Nacional sediada em **Osasco/SP (código
IBGE 3534401)** e precisa estar operando em **01/11/2026**. Nessa data, segundo a Res. CGSN
nº 191/2026, a ME/EPP do Simples passa a emitir obrigatoriamente pelo Emissor Nacional.

### Regras obrigatórias

1. **Fontes aceitas como resposta:** sites de órgãos federais em gov.br (inclusive gov.br/nfse,
   gov.br/receitafederal, gov.br/fazenda e gov.br/pt-br/servicos); todos os hosts `*.nfse.gov.br`
   (SEFIN, ADN, Swagger, Painel); in.gov.br (DOU); planalto.gov.br; camara.leg.br e normas.leg.br;
   cgibs.gov.br; www8.receita.fazenda.gov.br/SimplesNacional; a cópia oficial da SEEC-DF em
   economia.df.gov.br; portais e diários oficiais de prefeituras (incluindo nfe.osasco.sp.gov.br,
   osasco.sp.gov.br e sf.osasco.sp.gov.br); tce.sp.gov.br. Sites de fornecedores, blogs e fóruns
   servem só como **pista**, marcados `[SECUNDÁRIA]`, nunca como resposta final.
2. Para cada resposta informe: **URL exata, título do documento, versão, data de publicação,
   seção/página/artigo/código da regra e um trecho literal curto** (até 3 linhas).
3. Procure sempre a **versão mais recente**. Para DOC1, DOC2, DOC4, DOC7 e DOC9, liste também as
   versões anteriores encontradas e o que mudou entre elas.
4. Se não encontrar, use o status **NÃO ENCONTRADO** e diga onde procurou. Não deduza e não
   complete com conhecimento prévio. Se a fonte só existir atrás de login, diga isso.
5. Se duas fontes oficiais divergirem, mostre as duas.
6. **Status de cada resposta:**
   - `CONFIRMA`: a fonte oficial confirma o "Assumimos".
   - `DIVERGE`: a fonte oficial contradiz o "Assumimos". Informe o valor correto.
   - `RESPONDIDO`: pergunta sem "Assumimos", respondida com fonte oficial.
   - `PARCIAL`: só parte foi respondida. Diga o que faltou.
   - `NOVO`: informação relevante que não foi perguntada.
   - `NÃO ENCONTRADO`.
7. **Códigos de regra (E0xxx):** os códigos citados aqui vieram de fontes secundárias e podem
   estar errados. Para cada um, informe o **código oficial da regra descrita** e o **texto oficial
   do código citado**. Se não coincidirem, use `DIVERGE`.
8. Perguntas que se sobrepõem: responda uma vez no ID principal e, nos demais, escreva
   "Ver <ID>".
9. **Ordem de prioridade**, se o tempo ou o tamanho da resposta for limitado:
   DOC1, DOC2, DOC4, DOC6, DOC9 → A1–A4, A7, A8 → B1–B3 → C1–C3, C6, C11 → D1–D2 → X1, X3, X4 →
   F1–F7, F12 → G1 → H1 → I1–I3, I7 → J1–J2 → restante.

### Bloco DOC: documentos (link direto para download)

Para cada documento: link direto do arquivo (PDF/ZIP/XLSX), versão, data e se é a versão vigente.

- **DOC1.** Pacote de esquemas **XSD** vigente da NFS-e (DPS, NFSe, pedRegEvento, evento). Informe
  o nome exato do ZIP, a data, a lista de arquivos (com tamanho ou hash, se a página mostrar), se
  existe versão posterior à 1.01 e se o pacote 1.01 foi republicado com o mesmo nome e conteúdo
  diferente.
- **DOC2.** **Anexo I**: leiaute e **regras de validação** da DPS/NFS-e (planilha), versão
  vigente. Há referências a "ANEXO_I-SEFIN_ADN-DPS_NFSe-SNNFSe-v1.00-20251216" e a um "Anexo I
  v1.01 20260101".
- **DOC3.** Leiaute e regras de validação dos **eventos** (pedRegEvento, e101101).
- **DOC4.** **Manual Contribuintes – Emissor Público API** (v1.2 out/2025 ou posterior). URL
  conhecida:
  `https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-emissor-publico-api-sistema-nacional-nfs-e-v1-2-out2025.pdf`
- **DOC5.** **Manual Contribuintes – APIs ADN**. URL conhecida:
  `https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-apis-adn-sistema-nacional-nfse.pdf`
- **DOC6.** **Swagger/OpenAPI** oficial da SEFIN Nacional e do ADN, em produção e em produção
  restrita. Caminhos a verificar: `/API/SefinNacional/docs/` (relatado por fornecedores, host a
  confirmar), o equivalente em `sefin.producaorestrita.nfse.gov.br`,
  `https://adn.nfse.gov.br/danfse/docs/index.html` e um possível
  `www.producaorestrita.nfse.gov.br/swagger/...`. Informe também se existe um "Anexo II –
  Manual/Guia das APIs" separado do Manual de Contribuintes.
- **DOC7.** **Notas Técnicas** SE/CGNFS-e. Versões conhecidas: NT 007/2026 v1.0 (07/02/2026);
  NT 008/2026 v1.0 (05/05/2026), v1.01 (30/06/2026) e v1.02 (14/07/2026), com o Anexo I do DANFSe;
  NT 009/2026 v1.0 (04/06/2026). Existe versão mais nova de alguma delas? Existe NT 010 ou
  posterior?
- **DOC8.** Tabelas do leiaute: lista nacional de serviços (aba MUN.INCID_INFO.SERV do Anexo I,
  cTribNac), municípios (Anexo V), NBS 2.0 (Anexo B), Anexo VI (IBSCBS; assumimos v1.03.00),
  Anexo VII (cIndOp; assumimos v1.01.00), CST e cClassTrib de IBS/CBS e a correspondência
  CNAE x cTribNac da RFB.
- **DOC9.** **Cartilha Perguntas e Respostas da NFS-e** v1.1 (22/09/2026) ou posterior. URL
  conhecida:
  `https://www.gov.br/nfse/pt-br/perguntas-frequentes/perguntas-e-respostas-nfs-e-v-1-1-20260922.pdf`
- **DOC10.** **Resolução CGSN nº 191/2026**, texto integral. URLs conhecidas:
  `https://www.in.gov.br/web/dou/-/resolucao-cgsn-n-191-de-4-de-agosto-de-2026-724399487` e
  `https://economia.df.gov.br/documents/d/seec/resol-cgsn-n-191-2026-pdf`
- **DOC11.** **Ato Conjunto RFB/CGIBS nº 4/2026**. URL conhecida:
  `https://www.cgibs.gov.br/upload/arquivos/202607/31091735-20260730-16h30-ato-conjunto-rfb-cgibs-na-c2-ba-4-260731-090909.pdf`
- **DOC12.** Lista oficial de **municípios aderentes** e painel de monitoramento:
  `https://www.gov.br/nfse/pt-br/municipios-aderentes/municipios-aderentes` e
  `https://www.gov.br/nfse/pt-br/municipios/monitoramento-adesoes`
- **DOC13.** **Portal NFS-e de Osasco**: notícias, avisos, FAQ, manuais e legislação publicados
  desde 11/08/2026.
  - `https://nfe.osasco.sp.gov.br/EissnfeWebApp/portal/Noticias.aspx`
  - `https://nfe.osasco.sp.gov.br/EissnfeWebApp/portal/AvisosImportantes.aspx`
  - `https://nfe.osasco.sp.gov.br/EissnfeWebApp/portal/Manuais.aspx`
  - `https://nfe.osasco.sp.gov.br/EissnfeWebApp/portal/Legislacao.aspx`
  - `https://nfe.osasco.sp.gov.br/EissnfeWebApp/Sistema/FAQ/FAQ.aspx`
  - `https://homolog-nfe.osasco.sp.gov.br/EissnfeWebApp/Portal/Noticias.aspx`
  - `https://sf.osasco.sp.gov.br/pages/noticias`
- **DOC14.** NT ou esquema da NFS-e Nacional sobre **CNPJ alfanumérico**, se existir.

### A. Obrigatoriedade e prazo (Simples Nacional)

Pontos de partida:
`https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/agosto/simples-nacional-nfs-e-nacional-sera-obrigatoria-para-me-e-epp-a-partir-de-1o-de-novembro-de-2026`,
`https://www.gov.br/nfse/pt-br/noticias/comite-gestor-do-simples-nacional-prorroga-a-obrigatoriedade-de-emissao-de-notas-fiscais-de-servico-pelo-emissor-nacional-da-nfs-e`,
`https://www.gov.br/nfse/pt-br/noticias`.

- **A1.** Transcreva o art. 59, §§ 1º, 1º-A, 1º-B, 1º-C, 1º-D e 1º-E, e o art. 79, II, da Res. CGSN
  nº 140/2018 com a redação da Res. CGSN nº 191/2026, além dos arts. 2º e 3º da 191. Basta usar
  **um** dos canais (web **ou** API)? Um software próprio que envia a DPS à API da SEFIN Nacional
  cumpre a obrigação? O aplicativo móvel conta como canal? Qual é o "art. 12" citado no § 1º-A?
  Assumimos: web ou API; software próprio via API cumpre.
- **A2.** Depois de 10/08/2026 saiu alguma resolução (195/2026 ou outra) ou comunicado oficial que
  mude a data de **01/11/2026**? Verifique o DOU e as notícias da RFB e do gov.br/nfse até hoje.
- **A3.** Em 01/11/2026 todas as ME/EPP ficam **habilitadas automaticamente** nos emissores
  públicos? Fontes secundárias atribuem à RFB a frase "independentemente da opção adotada pelo
  município"; localize a fonte oficial literal ou responda NÃO ENCONTRADO. Vale também para
  município que não parametrizou o convênio? Existe prazo (ex.: até 24 h) para o cadastro chegar
  ao ambiente nacional?
- **A4.** Transcreva as regras abaixo e diga se o código corresponde à descrição. Como emitir,
  depois de 01/11, uma nota de **competência até 31/10**?
  - E0025: competência da DPS anterior à data de autorização de uso dos emissores no CNC.
  - E0037: município emissor sem cadastro no convênio.
  - E0038: convênio do município não ATIVO.
  - E0039: município não parametrizado para os emissores públicos (exceto MEI).
  - E0093: município optou por emissor próprio.
- **A5.** O que acontece se a ME/EPP continuar emitindo pelo sistema municipal depois de 01/11:
  validade da nota, exclusão do Simples (Res. 140, art. 84, IV, "j"; LC 123, art. 29, XI e § 9º),
  multas (LC 123, art. 38-B)? Transcreva também o art. 26, I e § 4º, da LC 123: o município pode
  exigir outra obrigação acessória, como emitir também no sistema municipal?
  Assumimos: redução das multas acessórias de 50% até 2026 e de 60% a partir de 2027
  (LC 227/2026, art. 169).
- **A6.** A ME/EPP pode entrar no Emissor Nacional com a conta gov.br (prata/ouro) do responsável,
  ou só com certificado digital ou "primeiro acesso"? A API aceita procuração eletrônica do e-CAC?
  Ponto de partida: `https://www.gov.br/pt-br/servicos/emitir-nota-fiscal-de-servico-eletronica`
- **A7.** Como a ME/EPP com opção **pendente** (§ 1º-A) informa `opSimpNac`? Existe um valor novo
  (NT 009)? A SEFIN confere `opSimpNac` com o cadastro do CNPJ? Qual o código dessa regra?
  Assumimos: E0160.
- **A8.** Na Cartilha Perguntas e Respostas v1.1 (DOC9), ou em versão posterior:
  - (a) Transcreva a pergunta 5.3: coexistência entre o sistema próprio do município e o Emissor
    Nacional, controlada contribuinte a contribuinte pela "Autorização de Uso dos Emissores
    Públicos" no CNC.
  - (b) Existe vedação de emitir pelo sistema municipal e pelo Emissor Nacional/API **na mesma
    competência**? Transcreva o trecho ou responda NÃO ENCONTRADO.
  - (c) O que a cartilha diz sobre notas de competência outubro emitidas em novembro?
  - (d) Ela manda redirecionar à API nacional as integrações (web services) feitas com a
    prefeitura?
  - (e) Compare com a v1.00:
    `https://www.gov.br/nfse/pt-br/biblioteca/perguntas-e-respostas/perguntas-e-respostas-da-nfs-e/perguntas-e-respostas-nfse-v1-00-20260908.pdf`
- **A9.** Res. CGSN nº 189/2026 (revogada): em que data foi publicada no DOU (23 ou 28/04/2026)? O
  § 1º-A original falava só em discussão "administrativa", e a palavra "judicial" foi incluída
  pela 191?

### B. Osasco (IBGE 3534401) e outros municípios

- **B1.** Situação de Osasco na lista oficial (DOC12), se "Conveniado e Ativo" ou "Conveniado
  porém ainda não ativo"; data do termo de adesão; modalidade (emissor próprio com envio ao ADN, ou
  Emissor Nacional). Informe também a situação em **produção restrita**. Se só houver o Painel
  Nacional com login (`https://www.producaorestrita.nfse.gov.br/PainelNacional/Login`), responda
  NÃO ENCONTRADO para essa parte.
  Assumimos: conveniado, com emissor próprio (ISS/NF-E, plataforma E-Governe) enviando ao ADN.
- **B2.** O convênio de Osasco permite os emissores públicos para ME/EPP? Osasco usou a
  antecipação do Painel Administrativo Municipal? Ponto de partida:
  `https://www.gov.br/nfse/pt-br/noticias/nova-funcionalidade-no-painel-administrativo-municipal-permite-antecipar-a-adocao-do-emissor-nacional-para-optantes-pelo-simples-nacional`
- **B3.** Comunicados de Osasco posteriores a **11/08/2026** (DOC13):
  - O sistema ISS/NF-E será bloqueado para o Simples em 01/11?
  - Haverá consulta e emissão retroativa para competências até 31/10, e até quando?
  - O que acontece com os métodos `Emitir` e `EmitirEmLote` do Web Service?
  - Osasco orienta sobre série e numeração na migração para o Emissor Nacional (série nova ou
    continuar a numeração do RPS/NFS-e municipal)?
- **B4.** Existe decreto ou ato municipal posterior ao Decreto 14.010/2023 sobre a migração do
  Simples, o fim da importação de RPS (01/01/2027) ou IBS/CBS? Procure no IOMO de junho a outubro
  de 2026; o último indexado foi `https://osasco.sp.gov.br/wp-content/uploads/2026/05/iomo-3009.pdf`.
  O prazo de conversão do RPS (até o dia 5 do mês seguinte) mudou? Que penalidades a LC 404/2022
  (Código Tributário de Osasco) prevê para emissão irregular?
- **B5.** Osasco exige `cTribMun` ou NBS na DPS? Há alíquota de ISS parametrizada por serviço?
- **B6.** Osasco está entre os 14 municípios paulistas sem adesão do Comunicado SDG 72/2025 do
  TCE-SP? Veja o anexo:
  `https://tce.sp.gov.br/legislacao/comunicado/comunicado-sdg-722025`
- **B7.** (Contexto, baixa prioridade.) Data e regra de transição em: SP capital (IN SF/SUREM
  7/2026; Resolução CGNFS-e nº 9 de 30/12/2025), São José dos Campos, Juiz de Fora (Decreto
  17.913/2026), Barueri, Paracambi (Decreto 6.388/2026), Ipatinga, Rio de Janeiro, São José do Rio
  Preto, Natal e Severínia.
- **B8.** Para quem continua no sistema de Osasco (não optantes): os métodos `RTC_EmitirNFE` são
  obrigatórios desde 01/07/2026? O sistema rejeita nota sem IBS/CBS? Quem é o fornecedor da
  plataforma E-Governe? Há plano de migrar os não optantes?

### C. API da SEFIN Nacional e do ADN

- **C1.** URL base exata em produção e em produção restrita. O path é `/SefinNacional` ou
  `/sefinnacional`, e o servidor diferencia maiúsculas? Há prefixo de versão?
  Assumimos:
  - `https://sefin.nfse.gov.br/SefinNacional`
  - `https://sefin.producaorestrita.nfse.gov.br/SefinNacional`
  - `https://adn.nfse.gov.br`
  - `https://adn.producaorestrita.nfse.gov.br`
- **C2.** `POST /nfse`:
  - Nome do campo JSON (`dpsXmlGZipB64`) e se o conteúdo é GZip e depois Base64 do XML assinado.
  - O XML pode ter a declaração `<?xml ...?>`? Qual Content-Type é exigido?
  - Status HTTP de sucesso (200 ou 201?).
  - Campos da resposta: `chaveAcesso`, `nfseXmlGZipB64`, `idDps`, `alertas`,
    `dataHoraProcessamento`, `tipoAmbiente`, `versaoAplicativo`. Qual a estrutura de cada item de
    `alertas`?
- **C3.** Estrutura do corpo de **erro**: chave `erro` ou `erros`, lista ou objeto, capitalização
  de `Codigo`/`Descricao`/`Complemento`, status HTTP das rejeições (400? 422?). Um 5xx pode
  significar que a nota foi processada?
- **C4.** `GET /dps/{id}` (existe `HEAD`?): o que retorna, se o campo da chave se chama
  `chaveAcesso`, e o que significa 404 (não processada ou ainda em processamento)? Quem pode
  consultar?
- **C5.** `GET /nfse/{chave}`: o que retorna e quem pode consultar (só o emitente, ou também o
  tomador e o intermediário)? Como saber se a nota foi cancelada (ex.:
  `GET /nfse/{chave}/eventos`)?
- **C6.** `POST /nfse/{chave}/eventos`:
  - Nome do campo da requisição (`pedidoRegistroEventoXmlGZipB64`?).
  - Status HTTP de sucesso. Um 2xx garante que o evento foi registrado, ou o processamento pode
    ser assíncrono?
  - Campos da resposta (`eventoXmlGZipB64`?).
  - A chave na URL precisa coincidir com o `chNFSe` do XML? Se sim, qual o código da regra?
  - O erro segue o formato do C3?
- **C7.** TLS mútuo: o certificado precisa ser e-CNPJ do próprio prestador (CNPJ completo ou
  raiz)? Aceita e-CPF? Precisa enviar a cadeia? Só chaves RSA? O certificado do TLS precisa ser o
  mesmo da assinatura? Quais são o código e o texto das rejeições por titularidade divergente?
- **C8.** Cabeçalhos exigidos (Content-Type, Accept), versão mínima de TLS, limites de requisição
  e timeouts recomendados.
- **C9.** Existe API de **parâmetros municipais** (convênio ativo, alíquotas por serviço, serviços
  habilitados)? Informe paths e autenticação.
- **C10.** `tpAmb` divergente do host gera rejeição? Assumimos: E0006. A documentação chama o
  `tpAmb = 2` de "produção restrita" ou "homologação" (é o mesmo ambiente)?
- **C11.** Para usar a API em **produção**, o contribuinte ou o software precisa de
  credenciamento, cadastro ou habilitação prévia (no CNC, no Painel Nacional ou no gov.br), além
  do certificado? A produção restrita tem cadastro próprio?
- **C12.** Existe página oficial de status do Sistema Nacional? A documentação prevê respostas
  502, 503 ou 504 com corpo HTML e diz como o cliente deve agir?
- **C13.** O MEI pode emitir pela API? Prestador pessoa física (CPF) com `opSimpNac` 2 ou 3 é
  rejeitado? Qual o código da regra?

### D. Assinatura digital

- **D1.** Algoritmo exigido: RSA-SHA1 com digest SHA-1, ou RSA-SHA256? Há data prevista para
  desativar o SHA-1? A regra é a mesma para DPS e para pedido de evento?
  Assumimos: RSA-SHA1, digest SHA-1, PKCS#1 v1.5.
- **D2.** Canonicalização C14N 1.0 inclusiva ou exclusiva; transforms (enveloped + C14N);
  `Reference URI="#Id"`; `Signature` como último filho de `DPS` e de `pedRegEvento`; `KeyInfo` só
  com o certificado do signatário ou com a cadeia. Comentários e espaços em branco são tolerados?
  Assumimos: C14N 1.0 inclusiva, enveloped + C14N, `KeyInfo` só com o certificado folha.

### X. Leiaute e XSD

(Bloco chamado "X" para não confundir com os códigos de regra E0xxx.)

- **X1.** Versão do leiaute aceita hoje em produção (1.00, 1.01 ou posterior). Terceiros citam
  "1.6": é versão do leiaute ou do documento? Datas de vigência e de desativação da versão
  anterior. O atributo `versao` do `pedRegEvento` precisa ser igual ao da DPS? O tipo `TVerNFSe`
  continua `1\.00|1\.01`? Que `versao` vem no XML da NFS-e devolvida pela SEFIN?
  Assumimos: `versao="1.01"`.
- **X2.** Transcreva o padrão literal de `TSSerieDPS` no XSD **oficial**, dizendo se tem `^` e
  `$`. (A cópia de terceiros que usamos traz `^0{0,4}\d{1,5}$`.)
- **X3.** Id da DPS. Assumimos: 45 posições, todas com zeros à esquerda, assim:
  - "DPS"
  - código do município (7 posições; assumimos que é o `cLocEmi`)
  - tipo de inscrição (1 posição; 1 = CPF, 2 = CNPJ)
  - inscrição federal (14 posições)
  - série (5 posições)
  - nDPS (15 posições)

  Confirme e informe o código da regra que valida o Id (assumimos E0004).
- **X4.** Faixas de **série** por tipo de emissor (`procEmi`): API (assumimos 00001–49999), web
  (assumimos 70000–79999), app, transcrição. Texto da regra de série fora da faixa (assumimos
  E0010). A série "1" é aceita via API?
- **X5.** `nDPS`: lacunas na numeração são permitidas? Pode reaproveitar o número de uma DPS
  rejeitada? Qual a regra de duplicidade? Na migração do sistema municipal, a numeração continua ou
  reinicia?
- **X6.** Chave de acesso. Assumimos 50 posições:
  - código do município (7)
  - ambiente gerador (1)
  - tipo de inscrição (1)
  - inscrição (14)
  - nNFSe (13)
  - AAMM (4)
  - código numérico (9)
  - DV (1)

  Confirme, informe o algoritmo do DV e diga se o Id do `infNFSe` é "NFS" + chave.
- **X7.** Com `tpEmit = 1`, `xNome` e `end` do prestador são proibidos? `IM`, `fone` e `email`
  são permitidos? A IM precisa coincidir com o cadastro municipal?
- **X8.** `dhEmi`: texto da regra de data posterior ao processamento (assumimos E0008),
  tolerância, limite de atraso, se exige offset -03:00. `dCompet`: é a competência ou a data de
  início da prestação? Pode ser futura? Qual o limite de retroatividade e o código da regra?
- **X9.** Formato e limite de `verAplic` (até 20 caracteres?). O XML deve ser UTF-8 sem BOM? Há
  limites de negócio, além do XSD, para `fone` (6 a 20), `email` (80), `IM` (15) e `xDescServ`
  (2000)?

### F. Regras de validação (texto exato e código oficial)

Lembre da regra 7: confirme se o número de cada código bate com a descrição.

- **F1.** ME/EPP não pode informar `indTotTrib` e deve informar `pTotTribSN`? Aceita `vTotTrib`
  ou `pTotTrib`? Assumimos: regra E0712; ME/EPP sempre envia `pTotTribSN`.
- **F2.** MEI não pode informar `pTotTribSN`? Assumimos: regra E0710; MEI envia
  `indTotTrib = 0`.
- **F3.** `pTotTribSN` pode ser 0? Deve ser a alíquota efetiva do DAS ou a carga aproximada da
  Lei 12.741/2012? Qual a precisão e o valor máximo? A SEFIN compara com a RBT12 ou com a faixa?
- **F4.** `regApTribSN` é obrigatório para ME/EPP e proibido para MEI? Como a SEFIN valida os
  valores 2 e 3 (sublimite)? Assumimos: regras E0162 e E0166.
- **F5.** Ver A7.
- **F6.** `pAliq` para ME/EPP: quando é proibido, opcional ou obrigatório (município conveniado,
  `regApTribSN = 1`, ISS retido, início de atividade, município de incidência fora do sistema)?
  Deve ser a alíquota de ISS do Simples (LC 123, art. 21, § 4º)? Qual a faixa aceita (2% a 5%)?
  Existe hoje rejeição por "município de incidência sem convênio"?
  Assumimos: só é enviado se o usuário informar; em município conveniado o sistema preenche.
- **F7.** Tomador com CNPJ exige endereço: só endereço nacional? Só quando `tpEmit = 1`? Vale
  também para tomador CPF? Assumimos: regra E0235. CEP do tomador x município: assumimos regra
  E0240.
- **F8.** `tpRetISSQN = 3` (retido pelo intermediário) exige o grupo `interm`? MEI pode ter ISS
  retido? Retenção exige `pAliq`?
- **F9.** `tribISSQN = 1`, ausência de `tribFed` e `regEspTrib = 0` são aceitos para MEI e
  ME/EPP? Há regra cruzando `regEspTrib` com `opSimpNac`? A reforma passou a exigir CST de
  PIS/COFINS do optante?
- **F10.** O `cTribNac` precisa estar habilitado no município de incidência? `cTribMun` tem
  3 dígitos? `cNBS` passou a ser obrigatório em 2026? Qual a versão vigente da tabela NBS?
- **F11.** Transcreva **todas** as regras (código e texto) sobre: `opSimpNac`, `regApTribSN`,
  `regEspTrib`, `totTrib`, `pAliq`, `tribISSQN`, `tribFed`/`piscofins`, `tpRetISSQN`/`interm`,
  `toma`, `prest` (com `tpEmit`), `cServ`, `dhEmi`, `dCompet`, `serie`, `nDPS`/Id e `tpAmb`.
- **F12.** Para cada código a seguir, informe o texto oficial e se ele corresponde à descrição que
  usamos. Se não corresponder, informe o código correto da regra descrita.

  | Código | Descrição que usamos |
  |---|---|
  | E0004 | Id da DPS |
  | E0006 | `tpAmb` x host |
  | E0008 | `dhEmi` posterior ao processamento |
  | E0010 | série fora da faixa |
  | E0160 | situação no Simples |
  | E0162 / E0166 | `regApTribSN` |
  | E0235 | endereço do tomador |
  | E0240 | CEP x município |
  | E0710 | `pTotTribSN` no MEI |
  | E0712 | `totTrib` na ME/EPP |

### G. Eventos e cancelamento

- **G1.** Id do pedido de evento. Assumimos: "PRE" + chave (50) + tpEvento (6) = 59 posições,
  **sem** `nPedRegEvento`.
- **G2.** Códigos de `cMotivo` (assumimos 1, 2 e 9); tamanho de `xMotivo` (assumimos 15–255);
  **prazo** para cancelar sem análise fiscal (evento e101103?); impedimentos ao cancelamento.
- **G3.** `CNPJAutor` deve ser o prestador e coincidir com o certificado? Regras de `dhEvento`. O
  `tpAmb` do pedido precisa coincidir com o da NFS-e? Qual o código da regra?

### H. DANFSe

Pontos de partida:
`https://www.gov.br/nfse/pt-br/noticias/danfse-novos-ajustes-de-leiaute-e-prorrogacao-do-prazo-para-adequacao`,
`https://adn.nfse.gov.br/danfse/docs/index.html`.

- **H1.** Versão vigente da NT 008 e o que mudou entre as versões v1.0, v1.01 e v1.02. A API
  `GET {adn}/danfse/{chave}` está suspensa ("sobrestada") desde 03/08/2026? Por qual ato? Foi
  substituída por outro endpoint? O contribuinte passa a ser obrigado a gerar o DANFSe localmente?
- **H2.** Leiaute oficial do DANFSe (Anexo I da NT 008):
  - Número de blocos (13?), tamanho e orientação da página, margens, tamanhos mínimos de fonte.
  - QR Code: conteúdo e URL de consulta pública.
  - Regras de logotipo e se exige PDF/A.
  - Tarjas: "NFS-e SEM VALIDADE JURÍDICA" em homologação, cancelada, substituída.
  - As linhas de PIS/COFINS aparecem só para competência até dez/2026?
  - Saiu NT de DANFSe para IBS/CBS?

### I. IBS/CBS (reforma tributária)

Pontos de partida:
`https://cgibs.gov.br/receita-federal-e-comite-gestor-do-ibs-publicam-o-cronograma-de-implementacao-dos-documentos-fiscais-eletronicos`,
`https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/julho/receita-federal-e-comite-gestor-do-ibs-publicam-o-cronograma-de-implementacao-dos-documentos-fiscais-eletronicos-da-reforma-tributaria-do-consumo`.

- **I1.** Transcreva o art. 1º, § 1º, do Ato Conjunto RFB/CGIBS nº 4/2026 (DOC11): o marco de
  01/01/2027 vale para **todos** os optantes do Simples ou só para quem optar pelo regime regular?
  Confirme as datas de 03/08, 01/10 e 01/12/2026 para os demais contribuintes e o enquadramento dos
  subitens 1.03, 1.05, 1.09 e 16.01. Confirme a publicação (DOU nº 143, Seção 1, p. 25), o
  programa de conformidade de até 30 dias e a relação com o Ato Conjunto RFB/CGIBS nº 1/2025.
- **I2.** Até quando a SEFIN aceita DPS sem o grupo `IBSCBS`, e a partir de quando passa a
  rejeitar? Responda separadamente para DPS com `opSimpNac = 3` (ME/EPP) e para não optantes.
- **I3.** NT 009: foi implementada ou adiada? Qual o cronograma? Quais os campos novos do Simples
  para IBS/CBS, o novo valor de `opSimpNac` e os campos de locação, cessão e arrendamento?
- **I4.** Campos mínimos do grupo `IBSCBS` para ME/EPP em 2027 (finNFSe, cIndOp, indDest, CST,
  cClassTrib) e tabelas oficiais. Os campos mudam se o optante recolher IBS/CBS no DAS ou optar
  pelo regime regular (Res. CGSN 194/2026)? Quais são obrigatórios para o MEI?
- **I5.** NT 007: locação, cessão e arrendamento (códigos 99.xx) só podem ser autorizados pelos
  emissores públicos? Para que serve o campo `indZFMALC`? Os códigos 1 e 2 de `tpRetPisCofins`
  serão suprimidos, e quando?
- **I6.** Res. CGSN nº 190/2026: altera as tabelas dos Anexos III, IV e V ou a partilha do ISS a
  partir de 2027? Renumera ou altera os arts. 59, 79, 84 e 106-A da Res. 140? Ponto de partida:
  `https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/agosto/cgsn-atualiza-regras-do-simples-nacional-para-adequacao-a-reforma-tributaria-do-consumo`
- **I7.** Existe o "Ato Técnico Conjunto CGIBS/RFB nº 1"? Informe número, data e URL. A orientação
  da CGNFS-e sobre os prazos de destaque de IBS/CBS garante a não rejeição até 31/12/2026? A URL
  que temos parece malformada (contém `%20`); informe a correta:
  `https://www.gov.br/nfse/pt-br/noticias/cgnfs-e-orienta-sobre-os-prazos-para%20destaque-de-ibs-cbs-nas-notas-fiscais-de-servico`
- **I8.** Res. CGSN nº 194/2026 (DOU, edição extra de 28/09/2026): confirme as datas. Assumimos:
  opção pelo Simples para 2027 até 15/10/2026, opção pelo regime regular de IBS/CBS até
  30/10/2026 e cancelamento entre 03/11 e 20/12/2026. Ela trata de NFS-e?

### J. CNPJ alfanumérico

- **J1.** Existe NT ou XSD da NFS-e Nacional que aceite CNPJ alfanumérico? Desde quando vale? O
  XSD 1.01 exige `[0-9]{14}`.
- **J2.** Desde que data a RFB atribui CNPJ alfanumérico a novos inscritos (IN RFB nº 2.229/2024
  ou norma posterior)? Transcreva o dispositivo. Qual o algoritmo oficial do DV e em que documento
  ele está? Hoje a SEFIN aceita DPS com **tomador** de CNPJ alfanumérico? E com **prestador**?
  Como ficam o Id da DPS, a chave de acesso e o `CNPJAutor` do evento?

### K. Cálculo do Simples Nacional

Fonte: LC 123/2006 no Planalto (`https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm`).

- **K1.** Confirme, para 2026, as alíquotas nominais e parcelas a deduzir dos Anexos III, IV e V e
  o percentual de ISS por faixa. Assumimos estes percentuais de ISS, da 1ª à 6ª faixa:
  - Anexo III: 33,5 / 32 / 32,5 / 32,5 / 33,5 / 0
  - Anexo IV: 44,5 / 40 / 40 / 40 / 40 / 0
  - Anexo V: 14 / 17 / 19 / 21 / 23,5 / 0
- **K2.** Confirme: teto de 5% para a parcela de ISS, com redistribuição do excedente; piso de 2%;
  limiar do fator R (28%); cálculo no início de atividade (art. 18, § 2º); sublimite de R$ 3,6
  milhões.

### L. MEI e contexto legal

- **L1.** A LC 214/2025 alterou o art. 26 da LC 123 para obrigar o MEI a emitir NFS-e também para
  tomador pessoa física a partir de 2027? Qual dispositivo?
- **L2.** Transcreva o art. 62 da LC 214/2025 (caput e §§ 1º a 7º) no texto compilado do Planalto
  (`https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm`), indicando as notas "Redação
  dada/Incluído pela LC 227/2026". O § 2º (até 31/12/2032) limita o § 1º inteiro? A sanção do § 7º
  recai só sobre o ente? O que diz o art. 52 da LC 214, citado pela Fenacon como base da
  obrigação do Simples?
- **L3.** Precedente do MEI:
  - Datas e publicação no DOU das Res. CGSN 169/2022, 171/2022 e 172/2023.
  - Transcreva o art. 106-A da Res. 140.
  - Hoje o MEI emite pelos emissores públicos independentemente do convênio do município?
  - A NT SE/CGNFS-e 2023.001 foi atualizada?
    (`https://www.gov.br/nfse/pt-br/nt-2023-001-obrigatoriedade-da-nfs-e-nacional-para-o-mei.pdf`)

### M. Contexto nacional (baixa prioridade)

- **M1.** Número oficial atual (set/out 2026) de municípios ativos e divisão entre emissor próprio
  e Emissor Nacional. Alguma transferência voluntária foi suspensa por falta de adesão? O sistema
  próprio do município deve enviar ao ADN imediatamente ou "ao menos diariamente"? Ponto de
  partida:
  `https://www.gov.br/nfse/pt-br/municipios/como-conveniar-se/protocolo-de-adesao-do-municipio-a-nfs-e.pdf`

### Formato da resposta

Para cada ID:

```
### <ID> — <título curto>
Status: CONFIRMA | DIVERGE | RESPONDIDO | PARCIAL | NOVO | NÃO ENCONTRADO
Resposta: ...
Fonte: <título>, <versão>, <data>, <URL>, <seção/página/artigo/código da regra>
Trecho: "<citação literal>"
Observações: ...
```

Ao final, inclua:

1. Tabela DOC1–DOC14 com link direto, versão, data e se é a vigente.
2. Lista de **mudanças publicadas desde 01/01/2026** que afetam quem emite pela API (NTs, novas
   versões de XSD, regras de validação novas ou alteradas, endpoints suspensos).
3. Lista do que **não foi possível verificar**, com o motivo.
