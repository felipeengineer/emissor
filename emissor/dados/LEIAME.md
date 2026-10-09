# Tabelas de dados

## `municipios_ibge.csv`

Tabela de municípios do IBGE usada pelo DANFSe (NT 008 v1.02) para converter os códigos `cMun`,
`cLocPrestacao`, `cLocIncid` e `cLocalidadeIncid` em nome e sigla da UF. Colunas: `codigo;nome;uf`
(UTF-8, separador `;`, ordenada pelo código).

Origem: aba `TAB.MUN_IBGE` do anexo oficial `anexo_a-municipio_ibge-paises_iso2-v1-00-snnfse-20251210.xlsx`
(gov.br/nfse, documentação técnica), sha256 `238b715ab2dcc2c9e0857c44d69048e0af806b45ec8499568342de4a37f4419d`.

Transformações feitas na geração (nenhum nome foi alterado):

- 5.570 municípios. Em 5.120 linhas a planilha não traz a sigla da UF; ela foi deduzida dos dois
  primeiros dígitos do código IBGE (código da UF). Onde a planilha traz a sigla, ela confere com o prefixo.
- Espaços repetidos no nome foram reduzidos a um.
- Acrescentada a localidade geral `0000000;Águas Marítimas;` (aba `TAB.LOC.GERAL`), sem UF.

sha256 do CSV gerado: `a5d16f753bba3ce5309a138292c4739848838180c239428540c52900fe7197cd`
