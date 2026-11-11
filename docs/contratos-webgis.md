# Contratos locais para o WebGIS

O exportador `aquaclima.reporting.contracts.export_contracts` gera um pacote local de intercâmbio versão **1.0.0**. O aplicativo poderá consumir esse pacote sem executar consultas remotas ou abrir rasters. Esta fase entrega os arquivos e seus contratos; a interface será implementada posteriormente.

O ponto de entrada é `manifest.json`. Cada entrada de `files` contém caminho relativo ao diretório do manifesto, formato, quantidade de linhas quando aplicável, tamanho em bytes, SHA-256 e referência ao esquema do registro. `package_sha256` identifica o conteúdo completo; `packages/<hash>/` permite manter versões simultâneas. O manifesto só é atualizado após a validação dos insumos e a escrita dos arquivos do pacote. Reexecutar com os mesmos insumos conserva bytes e datas de modificação. O consumidor deve verificar os hashes antes de carregar um pacote.

Quando o dataset contém `dataset_manifest.json`, o campo de proveniência `dataset_name` usa sua `dataset_version` e verifica os hashes declarados de observações e tabela mensal. Assim, reproduzir a mesma versão científica em outro diretório conserva o pacote e seu identificador. Para bases anteriores sem esse manifesto, conserva-se o nome do diretório como identificação local.

## Arquivos e chaves

| Arquivo | Chave | Conteúdo principal |
|---|---|---|
| `pivots.geojson` | `properties.pivot_id` | Polígonos ANA e atributos originais, incluindo `area_ha`. GeoJSON WGS84, longitude/latitude, EPSG:4326. |
| `observations.csv` | `pivot_id`, `date`, `scene_id` | Somente observações aceitas: `month`, `ndvi_median`, `ndmi_median`, `valid_pixel_pct`, `status=ok`, identificadores, atributos de origem e hashes disponíveis na tabela científica. |
| `monthly.csv` | `pivot_id`, `month` | Todos os espaços pivô/mês do período contínuo, incluindo ausentes; índices, contagens, qualidade, chuva e proveniência. |
| `precipitation.csv` | `pivot_id`, `month` | `precip_mm`, `precip_status` e todos os campos `chirps_*` da tabela mensal, como URL, célula e integridade quando disponíveis. |
| `quality.csv` | `pivot_id`, `month` | `monthly_status`, `batch_status`, `query_complete`, `n_attempted_scenes`, `n_accepted_scenes`, `valid_pixel_pct_min`, `valid_pixel_pct_median`, `quality_review`; conserva contagem de datas, amplitude de dias e identificadores/hashes disponíveis. |
| `models.csv` | `experiment`, `pivot_id`, `target`, `method`, `phase` | Estado de elegibilidade, `n_valid_pairs`, `expected_months`, `coverage_fraction`, `mae`, `rmse`, `bias_mean`. Métricas inelegíveis ficam ausentes. |
| `model_predictions.csv` | `experiment`, `pivot_id`, `target`, `method`, `phase`, `month` | Valor observado e estimado, residual, estado de cada predição e `reference_month` quando aplicável. Preserva alvos ausentes e insuficiência de treinamento. |
| `model_parameters.json` | Nome do experimento | Parâmetros e coeficientes dos baselines sazonais, limiares de elegibilidade e meses usados no treinamento. Objeto vazio quando o experimento não for fornecido. |
| `events.csv` | `pivot_id`, `index`, `from_month`, `to_month` | Mudanças descritivas entre meses observados: valores, diferença, limiar, distância temporal e lacunas. `event_type=descriptive_spectral_change`. |
| `provenance.json` | Pacote | Dataset de origem, lista de meses, hashes/tamanhos dos insumos e experimentos, disponibilidade e relatórios científicos dos modelos. |
| `schemas.json` | `$defs.<nome_do_arquivo>` | JSON Schema 2020-12 dos registros tipados, campos obrigatórios, tipos, unidades e `x-primary-key`. |

O exportador conserva as colunas científicas das tabelas de observações e mensal. Campos adicionais de uma nova fonte podem ser incluídos sem mudar a versão principal do contrato; campos obrigatórios, tipos, unidades e semântica de campos existentes precisam ser preservados. O pacote e seus hashes mudam quando algum conteúdo muda. O contrato não deduz a fonte a partir do nome da cena: a interface deve apresentar os campos de proveniência registrados pelo pipeline.

## Tipos, unidades e estados

- CSV em UTF-8, separador vírgula, uma linha de cabeçalho e terminador LF. Campo vazio significa `null`; nunca zero implícito. Booleanos são `true` e `false` em minúsculas. Identificadores, inclusive `pivot_id`, são texto para preservar zeros iniciais.
- Datas seguem `YYYY-MM-DD`; meses seguem `YYYY-MM`. Os esquemas descrevem os registros após a conversão tipada dos campos CSV. Strings de IDs e URLs devem permanecer intactas.
- `processing_baseline` é uma versão textual, como `05.10`, preservada com os zeros. Não convertê-la para número decimal. `collection`, `provider`, `native_scene_id`, `acquisition_key`, `radiometric_method`, `calibration_path` e `calibration_sha256`, quando presentes nas observações, identificam a origem e a calibração aplicada.
- NDVI e NDMI observados são adimensionais, entre −1 e 1. São medianas espaciais por cena; a estatística mensal usa **mediana das medianas de cenas aceitas, com pesos iguais** (`temporal_aggregation=median_of_scene_medians_equal_weight`). O valor previsto pela regressão não é truncado ao intervalo: trata-se da saída numérica do modelo.
- `valid_pixel_pct*` usa escala de 0 a 100. `quality_review` é verdadeiro quando não há cena aceita ou o menor percentual válido aceito no mês é inferior a 80%. É um indicador de revisão, separado do limiar científico de aceitação de 70% da área válida.
- `precip_mm` corresponde à estimativa CHIRPS mensal em milímetros acumulados. Pivôs próximos podem compartilhar a mesma célula de aproximadamente 0,05°. Não representa medição meteorológica individual no talhão.
- `monthly_status=ok` implica pelo menos uma observação aceita. Ausência de observação mantém índices vazios e motivo explícito. `batch_status` e `query_complete` distinguem ausência observacional de aquisição incompleta.
- `mae` e `rmse` são adimensionais e pertencem ao alvo em `target`. `coverage_fraction` corresponde a `n_valid_pairs / expected_months`. O residual é `observed − predicted`; `bias_mean`, quando fornecido, é sua média.
- `experiment=seasonal_original` identifica o **protocolo sazonal original**, aplicado ao dataset de entrada identificado por hash. Treina em 2022–2023 e valida em 2024. `naive_contingency` é o experimento retrospectivo separado com o mesmo mês de 2023 como referência de 2024. Nenhum deles usa 2025.
- Eventos são alterações espectrais descritivas. `elapsed_calendar_months` e `unobserved_months_between` informam a distância entre observações; uma diferença através de lacunas não é uma mudança medida em um único mês. Não são diagnósticos de falha de irrigação.

