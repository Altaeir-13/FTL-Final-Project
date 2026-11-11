# Resultado histórico de 2022 a 2024

Execução real em 11 de novembro de 2026, Windows e Python 3.12.13, em CPU. O desenvolvimento ocorreu na branch development/historical-acquisition. Os mesmos cinco pivôs do piloto foram usados. Os arquivos do piloto de 2025 e a referência main foram preservados.

A aquisição incremental conserva catálogos, respostas STAC, triagem SCL, recortes e checkpoints mensais. Os modelos e a análise exploratória consomem os datasets consolidados por arquivos locais. Os detalhes de configuração, caminhos, política científica e comandos estão no [guia histórico](historico.md).

Foram consultados os 36 meses, com 153 candidatas C1. A seleção pela qualidade dentro dos pivôs resultou em 45 cenas, 203 observações aceitas e 22 rejeições entre 225 pares pivô–cena processados. A tabela mensal contém 180 linhas. Há índices observados em 111 pivôs-mês, ou 61,67% do período solicitado.

| Ano | Candidatas C1 | Observações aceitas | Pivôs-mês observados/esperados | Cobertura |
| --- | ---: | ---: | ---: | ---: |
| 2022 | 7 | 5 | 5/60 | 8,3% |
| 2023 | 73 | 108 | 57/60 | 95,0% |
| 2024 | 73 | 90 | 49/60 | 81,7% |

Em 2022, dez meses não retornaram itens no catálogo C1 consultado. Dezembro tinha seis candidatas, todas rejeitadas pela qualidade local. As observações de 2022 provêm apenas de março. Janeiro e novembro de 2024 também terminaram sem observações espectrais aceitas. Essas lacunas representam o catálogo e o filtro efetivamente utilizados. A verificação de outra coleção Sentinel-2 encontrou mais itens, acompanhados de particularidades radiométricas que precisam de validação própria antes de sua adoção.

| Pivô ANA | Meses observados/36 | Cobertura | Cenas aceitas | Meses de treino 2022–2023 |
| --- | ---: | ---: | ---: | ---: |
| 16708 | 23/36 | 63,9% | 42 | 13 |
| 17373 | 22/36 | 61,1% | 40 | 12 |
| 17382 | 21/36 | 58,3% | 38 | 12 |
| 19997 | 22/36 | 61,1% | 41 | 12 |
| 8087 | 23/36 | 63,9% | 42 | 13 |

A tabela seguinte distingue ausência de candidatas, datas selecionadas e observações aceitas. A precipitação ficou disponível nos 36 meses.

| Mês | Candidatas | Datas selecionadas | Pares pivô–cena aceitos | Pivôs observados/5 |
| --- | ---: | ---: | ---: | ---: |
| 2022-01 | 0 | 0 | 0 | 0/5 |
| 2022-02 | 0 | 0 | 0 | 0/5 |
| 2022-03 | 1 | 1 | 5 | 5/5 |
| 2022-04 | 0 | 0 | 0 | 0/5 |
| 2022-05 | 0 | 0 | 0 | 0/5 |
| 2022-06 | 0 | 0 | 0 | 0/5 |
| 2022-07 | 0 | 0 | 0 | 0/5 |
| 2022-08 | 0 | 0 | 0 | 0/5 |
| 2022-09 | 0 | 0 | 0 | 0/5 |
| 2022-10 | 0 | 0 | 0 | 0/5 |
| 2022-11 | 0 | 0 | 0 | 0/5 |
| 2022-12 | 6 | 0 | 0 | 0/5 |
| 2023-01 | 6 | 2 | 2 | 2/5 |
| 2023-02 | 6 | 2 | 10 | 5/5 |
| 2023-03 | 6 | 2 | 10 | 5/5 |
| 2023-04 | 6 | 2 | 6 | 5/5 |
| 2023-05 | 6 | 2 | 10 | 5/5 |
| 2023-06 | 6 | 2 | 10 | 5/5 |
| 2023-07 | 6 | 2 | 10 | 5/5 |
| 2023-08 | 6 | 2 | 10 | 5/5 |
| 2023-09 | 6 | 2 | 10 | 5/5 |
| 2023-10 | 7 | 2 | 10 | 5/5 |
| 2023-11 | 6 | 2 | 10 | 5/5 |
| 2023-12 | 6 | 2 | 10 | 5/5 |
| 2024-01 | 6 | 0 | 0 | 0/5 |
| 2024-02 | 6 | 2 | 7 | 5/5 |
| 2024-03 | 6 | 2 | 9 | 5/5 |
| 2024-04 | 6 | 2 | 10 | 5/5 |
| 2024-05 | 6 | 2 | 10 | 5/5 |
| 2024-06 | 6 | 2 | 10 | 5/5 |
| 2024-07 | 6 | 2 | 10 | 5/5 |
| 2024-08 | 7 | 2 | 10 | 5/5 |
| 2024-09 | 5 | 2 | 10 | 5/5 |
| 2024-10 | 6 | 2 | 6 | 5/5 |
| 2024-11 | 6 | 0 | 0 | 0/5 |
| 2024-12 | 7 | 2 | 8 | 4/5 |

