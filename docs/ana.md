# Delimitação e pivôs do piloto

O limite do estudo vem da unidade de automonitoramento `SMA`, registro `FID=16`. O serviço identifica a feição como **Bacia do São Marcos**, na unidade Paranaíba, e registra a BHO `06_02_04` de 19/10/2022 e a Resolução ANA nº 188/2024. A Resolução Conjunta nº 109/2021 descreve a bacia a montante da confluência do São Marcos com o Paranaíba. [Camada de automonitoramento da ANA](https://portal1.snirh.gov.br/server/rest/services/SFI/Unidades_Automonitoramento_UGRH_MRS/MapServer/0), [Resolução nº 188/2024](https://www.gov.br/ana/pt-br/legislacao/resolucoes/resolucoes-regulatorias/2024/188), [Resolução Conjunta nº 109/2021](https://www.gov.br/ana/pt-br/legislacao/resolucoes/resolucoes-regulatorias/2021/109).

As geometrias dos pivôs vêm do Mapeamento Atualizado da Agricultura Irrigada por Pivôs Centrais no Brasil, ano de referência 2022. As duas camadas são públicas, sem autenticação. Atribua os dados ao SNIRH e à Agência Nacional de Águas e Saneamento Básico (ANA), com identificação da camada e do recorte utilizado. A presença em 2022 indica o local mapeado e a atividade em datas posteriores requer verificação independente. [Camada Pivôs Centrais 2022](https://portal1.snirh.gov.br/server/rest/services/SFI/PIVOS_2022_SNIRH/MapServer/0), [Publicação do mapeamento](https://www.gov.br/ana/pt-br/ana-lanca-mapeamento-com-dados-atualizados-sobre-agricultura-irrigada-por-pivos-centrais-no-brasil).

## Consulta e seleção

1. O ArcGIS fornece o limite da bacia em GeoJSON, com `outSR=4326`. Os metadados registram EPSG:4674 para a origem do limite e dos pivôs.
2. O pipeline consulta o retângulo envolvente da bacia. Compara a contagem do servidor com os identificadores únicos retornados e recupera suas feições em lotes de até 250 por `objectIds`, dentro do máximo anunciado de 2.000. Confere o CRS explícito EPSG:4674, a identidade e a completude de cada lote.
3. Para uma geometria inválida, aplica `make_valid` do GEOS, mantém os componentes poligonais e os une. Registra o motivo da invalidez e descarta feições que continuam sem área poligonal válida. Transforma o limite da bacia para EPSG:4674 e seleciona apenas pivôs cobertos por inteiro.
4. Calcula `area_ha` geodesicamente sobre o elipsoide GRS80, preservando `Hectares` como atributo original. O corte de 25 ha equivale a aproximadamente 625 células de 20 m antes das perdas por bordas e máscaras. O objetivo é reter uma área suficiente para estatísticas espectrais no piloto.
5. Compara os centroides em SIRGAS 2000 / UTM 23S (EPSG:31983). Seleciona o grupo que minimiza a distância de um centro candidato ao k-ésimo vizinho, contando o próprio centro. Usa a soma de distâncias quadráticas e o FID como desempate. A amostra é concentrada para baratear a validação. A inferência do piloto se restringe ao grupo escolhido.

As saídas locais são `data/processed/pivots.geojson` (WGS 84, longitude e latitude) e `data/processed/pivots.gpkg` (SIRGAS 2000, camada `pivots`). Preservam `FID`, `Hectares`, `PIVO_2019`, `id_1`, campos municipais e os demais atributos originais. O campo `pivot_id` usa o `FID` como texto e seu escopo é o inventário consultado. O GeoJSON inclui os critérios, contagens e informações de proveniência. `data/raw/ana/` contém as respostas originais e `data/acquisition.jsonl` inventaria os arquivos com origem e SHA-256.

## Aquisição verificada

Em 10/11/2026, o serviço retornou 2.661 FIDs únicos no envelope do limite oficial. As 2.661 feições foram obtidas em 11 lotes, todos com EPSG:4674 declarado. Os metadados, o limite, a contagem, os identificadores e os lotes somaram 16 arquivos e 17.404.766 bytes de respostas bem-sucedidas no inventário local. A soma dos tempos das 16 requisições registradas foi de 5,38 s. O retângulo envolvente cobre aproximadamente 47,8932° O a 46,9849° O e 18,2574° S a 15,9794° S. As coordenadas arredondadas servem para descrever o recorte. O código consulta o envelope com a precisão do arquivo de origem.

Das 2.661 feições recuperadas, 1.496 estavam inteiramente dentro da bacia e 1.374 tinham pelo menos 25 ha. Foram selecionados cinco pivôs em Paracatu, MG, com distância máxima de 794,05 m ao centro de referência. O limite e todas as geometrias recuperadas passaram na validação. A contagem de correções e de duplicatas foi zero.

| FID ANA | Área geodésica (ha) | `Hectares` ANA |
| --- | ---: | ---: |
| 8087 | 53,22446 | 53,22484 |
| 16708 | 30,72905 | 30,72927 |
| 17373 | 28,76991 | 28,77012 |
| 17382 | 50,91155 | 50,91191 |
| 19997 | 30,25146 | 30,25168 |

GeoJSON e GeoPackage foram reabertos e validados em EPSG:4326 e EPSG:4674, respectivamente, com os mesmos cinco identificadores e 170.823 bytes de armazenamento combinado. A seleção e a gravação a partir do cache levaram 1,42 s, com zero requisições. A repetição levou 0,95 s, com zero requisições e sem alteração dos hashes ou horários de modificação das saídas.
