# Baselines após a recuperação histórica

Resultado verificado em 11/11/2026, na versão **`2022_2024_recovery_v1`**, gerada em `data/recovery/curated/2022_2024_recovery_v1/`. A recuperação viabilizou a mediana sazonal para os cinco pivôs e a regressão harmônica Ridge para dois pivôs, mantendo integralmente os critérios definidos na fase anterior.

## Base e elegibilidade

A versão contém **256 observações aceitas, 57 cenas e 180 registros mensais**. São 141 espaços pivô/mês observados, ou 78,3% de cobertura no período 2022–2024. A base anterior continua preservada, com 203 observações e 111 espaços observados. As 53 observações adicionais recuperaram seis meses de 2022 — abril, maio, julho, agosto, setembro e outubro — nos cinco pivôs, totalizando 30 espaços recuperados. Somente produtos Planetary Computer com processing baseline 05.10, aprovados na auditoria radiométrica, foram integrados.

| Pivô ANA | Meses observados 2022–2024 | Meses de treino 2022–2023 | Meses do calendário presentes no treino | Mediana sazonal | Ridge harmônica |
|---|---:|---:|---:|---|---|
| 8087 | 29/36 | 19 | 12 | Elegível: 7 meses de validação | Elegível: 10 meses de validação |
| 16708 | 29/36 | 19 | 12 | Elegível: 7 meses de validação | Elegível: 10 meses de validação |
| 17373 | 28/36 | 18 | 11 | Elegível: 7 meses de validação | Inelegível: falta janeiro no treino |
| 17382 | 27/36 | 18 | 11 | Elegível: 7 meses de validação | Inelegível: falta janeiro no treino |
| 19997 | 28/36 | 18 | 11 | Elegível: 7 meses de validação | Inelegível: falta janeiro no treino |

2022 passou de 5 para 35 espaços observados em 60, cobertura de 8,3% para **58,3%**. 2023 conserva 57/60, e 2024 conserva 49/60. Permanecem ausentes em 2022 janeiro, fevereiro, junho, novembro e dezembro; em 2023, janeiro é ausente para os três pivôs com Ridge inelegível. A ausência desses meses não foi preenchida por imputação.

O protocolo original usa:

- **Treinamento:** somente meses aceitos e lotes completos de 2022–2023.
- **Mediana sazonal:** mediana dos valores de um mesmo mês do calendário, com pelo menos dois anos distintos representados. Nesta base, os meses elegíveis são março, abril, maio, julho, agosto, setembro e outubro.
- **Ridge harmônica:** intercepto e termos seno/cosseno das frequências anual e semestral; regularização fixa `alpha=1`, sem penalizar o intercepto. Exige pelo menos 18 meses de treinamento e todos os 12 meses do calendário representados.
- **Validação:** valores espectrais mensais observados de 2024. MAE e RMSE exigem pelo menos seis meses pontuados para cada pivô/índice/método. Não foram alterados os limiares após a recuperação.
- **2025:** excluído do ajuste, das predições e das métricas. As três datas examinadas no piloto exploratório, 27/06, 02/07 e 26/08/2025, permanecem registradas como exposição prévia.

Os três modelos Ridge inelegíveis continuam com métricas vazias. O motivo do treinamento está em `baseline/model_parameters.json`; os registros de predição indicam `insufficient_training_data`. O estado agregado de métricas é `insufficient_validation_data`, pois não há predições elegíveis para pontuar.

## Resultados numéricos em 2024

Os alvos são índices espectrais mensais aceitos, adimensionais. A tabela abaixo apresenta os resultados de cada método no conjunto de meses disponível para ele; a mediana usa sete meses e a Ridge usa dez. **Esses conjuntos são diferentes**, portanto a comparação direta entre os métodos requer a análise de meses comuns da seção seguinte.