A triagem das candidatas registrou os motivos {'scl_threshold_met': 94, 'no_pivot_above_scl_threshold': 59}. As frações de pixels por pivô, os IDs e as justificativas de exclusão permanecem nos manifestos selected.json. Em 19/01/2023, uma cena com 63,39% de nuvens globais forneceu 71,89% de pixels válidos no pivô 8087, enquanto os outros quatro pivôs nessa cena foram rejeitados. Esse caso demonstra o uso da qualidade local.

Os resultados exploratórios mostram trajetórias diferentes entre pivôs próximos. Os agregados mensais variaram de 0,124 a 0,903 em NDVI e de −0,341 a 0,532 em NDMI. Em dezembro de 2023, sob o mesmo contexto regional de 270,87 mm de chuva, os NDVIs mensais dos cinco pivôs ficaram entre 0,124 e 0,897. Cultura, fase fenológica e manejo permanecem desconhecidos.

Foram registrados 83 contrastes que ultrapassaram os limiares descritivos de 0,20 em NDVI ou 0,15 em NDMI. Eles correspondem a 49 transições distintas entre pivôs e meses, e 24 contrastes atravessam lacunas. A lista de baixa qualidade contém 71 linhas, incluindo 69 meses sem observação e dois meses observados com validade mínima abaixo de 80%. Esses registros orientam revisão exploratória.

A comparação anual usa apenas cinco pivôs-mês em 2022, todos de março, contra 57 em 2023 e 49 em 2024. A diferença de amostragem e sazonalidade limita a interpretação como tendência anual. Todos os pivôs compartilham uma célula CHIRPS por mês. O gráfico de chuva fornece contexto regional repetido entre campos próximos e permite inspecionar associação retrospectiva.

As saídas incluem distributions.png, temporal_pivots.png, annual_comparison.png, seasonal_heatmap.png, rain_context.png, descriptive_statistics.csv, month_coverage.csv, seasonal_coverage.csv, low_quality_months.csv e pronounced_changes.csv. Os cinco gráficos passaram por inspeção visual.

O módulo sazonal foi executado com treino 2022–2023 e validação em 2024. Há apenas 12 ou 13 meses de treinamento por pivô. O método harmônico exige 18 meses e os 12 meses do calendário. A mediana sazonal exige duas observações de anos distintos por mês do calendário, satisfeitas apenas em março nesta base. Dez estimativas numéricas, correspondentes a cinco pivôs e dois índices em março de 2024, puderam ser construídas. As 240 linhas do arquivo de validação incluem registros explícitos de insuficiência. Nenhuma combinação alcançou seis meses pontuados, portanto MAE e RMSE permanecem ausentes e baseline_report.json registra insufficient_data.

