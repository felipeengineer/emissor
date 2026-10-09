# Esquemas XSD da NFS-e Nacional — leiaute 1.01

Cópia **sem alterações** do pacote oficial `esquemas-nfse-rtc-v1-01-20260727.zip`, publicado no
gov.br/nfse para a produção restrita em 28/07/2026 (evolução do CNPJ alfanumérico, em produção desde
10/08/2026 segundo a página "Atualizações e Implantações"). Usado para validar localmente a DPS e o
pedido de registro de evento antes do envio à SEFIN.

Em relação ao pacote de 09/02/2026 (`nfse-esquemas_xsd-v1-01-20260209.zip`), só mudam
`tiposSimples_v1.01.xsd` e o DOCTYPE do `xmldsig-core-schema.xsd`:

- `TSCNPJ` aceita CNPJ alfanumérico (`[0-9A-Z]{14}`); os Ids da DPS, da NFS-e e do pedido de evento
  aceitam letras na inscrição federal.
- `TSSerieDPS` passa a `[0-9]{1,4}|[0-8][0-9]{4}` (até 89999). O padrão antigo (`^0{0,4}\d{1,5}$`)
  não funcionava no libxml2, que trata `^` e `$` como caracteres literais.
- Campos de texto (`TSDesc*`) passam a rejeitar valores só com espaços.

Limitação conhecida do pacote oficial: `TSChaveNFSe` (`[0-9]{6}([0-9A-Z]{14})[0-9]{30}`) só aceita
letras nas posições 7–20 da chave, enquanto `TSIdNFSe` e `TSIdPedRegEvt` as colocam nas posições
10–23. Um cancelamento de nota de prestador com CNPJ alfanumérico pode falhar na validação local.

Pacote ZIP — sha256 `6c7e0510d3ecff4454f291f4e10b742d27a4818f23aab181494f96d0ea79f3dc`

| Arquivo | sha256 |
|---|---|
| DPS_v1.01.xsd | `c7dab363d8cf7c83fc2b3b21e72cf669a51bd30947a5690685ea96c4b3e39dcd` |
| pedRegEvento_v1.01.xsd | `186c83f33752a195845300af61ffbe7136547f84cab032b35238c78f9d78f7c6` |
| tiposComplexos_v1.01.xsd | `6f792f408a33c11e799042a8d61cac7d1c9f5992c53e07e60ce75a15f157d1ac` |
| tiposEventos_v1.01.xsd | `6c9ae744b1cb886607c1138c32eeb76cd410b856ce7301197b95d48d63f7b40b` |
| tiposSimples_v1.01.xsd | `3d8171c9b7c9a82ecb48eed9a96485f2077006e7d21db6cd182839dd34dbb5e4` |
| xmldsig-core-schema.xsd | `bf43998b2df1fedd9ed7d6914f91ab4d34958e8730c3b500cbe0b21e60335f11` |

Os esquemas são documentação técnica pública do Sistema Nacional NFS-e e não estão cobertos pela
licença deste projeto.
