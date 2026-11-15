# Seleção territorial MA/PI — AquaClima, fase 6

Data de referência: 15/11/2026. **Decisão documentada antes da aquisição de rasters: Guadalupe, PI**, código IBGE `2204501`, para uma prova exploratória com cinco pivôs ANA. Seleção não constitui validação de monitoramento, de sazonalidade ou de modelo regional.

## Fontes e consulta

A fonte obrigatória é a [camada oficial ANA/SNIRH Pivôs Centrais 2022](https://portal1.snirh.gov.br/server/rest/services/SFI/PIVOS_2022_SNIRH/MapServer/0). Os metadados reais consultados anunciam polígonos EPSG:4674, campo OID `FID`, máximo de 2.000 feições e ausência de paginação convencional. `MUNIC_CD` é texto. O código consulta `returnCountOnly`, confere `returnIdsOnly` e recupera geometrias por lotes de até 250 `objectIds`, reutilizando validadores de completude, duplicatas e CRS do pipeline original. Nenhum `resultOffset` é empregado.

O inventário estadual completo de MA e PI fornece uma checagem independente dos filtros por código municipal. Nomes e códigos foram resolvidos na [API oficial de localidades do IBGE](https://servicodados.ibge.gov.br/api/docs/localidades), sem confiar em dígitos verificadores digitados manualmente. A associação espacial é conferida com a [API de malhas municipais IBGE v3](https://servicodados.ibge.gov.br/api/docs/malhas?versao=3), qualidade máxima, resposta corrente preservada e identificada por hash. A API retornou HTTP 500 para o parâmetro `periodo=2024`; portanto **não se atribui ano 2024 ao limite recuperado sem esse parâmetro**. Diferenças de limite são inconsistências cartográficas a investigar, sem corrigir silenciosamente a classificação ANA.

A referência territorial é o ponto público da sede de Caxias, código `2103000`, da [camada oficial de sedes municipais no SNIRH](https://portal1.snirh.gov.br/arcgis/rest/services/DADOSABERTOS/Sede_Municipais/MapServer/0): longitude `-43.358539429`, latitude `-4.86167498984`. Não foi utilizado endereço pessoal. Áreas e distâncias são geodésicas no elipsoide GRS80. O grupo minimiza a distância ao k-ésimo vizinho, com desempate pela soma das distâncias quadráticas e FID; k é o mínimo entre cinco e a quantidade elegível. A saída pública usa transformação EPSG:4674 → EPSG:4326.

## Critérios registrados antes da triagem STAC

`data/regions/selection/method.json` registra horário, fórmulas, pesos e justificativas, antes das consultas comparativas Sentinel-2. O escore é uma ferramenta de priorização de engenharia, não uma métrica de validade científica.

| Critério | Peso | Medida normalizada entre 0 e 1 |
|---|---:|---|
| Quantidade e geometria | 25% | mínimo de 1 e quantidade de pivôs válidos, sem reparo, com ≥25 ha e centroide dentro da malha / 5 |
| Disponibilidade Sentinel-2 | 25% | mínimo de 1 e datas distintas com uma cena cobrindo integralmente a amostra, nuvens da cena ≤40% / 48 |
| Continuidade preliminar | 20% | meses de 2023–2024 com ao menos uma cena elegível / 24 |
| Proximidade de Caxias | 15% | máximo de 0 e 1 − distância sede–centroide do grupo / 600 km |
| Custo e concentração | 15% | 0,5 / quantidade de tiles MGRS elegíveis + 0,5 × máximo de 0 e 1 − raio do grupo / 20 km |

Cinco pivôs e 25 ha preservam a escala do piloto anterior. As 48 datas representam duas alternativas por mês para contingência de nuvens; 24 meses medem continuidade da janela 2023–2024. 600 km define a escala regional e 20 km favorece amostras compactas frente aos tiles Sentinel-2 de aproximadamente 100 km. São metas operacionais explícitas, sem pretensão de universalidade. O mínimo para avançar é três pivôs e seis meses com cenas preliminares. A decisão escolhe o maior escore elegível, com desempate por distância e código.

## Inventário e comparação real

| Município | UF | Código IBGE | Pivôs ANA | Elegíveis ≥25 ha | Raio grupo (km) | Distância Caxias (km) | Datas STAC elegíveis | Meses /24 | Escore /100 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Caxias | MA | 2103000 | 0 | 0 | — | — | não consultado | — | inelegível |
| Timon | MA | 2112209 | 5 | 3 | 0,85 | 76,78 | 86 | 21 | 85,26 |
| Guadalupe | PI | 2204501 | 12 | 10 | 1,72 | 215,49 | 68 | 19 | **89,80** |
| Jerumenha | PI | 2205300 | 2 | 2 | 0,97 | 252,08 | não consultado | — | inelegível |
| Landri Sales | PI | 2205607 | 0 | 0 | — | — | não consultado | — | inelegível |
| Balsas | MA | 2101400 | 49 | 45 | 0,95 | 439,42 | 74 | 18 | 83,66 |
| Riachão | MA | 2109502 | 33 | 33 | 1,19 | 429,17 | 74 | 18 | 83,82 |
| Loreto | MA | 2106102 | 3 | 3 | 1,40 | 367,26 | 82 | 22 | 78,63 |
| Barra do Corda | MA | 2101608 | 4 | 4 | 37,62 | 205,90 | 47 | 15 | 74,33 |
| Colinas | MA | 2103505 | 3 | 3 | 4,83 | 161,35 | 65 | 16 | 77,49 |
| Anapurus | MA | 2100808 | 1 | 0 | — | — | não consultado | — | inelegível |
| Parnarama | MA | 2107803 | 2 | 2 | 1,43 | 86,72 | não consultado | — | inelegível |
| Palmeirais | PI | 2207504 | 1 | 1 | 0 | 116,65 | não consultado | — | inelegível |
| Teresina | PI | 2211001 | 1 | 1 | 0 | 77,26 | não consultado | — | inelegível |

Barra do Corda e Colinas foram adicionadas porque o inventário estadual mostrou ao menos três pivôs a menos de 250 km da sede de Caxias. Após a decisão, a auditoria suplementar conferiu também todos os municípios com algum pivô a menos de 150 km: Anapurus, Parnarama, Palmeirais e Teresina. Nenhum alcança três pivôs elegíveis, portanto a escolha permaneceu a mesma. Todas as medidas exatas estão em `municipalities.csv`. Contagens integrais por município de ambos os estados estão em `state-municipality-counts.json`: **136 pivôs no Maranhão e 40 no Piauí, distribuídos por 26 municípios**. A tabela detalha 14 municípios candidatos e 116 polígonos; os demais constam no inventário estadual resumido.

A conferência por interseção geométrica do inventário estadual completo com as malhas IBGE também encontrou zero pivôs em Caxias e Landri Sales. Isso reforça o resultado dos atributos municipais na edição consultada; não prova ausência de toda forma de irrigação, nem ausência atual de equipamentos não mapeados.

Não foram encontradas geometrias inválidas nos municípios da tabela. Balsas apresenta três centroides fora da malha IBGE recuperada (`5627`, `18950`, `18951`) e sete polígonos não integralmente cobertos; os três primeiros foram excluídos da elegibilidade. A malha de Riachão intersecta quatro polígonos atribuídos a Balsas (`5611`, `17183`, `18950`, `18951`). Os polígonos e os atributos originais continuam no inventário, sem reassociação inventada. Em Guadalupe, os 12 polígonos estão integralmente dentro da malha; dois têm área inferior a 25 ha. Em Timon, os cinco estão dentro da malha, mas dois têm área inferior a 25 ha: a amostra elegível real é três.

## Região selecionada e alternativas

Guadalupe venceu pelo conjunto de cinco pivôs compactos, dez opções elegíveis no município, 19 meses com alternativas STAC e proximidade regional razoável. A distância até a sede de Caxias é 215,49 km em linha reta, medida sobre o centroide do grupo, sem equivalência a deslocamento rodoviário. Timon é a alternativa mais próxima e obteve a segunda maior nota, mas oferece somente três pivôs acima do corte de área. Guadalupe possui **pivôs reais na camada ANA**; a escolha não transforma outras modalidades de irrigação do município em pivôs.

| FID ANA selecionado | Identificador do estudo |
|---:|---|
| 5795 | `PI:5795` |
| 5797 | `PI:5797` |
| 5798 | `PI:5798` |
| 5802 | `PI:5802` |
| 5804 | `PI:5804` |

As áreas, coordenadas e atributos individuais estão em `inventory.csv` e `inventory.geojson`; `sample-2204501.geojson` contém o grupo de aquisição. O tile elegível é `23MPN`. A triagem recuperou 146 itens C1 L2A de 2023–2024 para o grupo, dos quais 68 datas cobrem integralmente todos os pivôs e satisfazem o filtro de nuvens da cena. Os meses com alternativas preliminares são janeiro–fevereiro e maio–dezembro de 2023; março e maio–dezembro de 2024. **Isso não equivale a 19 meses com índices válidos**: a qualidade por pixel ainda será testada.

## Plano de aquisição e critérios de parada

1. Copiar a amostra para namespace independente `data/regions/guadalupe-pi/`, mantendo FID, UF e chave regional.
2. Executar pequena prova em meses distribuídos: **janeiro, julho e novembro de 2023; março, julho e novembro de 2024**. Janeiro de 2023 substituiu março de 2023 após a triagem STAC e antes dos rasters, pois março não tinha alternativa com nuvens de cena ≤40%. Essa escolha condicionada à disponibilidade é não aleatória e não representa uma amostragem sazonal completa. Usar poucos candidatos por mês e orçamento explícito, sem adquirir centenas de imagens.
3. Reutilizar o pipeline de COG/SCL, auditoria de escala e offset de cada produto, alinhamento, NDVI/NDMI e mediana espacial sobre pixels válidos; somente aceitar observações com ≥70% de pixels válidos.
4. Integrar precipitação CHIRPS v3 como contexto regional, sem inferir consumo ou economia de água.
5. Verificar os hashes e reproduzir offline. Somente relatar portabilidade efetivamente demonstrada após a execução. Não aplicar modelos de Paracatu como se validados nesta população.

Se a prova não alcançar três pivôs com observações reais em datas distintas e precipitação, apresentar apenas auditoria territorial na entrega. A decisão de incorporação deve ocorrer até 18/11; novos experimentos encerram-se em 20/11. O estudo `2022_2024_recovery_v1` de Paracatu permanece congelado e separado.

## Reexecução, evidências e limitações

Com o ambiente instalado: `.venv/Scripts/python.exe -m aquaclima.regions.audit`. `--inventory-only` executa a etapa ANA/IBGE sem consulta Sentinel-2. `acquisition.jsonl` mantém origem, bytes e SHA-256; `decision.json` registra data da decisão, hash do método, hash do inventário, scores e amostra. Os arquivos em `raw/` preservam respostas originais; são cache local e não devem ser incorporados em volume ao Git. Pequenos inventários, amostra, método, decisão e resumos de cenas são os artefatos de revisão.

A decisão original, tomada às 14:37:47 de 15/11/2026 no horário de São Paulo, tem SHA-256 `43f1c57db963fe29ec3f57a085f705e421ff3b762ee255fc7d6b1d2d8968ccf0`. Ela antecede a política de aquisição e permanece congelada, vinculando exatamente os cinco FIDs. Durante a complementação espacial o arquivo foi regravado, mas seus bytes originais foram recuperados e conferidos contra o hash já registrado na política do piloto. `supplemental.json` preserva a extensão da auditoria com quatro municípios adicionais e interseções espaciais, sem esconder essa sequência. `inventory-initial-recovered.geojson` conserva o inventário inicial com o hash gravado na decisão; `inventory.geojson` é o inventário suplementar com transformação explícita para WGS84.

Reexecução real sem rede concluída: `.venv/Scripts/python.exe -m aquaclima.regions.audit --offline`, **zero requisições e zero bytes transferidos**, mesma escolha e amostra sem alteração de bytes. Uma nova execução grava `replay.json` e não substitui a decisão nem os arquivos de amostra existentes. A checagem portátil `.venv/Scripts/python.exe scripts/verify_regional_selection.py` verificou 18 artefatos e o vínculo da amostra com a decisão, sem precisar dos caches externos. O manifesto `public-integrity.json` controla o conjunto revisável de 19 arquivos, aproximadamente 5,24 MB, sem rasters.

O inventário HTTP da auditoria, incluindo consultas iniciais, retentativas e complementação, registrou **83 requisições, 25.405.987 bytes transferidos e 25.685.049 bytes nos arquivos de aquisição inventariados**, com seis requisições malsucedidas. São bytes de transporte antes da descompressão e arquivos decodificados, respectivamente; não representam download de imagens. A seleção e os relatórios acrescentam armazenamento local fora desse inventário HTTP. Os erros observados (HTTP 500 na malha com período explícito e gzip do IBGE) foram registrados e tratados: a integração regional aceita gzip com limite tanto no corpo comprimido quanto no descomprimido, sem modificar a política de transferência de rasters do estudo congelado.

Os 11 testes de auditoria regional foram executados com sucesso, cobrindo completude municipal, IDs duplicados ou incorretos, ausência de geometria, reparos excluídos da amostra, divergência entre atributo e localização, concentração geodésica determinística, imutabilidade de amostras, gzip limitado do IBGE e recusa de cache adulterado em modo offline. Comando local: `.venv/Scripts/python.exe -m pytest tests/test_regions_audit.py -q --basetemp .local-review/pytest-regions-audit-v1`.

As consultas de nuvens são uma proxy de planejamento da cena inteira. Não indicam condição específica do pivô, atividade de irrigação em 2023–2024, produtividade ou sazonalidade anual completa. Datas em catálogo podem falhar na aquisição COG. O mapeamento ANA refere-se a 2022; limites IBGE correntes podem diferir do período de levantamento. A seleção cobre os candidatos explícitos e alternativas próximas encontradas no inventário, não otimiza todos os municípios brasileiros. Não houve aquisição de raster nesta etapa.