Ajustar uma regressão regularizada com menos observações é algebricamente possível, mas não satisfaz o critério de evidência definido para esta execução. A recomendação é completar e auditar as lacunas de Sentinel-2 L2A de 2022 antes da comparação anual de modelos, ou definir previamente outro protocolo temporal em um experimento separado. Aumentar o número de cenas nos meses já disponíveis não corrige a ausência dos outros meses de treinamento. O ano de 2025 continua reservado, com a exposição às três datas do piloto registrada.

O UCSB retornou HTTP 429 persistente e os pedidos seguintes foram interrompidos. A recuperação usou explicitamente o espelho oficial USGS do CHIRPS v3 final. Uma janela de 25 células de março de 2022 foi comparada à origem UCSB, com igualdade exata. Os arquivos completos foram adquiridos depois do novo planejamento e validados por decodificação integral e SHA-256. Os três meses UCSB anteriores foram preservados e os outros 33 foram recuperados no USGS. [Espelho oficial USGS](https://edcintl.cr.usgs.gov/downloads/sciweb1/shared/fews/web/global/monthly/chirps/final/downloads/monthly/)

A auditoria independente dos 36 GeoTIFFs confirmou os 180 valores de chuva e suas células, com diferença máxima de 0 mm. Os arquivos climáticos somam 766.937.788 bytes. Uma conferência independente de bandas de 2022 e 2024 também reproduziu NDVI e NDMI diretamente nos pixels de 20 m, com diferenças inferiores a 0,000001.

| Medição | Resultado |
| --- | ---: |
| Transferência histórica acumulada do pipeline | 988.966.476 bytes |
| Requisições históricas acumuladas | 2.181 |
| Transferência da recuperação USGS | 754.860.190 bytes |
| Armazenamento em data/ no fechamento da recuperação | 826.201.481 bytes |
| Primeira aquisição ampliada, com limitação UCSB | 895,346 s |
| Recuperação USGS e consolidação | 202,726 s |
| Reprodução offline | 8,580 s |
| Reexecução com cache | 9,695 s |

Os bytes de transferência contam os corpos HTTP registrados pelo pipeline e excluem sondagens diagnósticas isoladas e o ambiente de software. O planejamento inicial estimou 652,83 MB. A recuperação posterior estimou 754,86 MB adicionais para arquivos globais USGS. Cada execução respeitou os limites configurados de 2 GB. Havia cerca de 205 GB livres antes das aquisições.

Os 106 testes automatizados passaram. A reprodução offline bloqueou explicitamente a criação do cliente HTTP e as chamadas requests. Os três CSVs e os gráficos conferidos foram idênticos byte a byte entre aquisição, execução offline e reexecução com cache. Ambas as reexecuções fizeram zero requisições e transferiram zero bytes. O CSV e o gráfico originais do piloto de 2025 também foram reproduzidos com os hashes anteriores.

| Dataset | SHA-256 |
| --- | --- |
| Observações | 4ae5b9d7d34c5e1ca9bcc24e7598ef2c21830df36a9ea7ac4c8786cb6aabbce0 |
| Tentativas | aeafcab7d8967d14905cbef3cf6938cdba5464281e43e7434e4e58ee8db71ee3 |
| Mensal | c3b80e69ca7ad49c92a3045f76b7e1713e8315b258523d996e87886053d81da7 |

Os arquivos adquiridos, rasters, caches e ambientes ficam fora do Git. O código, os testes, os parâmetros e este relatório documentam a reprodução. O guia histórico contém os comandos PowerShell para aquisição, consolidação, exploração, baseline e reprodução offline.

Contains modified Copernicus Sentinel data 2022, 2023, 2024. Precipitação do Climate Hazards Center Infrared Precipitation with Stations version 3, UCSB, com distribuição complementar pelo USGS.
