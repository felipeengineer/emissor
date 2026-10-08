# Esquemas XSD da NFS-e Nacional — leiaute 1.01

Esquemas oficiais do Sistema Nacional NFS-e (pacote de esquemas v1.01, vigente desde 01/01/2026),
usados para validar localmente a DPS e o pedido de registro de evento antes do envio à SEFIN.

Cópia obtida de <https://github.com/mendesalexandre/php-nfse-nacional> (`docs/schemas/1.01`), que
redistribui os arquivos publicados em gov.br/nfse. Confira com o pacote oficial ao atualizar.

Os esquemas são documentação técnica pública do Sistema Nacional NFS-e e não estão cobertos pela
licença deste projeto.

Única alteração: em `tiposSimples_v1.01.xsd`, o padrão de `TSSerieDPS` passou de
`^0{0,4}\d{1,5}$` para `0{0,4}\d{1,5}`. Em expressões regulares de XSD `^` e `$` não são âncoras
(a ancoragem é implícita), e o libxml2 os trata como caracteres literais, o que rejeitaria
qualquer série. O significado pretendido pelo esquema oficial é o mesmo.
