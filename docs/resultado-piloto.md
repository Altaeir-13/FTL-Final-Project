# Resultado da aquisição piloto

Execução em 10 de novembro de 2026, no Windows, com Python 3.12.13 e processamento em CPU. A unidade de dados tinha 206.140.018.688 bytes livres antes das aquisições. O repositório oficial foi clonado sem branches remotas com commits, tags ou arquivos versionados.

## Observações obtidas

Foram aceitas **15 observações**, correspondentes a cinco pivôs e três datas, sem lacunas na junção mensal neste recorte. Todos os pares pivô–cena tiveram 100% de pixels válidos pela máscara conjunta. O valor descreve a amostra selecionada e a política de qualidade, com limiar de 70%, e não estima a cobertura anual. A seleção geográfica e os identificadores ANA estão detalhados em [Aquisição ANA](ana.md).

| Data | Cena STAC | Nuvens na cena (%) | Recortes | CHIRPS (mm/mês) |
| --- | --- | ---: | ---: | ---: |
| 2025-06-27 | S2B_T23KKA_20250627T132241_L2A | 0,001155 | 4 | 1,7987 |
| 2025-07-02 | S2C_T23KKA_20250702T132518_L2A | 0,001005 | 4 | 1,7581 |
| 2025-08-26 | S2B_T23KKA_20250826T132234_L2A | 0,001055 | 4 | 8,7562 |

As três cenas foram escolhidas entre 26 itens STAC que retornaram para a área e período. Os recortes B04/B08 têm 196 × 175 pixels a 10 m, e os de B11/SCL têm 101 × 90 pixels a 20 m, em WGS 84 / UTM 23S (EPSG:32723). Os ativos de reflectância registraram escala 0,0001, offset −0,1 e NoData igual a 0 nos itens selecionados.

Os GeoTIFFs mensais CHIRPS América Latina correspondem a junho, julho e agosto de 2025. A leitura integral verificou todos os blocos. Os arquivos não trazem etiquetas de unidade ou NoData. A unidade de milímetros acumulados e o valor ausente −9999 foram confirmados pela documentação do produto. Uma extração independente pela grade e coordenadas dos polígonos encontrou a mesma célula nos cinco pivôs e reproduziu os três totais. [Artigo do produto](https://doi.org/10.1038/s41597-026-07096-4) · [FAQ do produtor](https://wiki.chc.ucsb.edu/CHIRPS3_FAQ)

Exemplo para o FID ANA 8087, de 53,22 ha.

| Data | NDVI mediano | NDMI mediano | Pixels válidos (%) |
| --- | ---: | ---: | ---: |
| 2025-06-27 | 0,665394 | 0,120631 | 100 |
| 2025-07-02 | 0,634876 | 0,078540 | 100 |
| 2025-08-26 | 0,212089 | −0,184229 | 100 |

Em 27 de junho, um cálculo independente nas quatro células de 10 m correspondentes a cada centro de pixel de 20 m confirmou ambas as medianas do FID 8087 em 1.327 pixels válidos, com diferença absoluta inferior a 0,000001. Os três pontos temporais permitem inspecionar a cadeia de cálculo. A série ainda é curta para estimar o padrão sazonal de referência. Os cinco pivôs compartilham uma única célula regional de chuva.

Contains modified Copernicus Sentinel data 2025. Precipitação do Climate Hazards Center Infrared Precipitation with Stations version 3, UCSB.

## Medições e reprodução

| Fonte | Requisições registradas | Bytes de corpo HTTP |
| --- | ---: | ---: |
| ANA/SNIRH | 16 | 17.404.766 |
| STAC Earth Search | 2 | 483.232 |
| COGs Sentinel-2 | 122 | 12.845.056 |
| CHIRPS UCSB | 6 | 12.551.100 |
| Total | 146 | 43.284.154 |

As requisições somaram 75,369 segundos no inventário. Os 12 recortes Sentinel-2 somaram 350.314 bytes em disco. O volume lido por Range equivaleu a 0,85% do tamanho total declarado para os 12 COGs remotos. O diretório `data/` ocupava 31.689.026 bytes no momento de geração do relatório integrado, antes das cópias da reprodução. Os valores de transferência cobrem a aquisição registrada pelo pipeline e excluem a instalação e as sondagens manuais.

A integração sobre o cache levou 2,413 s. A reprodução offline levou 0,740 s, com zero requisições, e reproduziu o CSV e o gráfico byte a byte. O SHA-256 do CSV foi `663e37b8e5eda40922d199bb478ff153516779bba92bb20b57f0fd994de963c5`. A suíte executada no ambiente Python 3.12 teve **38 testes aprovados**.

Os arquivos locais de saída são `data/curated/observacoes.csv`, `data/curated/serie_temporal.png` e `data/curated/relatorio_aquisicao.json`. Os detalhes de integridade, tamanhos e origens estão em `data/acquisition.jsonl` e nos manifestos em `data/raw/`.

## Ocorrências operacionais

A resolução de dependências com `uv.lock` foi validada. O download de alguns wheels do PyPI progrediu lentamente, e a instalação foi concluída com os wheels de Rasterio e Pyogrio montados a partir de respostas parciais e verificados contra os SHA-256 do lock. O ambiente instalado passou em `uv pip check`. A primeira tentativa de recorte revelou uma incompatibilidade de registro do leitor customizado no Rasterio 1.5.2. Depois da correção, a segunda tentativa reutilizou o inventário STAC e obteve as 12 janelas. As observações acima vêm dessa execução validada.
