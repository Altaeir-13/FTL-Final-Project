# Comparação dos catálogos Sentinel-2 e decisão de aquisição

Diagnóstico executado em 11/11/2026 com os mesmos polígonos ANA dos cinco pivôs
8087, 16708, 17373, 17382 e 19997. SHA-256 do GeoJSON:
`b7da39ab1b08f1ee7280b6fefe976685b699b9e09b43c0364852679f50991878`.
As buscas usam a união completa das geometrias (`intersects`), sem filtro global
de nuvens, com paginação verificada e limite conservador de 500 produtos por
consulta. Janeiro representa uma amostra da estação chuvosa e julho uma amostra
da estação seca; essa escolha serve para auditar a fonte antes da expansão.

## Resultado efetivamente consultado

| Catálogo/coleção | Janeiro/2022: produtos / aquisições | Julho/2022: produtos / aquisições | Bandas e formato declarados |
|---|---:|---:|---|
| Earth Search `sentinel-2-c1-l2a` | 0 / 0 | 0 / 0 | Sem itens nesses dois meses e polígonos |
| Earth Search `sentinel-2-l2a` | 6 / 6 | 6 / 6 | `red`, `nir` (B08), `swir16`, `scl`: COG; alternativas JP2 |
| Planetary Computer `sentinel-2-l2a` | 6 / 6 | 9 / 6 | `B04`, `B08`, `B11`, `SCL`: COG |
| Copernicus Data Space `sentinel-2-l2a` | 6 / 6 | 6 / 6 | `B04_10m`, `B08_10m`, `B11_20m`, `SCL_20m`: JP2 em S3 |

Datas comuns aos três catálogos alternativos:

- Janeiro: 04, 09, 14, 19, 24 e 29.
- Julho: 03, 08, 13, 18, 23 e 28.

Todos os itens retornados pelos catálogos alternativos possuem os quatro ativos
obrigatórios e footprints que cobrem integralmente os cinco polígonos. Trata-se
de disponibilidade declarada no catálogo; a qualidade local exige leitura SCL e
a integridade/radiometria dos ativos exige auditoria própria. Os nove produtos
de julho no Planetary Computer correspondem a seis aquisições: há versões de
processamento distintas para 08, 13 e 28/07. Contar os nove como nove observações
independentes produziria duplicatas.

O identificador de aquisição deriva do nome SAFE: plataforma, instante de
aquisição, órbita relativa e tile, excluindo baseline e data de geração. Não se
usa igualdade exata do campo STAC `datetime` entre provedores: Earth Search
descreve o horário do granule e os outros catálogos podem usar o horário do
datatake, diferindo em vários minutos na mesma aquisição.

O tile é 23KKA, CRS projetado EPSG:32723, grades declaradas de 10 m para B04/B08 e
20 m para B11/SCL. O footprint do CDSE varia aproximadamente entre longitudes
−47,836 e −46,788 e latitudes −18,169 e −17,165; a seleção real usa polígonos, não
esse retângulo aproximado.

## Interpretação da lacuna e requisitos de acesso

A ausência de itens na coleção C1 consultada em janeiro/julho não representa
ausência de passagem Sentinel-2. Os três catálogos alternativos confirmam seis
aquisições em cada mês. Esse resultado identifica uma lacuna de disponibilidade
no catálogo/coleção escolhido para o histórico original; não permite afirmar a
causa interna da ingestão da Element 84.

Earth Search permite consulta STAC e leitura HTTPS anônimas. O Planetary
Computer permite consulta anônima e fornece assinatura SAS temporária pública
de leitura para os COGs Azure. A assinatura permanece somente em memória; URLs
assinadas não devem entrar em manifestos, logs ou Git. O CDSE respondeu às duas
consultas STAC públicas sem autenticação. Seus ativos declarados são JP2 em
`s3://eodata`; a leitura S3 exige cadastro gratuito e credenciais CDSE. Nenhuma
conta foi criada e nenhum ativo CDSE foi baixado neste diagnóstico. As duas
respostas CDSE transferiram 820.606 bytes em dois POSTs. A comparação reaproveitou
os seis snapshots locais anteriores dos outros catálogos.

O catálogo legado declara PB 03.01/04.00 em janeiro e 04.00 em julho. O Planetary
Computer declara PB 03.00/04.00 em janeiro e 04.00/05.10 em julho. O CDSE fornece
PB 05.10 nesses dois meses. A PB diferente implica potencial reprocessamento,
portanto uma correspondência de aquisição não garante igualdade dos pixels.
No legado, há ativos que declaram `offset=-0.1` mesmo com
`earthsearch:boa_offset_applied=true`; também existe relato público de flag
inconsistente. Esses metadados, isoladamente, não autorizam uma transformação
radiométrica genérica. A aprovação de um adaptador exige metadados nativos do
produto e comparação efetiva dos recortes, registrada no relatório de
recuperação.

## Artefatos e reprodução do diagnóstico

`data/recovery/diagnostic/catalogs/<provedor>/<mês>.json` preserva o snapshot
completo e `<mês>-page-*.json` preserva as respostas originais. O inventário
`data/recovery/diagnostic/http.jsonl` contém origem, bytes e SHA-256. O resumo
`data/recovery/diagnostic/catalog_comparison.json` preserva datas, contagens de
produtos e aquisições, cobertura por pivô, ativos, URLs, grades, baseline,
flags e hashes dos snapshots.

O módulo `aquaclima.ingestion.catalog_diagnostic` fornece
`run_catalog_diagnostic(http, pivots_path, output_dir, offline=False)`.
O padrão consulta apenas janeiro e julho de 2022. Snapshots existentes são
imutáveis, verificados pelo inventário e comparados à configuração solicitada.
`offline=True` impede aquisição de snapshots ausentes e registra a ausência;
falhas de um provedor não ocultam os resultados dos demais.

```powershell
@'
from pathlib import Path
from aquaclima.ingestion.catalog_diagnostic import run_catalog_diagnostic
from aquaclima.storage.http import HttpClient

root = Path("data/recovery/diagnostic")
with HttpClient(ledger=root / "http.jsonl", max_transfer_bytes=20_000_000,
                max_storage_bytes=20_000_000, max_downloads=100) as http:
    print(run_catalog_diagnostic(http, Path("data/processed/pivots.geojson"),
                                 root, offline=True))
    print(http.transferred, http.downloads)
'@ | uv run --no-sync python -
```

Reprodução executada: oito resultados `ok`, zero requests e zero bytes.
Testes específicos executados: nove aprovados, incluindo versões de uma mesma
aquisição, ativo ausente, cobertura parcial, duplicatas, período/coleção
incorretos, truncamento, paginação fora do domínio e integridade offline.

## Fontes primárias consultadas

- [Earth Search: API e coleções](https://github.com/Element84/earth-search).
- [Relato de inconsistências radiométricas no legado, issue 71](https://github.com/Element84/earth-search/issues/71).
- [Planetary Computer: assinaturas SAS](https://planetarycomputer.microsoft.com/docs/concepts/sas/).
- [CDSE: STAC público](https://documentation.dataspace.copernicus.eu/APIs/STAC.html).
- [CDSE: acesso S3 e credenciais](https://documentation.dataspace.copernicus.eu/APIs/S3.html).

As consultas reais acima, seus metadados e a auditoria dos pixels locais são a
evidência operacional. A existência de uma issue não substitui a validação do
produto efetivamente utilizado.