O esquema permite colunas adicionais, mas o exportador aplica verificações de integridade complementares: pivôs conhecidos, chaves únicas, grade completa e contínua de meses, correspondência entre datas e meses, contagem exata das observações aceitas, agregação mensal recalculada, limites de qualidade, chuva aceita não negativa, correspondência de eventos com os valores mensais e vínculo dos modelos ao hash exato da tabela mensal. Experimentos não solicitados ou indisponíveis ficam identificados em `experiment_availability`.

## Uso por Python e PowerShell

O diretório científico de entrada deve conter `observations.csv` e `monthly.csv`; `pronounced_changes.csv` é opcional. A função retorna o caminho do manifesto. O exemplo usa a base original para demonstrar a exportação sem modificar seu relatório de insuficiência:

```powershell
@'
from pathlib import Path
from aquaclima.modeling.naive_seasonal import run_naive_benchmark
from aquaclima.reporting.contracts import export_contracts

dataset = Path('data/history/curated/2022-01-01_2024-12-31_a48cba82f744')
experiment = Path('data/recovery/contingency-original')
run_naive_benchmark(dataset / 'monthly.csv', experiment)
print(export_contracts(
    Path('data/processed/pivots.geojson'), dataset, experiment / 'webgis',
    model_dir=dataset / 'baseline', benchmark_dir=experiment,
))
'@ | uv run --no-sync python -
```

Para uma versão recuperada, trocar apenas os caminhos do dataset e das saídas; fornecer o diretório dos modelos executados sobre aquela mesma tabela mensal. O hash evita misturar resultados de versões diferentes. Todos os arquivos de dados permanecem em `data/`, fora do Git. O código, os esquemas geradores e a documentação são versionados no repositório.

## Benchmark retrospectivo de contingência

`run_naive_benchmark` mantém os 12 espaços de comparação de cada pivô/índice. Calcula métricas somente para pares com `monthly_status=ok`, `batch_status=complete`, `query_complete=true` e valores disponíveis nos dois anos. Não imputa meses. Usa exclusivamente 2023 como referência e 2024 como avaliação; registra anos excluídos.

Na base original, a execução separada produziu **49 pares pivô/mês**, ou 98 resíduos contando NDVI e NDMI. Cada pivô tem 9–10 pares, cobertura de 75% a 83,3%. MAE varia de 0,1766 a 0,3112 para NDVI e de 0,1554 a 0,3143 para NDMI. Esses números descrevem a concordância retrospectiva dos agregados espectrais; cultura, estágio fenológico, manejo e datas das imagens podem variar entre anos. A dependência temporal e entre os cinco pivôs impede tratar os resíduos como amostras independentes. Comparações entre métodos devem apresentar também os meses efetivamente avaliados. O relatório sazonal original de insuficiência permanece preservado.

## Comparação adicional em meses comuns

`aquaclima.modeling.comparison.run_common_month_comparison(monthly_path, baseline_dir, naive_dir, output_dir)` compara as predições existentes sem ajustar modelos novamente. Para cada pivô e índice, produz um contraste dos três métodos e três contrastes aos pares. Cada contraste usa a **interseção dos meses de 2024 pontuados por todos os métodos participantes**. Retém o mínimo original de seis meses comuns para publicar MAE e RMSE; abaixo disso, as métricas ficam vazias e o estado é `insufficient_common_validation_months`.

Os arquivos `common_month_predictions.csv`, `common_month_metrics.csv` e `comparison_report.json` registram valores, meses exatos, cobertura, critérios e hashes dos insumos. A rotina verifica que os relatórios pertencem à mesma tabela mensal, que os valores observados correspondem à referência aceita e que os resíduos são coerentes. Não altera os resultados dos experimentos originais. Esses arquivos complementares podem ser consultados junto ao pacote WebGIS; seu esquema é independente da versão 1.0.0 dos arquivos centrais.

```powershell
@'
from pathlib import Path
from aquaclima.modeling.comparison import run_common_month_comparison

dataset = Path('data/history/curated/2022-01-01_2024-12-31_a48cba82f744')
naive = Path('data/recovery/contingency-original')
run_common_month_comparison(dataset / 'monthly.csv', dataset / 'baseline', naive, naive / 'comparison')
'@ | uv run --no-sync python -
```

Na base original, nenhum contraste sazonal atende aos seis meses comuns: a mediana só dispõe do mês de março, e a Ridge permanece inelegível. Os números do benchmark ingênuo conservam sua interpretação retrospectiva separada.