| Pivô | Índice | MAE mediana, n=7 | RMSE mediana, n=7 | MAE Ridge, n=10 | RMSE Ridge, n=10 |
|---|---|---:|---:|---:|---:|
| 8087 | NDVI | 0,305161 | 0,384284 | 0,266892 | 0,316517 |
| 8087 | NDMI | 0,342486 | 0,387520 | 0,273385 | 0,323227 |
| 16708 | NDVI | 0,194547 | 0,264050 | 0,214809 | 0,291026 |
| 16708 | NDMI | 0,173848 | 0,233265 | 0,178830 | 0,243052 |
| 17373 | NDVI | 0,087875 | 0,097483 | — | — |
| 17373 | NDMI | 0,073323 | 0,082720 | — | — |
| 17382 | NDVI | 0,212555 | 0,255088 | — | — |
| 17382 | NDMI | 0,165284 | 0,200500 | — | — |
| 19997 | NDVI | 0,096576 | 0,123347 | — | — |
| 19997 | NDMI | 0,127835 | 0,150892 | — | — |

As saídas completas estão em `baseline/validation_metrics.csv`, `baseline/validation_predictions.csv`, `baseline/model_parameters.json` e `baseline/baseline_report.json`. Há 14 linhas pivô/índice/método com métricas elegíveis: dez da mediana e quatro da Ridge. Nenhum resultado da versão anterior foi substituído.

## Comparação nos mesmos meses

O módulo independente `aquaclima.modeling.comparison` usa as predições já produzidas, sem reajustar modelos. Compara os três métodos juntos e cada par de métodos na interseção dos meses aceitos e pontuados. Mantém o mínimo de seis meses comuns para publicar métricas.

A comparação dos três métodos é elegível para os pivôs 8087 e 16708, em **sete meses de 2024**: março, abril, maio, julho, agosto, setembro e outubro. São 14 espaços pivô/mês compartilhados, sem tratá-los como amostras independentes.

| Pivô | Índice | Método | n comum | MAE | RMSE |
|---|---|---|---:|---:|---:|
| 8087 | NDVI | Mediana sazonal | 7 | 0,305161 | 0,384284 |
| 8087 | NDVI | Ridge harmônica | 7 | 0,296783 | 0,344644 |
| 8087 | NDVI | Mesmo mês de 2023 | 7 | 0,349113 | 0,455468 |
| 8087 | NDMI | Mediana sazonal | 7 | 0,342486 | 0,387520 |
| 8087 | NDMI | Ridge harmônica | 7 | 0,334005 | 0,362340 |
| 8087 | NDMI | Mesmo mês de 2023 | 7 | 0,370050 | 0,445650 |
| 16708 | NDVI | Mediana sazonal | 7 | 0,194547 | 0,264050 |
| 16708 | NDVI | Ridge harmônica | 7 | 0,188342 | 0,266466 |
| 16708 | NDVI | Mesmo mês de 2023 | 7 | 0,226999 | 0,272673 |
| 16708 | NDMI | Mediana sazonal | 7 | 0,173848 | 0,233265 |
| 16708 | NDMI | Ridge harmônica | 7 | 0,160462 | 0,229348 |
| 16708 | NDMI | Mesmo mês de 2023 | 7 | 0,192706 | 0,250260 |

Nos sete meses comuns, a Ridge tem menor MAE que a mediana nos dois índices desses dois pivôs. O RMSE de NDVI em 16708 é ligeiramente menor para a mediana. A diferença entre MAE e RMSE mostra por que não cabe declarar um vencedor universal.

A comparação mediana versus mesmo mês de 2023 pode usar os cinco pivôs nos sete meses comuns. A mediana apresenta menor MAE nos dois índices de quatro pivôs; em 17382, o benchmark de 2023 apresenta menor MAE. O contraste Ridge versus benchmark usa dez meses comuns nos dois pivôs elegíveis. Os arquivos `comparison/common_month_metrics.csv` e `comparison/common_month_predictions.csv` listam todos os conjuntos exatos, incluindo os contrastes inelegíveis.

