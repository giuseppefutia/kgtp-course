# Vocabularies

Both vocabularies are copied into the repository rather than downloaded when the
notebook runs, so everyone works on the same file. The sha256 checksum
identifies the exact copy.

## `pc/public-contracts.ttl` — Public Contracts Ontology

- Source: [opendatacz/public-contracts-ontology](https://github.com/opendatacz/public-contracts-ontology),
  commit `3d4eda1bdb4713e2c7721f25bbef760103a4ea67`
- sha256: `265ed5a1145669fb9713d0f15aed089866cbcf85da71e6ada8dee0bf666804fa`
- Licence: [CC BY 3.0 CZ](http://creativecommons.org/licenses/by/3.0/cz/).
  Authors: Jakub Klímek, Jindřich Mynarz, Martin Nečaský,
  Josef Petrák, Vojtěch Svátek and others.

The code lists that `pc:kind`, `pc:procedureType`, `pc:authorityKind` and
`pc:mainActivity` point to are not published in that repository. To use those
properties, you have to supply your own values.

## `gr/goodrelations.owl` — GoodRelations

- Source: <http://purl.org/goodrelations/v1.owl>, V 1.0, release 2011-10-01,
  downloaded on 2026-09-29
- sha256: `4eeecc843408390fc16d69a291cb2ba5454fb124eaedef24a9618f6dd40c1f9e`
- Licence: [CC BY 3.0](http://creativecommons.org/licenses/by/3.0/).
  This work is based on the GoodRelations ontology, developed by Martin Hepp:
  <http://purl.org/goodrelations/>.

The Public Contracts Ontology needs GoodRelations: the range of
`pc:contractingAuthority` and `pc:bidder` is `gr:BusinessEntity`.