## Benchmark retrospectivo separado

O benchmark usa exclusivamente o valor aceito do mesmo mês de 2023 para estimar o valor observado em 2024, quando ambos existem. Seus resultados não dependem da recuperação de 2022: permanecem **49 pares pivô/mês**, ou 98 resíduos entre os dois índices, com 9–10 pares por pivô. As métricas são separadas das do experimento sazonal original.

| Pivô | Pares por índice | MAE NDVI | RMSE NDVI | MAE NDMI | RMSE NDMI |
|---|---:|---:|---:|---:|---:|
| 8087 | 10 | 0,311170 | 0,410074 | 0,314265 | 0,392096 |
| 16708 | 10 | 0,280952 | 0,332835 | 0,231365 | 0,280130 |
| 17373 | 10 | 0,181526 | 0,204160 | 0,155357 | 0,192716 |
| 17382 | 9 | 0,176633 | 0,213902 | 0,157652 | 0,192399 |
| 19997 | 10 | 0,191706 | 0,230977 | 0,198271 | 0,235004 |

## Verificação independente

Além dos testes automatizados, uma leitura independente dos arquivos reais confirmou:

- As 203 observações originais preservam exatamente NDVI, NDMI e percentual de pixels válidos; os 180 valores mensais de precipitação permanecem iguais.
- As 256 observações aceitas respeitam o limiar de 70% de pixels válidos. Não há duplicatas por pivô e chave da aquisição. A proveniência Planetary Computer aponta para o produto nativo, XML de calibração e SHA-256 verificáveis.
- As medianas mensais recalculadas com `statistics.median` reproduzem a tabela consolidada.
- Os coeficientes Ridge recalculados por mínimos quadrados aumentados, com decomposição SVD, reproduzem o ajuste da implementação por equações normais com erro absoluto inferior a `1e-12`.
- As predições sazonais, MAE e RMSE, os resultados do benchmark e as métricas de todos os contrastes de meses comuns foram recalculados diretamente das tabelas, sem chamar as funções de modelagem.
- Os hashes dos arquivos publicados no manifesto WebGIS correspondem aos arquivos locais. O relatório sazonal original de insuficiência permanece com SHA-256 `93d707cfaa99b0c14c52c80be1878652183e32ac4c4f0db93a6314c394a36d8f`.

## Reprodução e próxima fase

Com os arquivos adquiridos disponíveis localmente:

```powershell
uv run --no-sync aquaclima recovery-run --config configs/recovery-2022.toml --allow-bulk --offline --output-dir data/recovery/reproduzido/2022_2024_recovery_v1
uv run --no-sync python -m pytest -q
```

O fluxo reproduz a consolidação, os experimentos, a comparação e os contratos WebGIS. Os contratos estão documentados em [contratos-webgis.md](contratos-webgis.md). O manifesto científico identifica a versão independentemente do nome do diretório de reprodução.

É viável apresentar no Capstone uma comparação **exploratória de reconstrução sazonal** com esses baselines, sem novas fontes ou modelos complexos. A cobertura recuperada continua enviesada para sete meses do calendário em 2022; os dois pivôs elegíveis para Ridge possuem janeiro de 2023 observado, ao contrário dos demais. As culturas, fases fenológicas e práticas de manejo são desconhecidas. Os meses sucessivos e os pivôs próximos são dependentes, e não há rótulos independentes de falhas de irrigação. Não há base para afirmar capacidade diagnóstica ou generalização estatística a outras áreas.

Recomenda-se congelar esta versão e os parâmetros, apresentar qualidade e lacunas no WebGIS e manter 2025 para a avaliação cronológica posterior com o protocolo registrado. A chuva mensal completa permanece contexto descritivo; estes modelos não a utilizam para alegar previsão antecipada dentro do mês. Não ajustar limiares ou selecionar modelos usando 2025. A demonstração da interface deve comunicar alterações espectrais e evidências observacionais com suas limitações.
