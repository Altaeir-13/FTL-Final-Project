# Aquisição histórica e preparação dos modelos

A fase histórica reutiliza os cinco polígonos do piloto e os clientes de aquisição existentes. Cada mês possui catálogo STAC, seleção por qualidade, manifesto de recortes, tabela de índices e checkpoint de conclusão em `data/history/batches/<policy_key>/YYYY-MM/`. O identificador da política depende do hash dos pivôs, limite mensal de cenas, limiar de pixels válidos e versão do processamento. Mudanças desses parâmetros criam outro conjunto de lotes. Os recortes ficam no cache compartilhado por hash dos pivôs e ID de cena. Os GeoTIFFs mensais CHIRPS também são compartilhados, enquanto `data/history/chirps.json` conserva o inventário histórico separado do piloto.

A auditoria identificou que o piloto tinha um único caminho de catálogo e recortes por consulta, um manifesto CHIRPS limitado aos meses da última chamada e uma integração por observação. A implementação histórica acrescenta caminhos explícitos, manifestos acumulativos e exportações distintas por intervalo. Uma interrupção mantém os arquivos publicados atomicamente, os checkpoints por candidato/ativo e os meses já concluídos. A retomada ocorre na granularidade de arquivo, recorte, candidato e mês. Arquivos incompletos são refeitos. Os caminhos e comandos padrão do piloto continuam disponíveis.

O catálogo é consultado mês a mês, conservando as respostas paginadas originais. Se uma consulta alcançar 500 itens ou apresentar uma contagem superior ao total recuperado sem próximo link, o intervalo é subdividido e consultado novamente, com deduplicação e checagem de conteúdo. Um intervalo mínimo ainda truncado produz erro explícito. O planejamento conserva contagem de candidatas, estimativa de bytes e origem da estimativa. O tamanho total de cenas completas permanece separado da estimativa de recortes. A estimativa usa a experiência de Range e a área das janelas, com margem de segurança. O cliente impõe os limites rígidos em tempo de execução.

A seleção histórica começa pela SCL de todas as candidatas geograficamente compatíveis, com classes válidas 4 e 5 e avaliação nos centros dos pixels dentro de cada pivô. O ranking considera quantos pivôs alcançam o limiar, a menor proporção válida e a proporção média, com desempate determinístico. A configuração inicial admite até duas datas distintas por mês. O manifesto mantém frações locais, IDs e motivos de exclusão para todas as candidatas. Os índices finais passam novamente pela máscara conjunta e pelos testes radiométricos. Uma SCL favorável pode resultar em rejeição posterior por NoData ou denominadores inválidos.

| Tabela | Unidade e regras |
| --- | --- |
| `observations.csv` | Uma linha por pivô e cena com status aceito. Mantém data, NDVI, NDMI, qualidade, cena, mês, clima e proveniência dos lotes. |
| `attempts.csv` | Todas as linhas de índices processadas, incluindo rejeições e falhas de recortes. As candidatas excluídas na triagem SCL permanecem nos manifestos de seleção. |
| `monthly.csv` | Uma linha por pivô e mês solicitado. Os índices são a mediana das medianas espaciais das cenas aceitas, com peso igual por cena. Mantém contagens, intervalo entre datas, qualidade mínima/mediana, IDs, status do lote e chuva mensal. |

Meses ausentes conservam índices vazios e motivos como consulta ainda incompleta ou nenhuma observação aceita. O número de datas e a distribuição dentro do mês permitem verificar a representatividade temporal. A seleção de dias claros e as lacunas na estação chuvosa podem introduzir viés. Duas datas próximas representam uma parcela pequena do mês. O levantamento vetorial de 2022 também exige investigação antes de pressupor atividade dos equipamentos em todos os anos.

As primeiras consultas reais confirmaram cobertura escassa da coleção `sentinel-2-c1-l2a` no primeiro trimestre de 2022. Uma consulta diagnóstica independente retornou uma cena C1 e 18 na coleção `sentinel-2-l2a` para a mesma geometria. A coleção antiga apresenta particularidades de offsets aplicados fisicamente aos COGs e relatos de inconsistência nos metadados. Nesta fase, os dados científicos adquiridos usam a C1 e sua conversão radiométrica validada. A adoção de outra coleção requer conferência própria dos valores de reflectância e registro explícito da transformação. [Discussão do mantenedor sobre offsets](https://github.com/Element84/earth-search/discussions/26) · [Registro de inconsistências na coleção antiga](https://github.com/Element84/earth-search/issues/71)

O baseline sazonal usa a mediana por pivô e mês do calendário, exigindo dois anos observados no treinamento de 2022–2023 para cada mês estimado. A alternativa harmônica usa dois harmônicos, intercepto sem penalização e Ridge com alfa fixo em 1. Exige pelo menos 18 meses observados de treinamento, cobrindo os 12 meses do calendário. A validação é cronológica em 2024. Os parâmetros e coeficientes são persistidos. MAE e RMSE comparam as estimativas às observações espectrais mensais aceitas e só são reportados com pelo menos seis meses pontuados por pivô, índice e método.

O módulo exclui 2025 antes do ajuste, previsão e cálculo de métricas desta fase. As datas 27/06, 02/07 e 26/08 de 2025 já foram examinadas no piloto exploratório e essa exposição está registrada nos planos e relatórios. A mediana sazonal e a alternativa harmônica usam apenas o calendário e as observações de treinamento. A chuva mensal completa fornece contexto retrospectivo. A proximidade dos cinco pivôs e a célula CHIRPS compartilhada limitam a independência espacial. A execução atual conserva métricas por pivô, sem assumir que as linhas constituem amostras independentes.

A exploração exporta distribuições, séries por pivô, comparação anual, matriz de cobertura, cobertura sazonal e contexto de chuva. A lista de mudanças pronunciadas usa limiares descritivos definidos antes da análise, de 0,20 para NDVI e 0,15 para NDMI. Cada diferença registra o intervalo em meses e eventuais meses ausentes. A lista de meses de baixa qualidade inclui meses sem observações e aqueles com proporção válida mínima inferior a 80%, um parâmetro de revisão distinto do limiar operacional de aceitação de 70%. A interpretação agronômica depende de cultura, calendário de manejo e validação independente.

Os comandos abaixo funcionam em PowerShell na raiz do repositório, após `uv sync --locked`. O primeiro plano e a execução padrão usam janeiro a março de 2022.

```powershell
uv run --no-sync aquaclima history-run --dry-run
uv run --no-sync aquaclima history-plan
uv run --no-sync aquaclima history-run
uv run --no-sync aquaclima history-run --offline --output-dir data/history/reproduzido/q1
```

Uma expansão de intervalo exige novo plano. `--allow-bulk` admite mais de três meses e mantém os limites de transferência, armazenamento e requisições do arquivo TOML. O modo offline utiliza os mesmos parâmetros e manifestos locais.

```powershell
uv run --no-sync aquaclima history-plan --start 2022-01-01 --end 2024-12-31 --allow-bulk
uv run --no-sync aquaclima history-run --start 2022-01-01 --end 2024-12-31 --allow-bulk --dry-run
uv run --no-sync aquaclima history-run --start 2022-01-01 --end 2024-12-31 --allow-bulk
uv run --no-sync aquaclima history-run --start 2022-01-01 --end 2024-12-31 --allow-bulk --offline --output-dir data/history/reproduzido/2022_2024
uv run --no-sync aquaclima history-consolidate --start 2022-01-01 --end 2024-12-31 --allow-bulk
uv run --no-sync aquaclima history-explore --start 2022-01-01 --end 2024-12-31 --allow-bulk
uv run --no-sync aquaclima history-baseline --start 2022-01-01 --end 2024-12-31 --allow-bulk
```

Os relatórios separam transferência da invocação atual, transferência acumulada desde a primeira operação histórica, meses processados e qualidade efetivamente observada. Os modelos só poderão ser avaliados nos meses que satisfizerem os critérios de treinamento e referência, e os relatórios registram insuficiência quando esses critérios falham.

A execução encontrou HTTP 429 persistente na origem UCSB ao iniciar abril de 2022. O downloader encerrou os pedidos a esse servidor e marcou os meses seguintes como pendentes. O espelho oficial USGS FEWS NET disponibiliza o CHIRPS v3 final mensal em GeoTIFF global. A conferência de uma janela de 5 × 5 células em março de 2022 encontrou igualdade exata com o arquivo regional UCSB, além de confirmar CRS, resolução, tipo, escala, offset e identificação do produto no TIFF. O arquivo global possui outra origem de grade, portanto seus índices de linha e coluna diferem dos regionais, enquanto a localização da célula é registrada no CSV. [Espelho USGS do produto final](https://edcintl.cr.usgs.gov/downloads/sciweb1/shared/fews/web/global/monthly/chirps/final/downloads/monthly/) · [Orientação do produtor para HTTP 429](https://github.com/chc-ucsb/chc-data-download#downloading-politely)

A configuração `history-usgs.toml` seleciona explicitamente esse espelho para meses pendentes, com os mesmos limites de 2 GB. Ela conserva arquivos UCSB já válidos, as falhas anteriores e os planos de cada origem. O planejamento estima os arquivos globais antes da recuperação. A aquisição por arquivo completo permite validar todos os blocos e o SHA-256, com volume maior que o produto regional. As requisições aos dois servidores são espaçadas pelo cliente.

```powershell
uv run --no-sync aquaclima history-plan --config configs/history-usgs.toml --allow-bulk
uv run --no-sync aquaclima history-run --config configs/history-usgs.toml --allow-bulk
uv run --no-sync aquaclima history-run --config configs/history-usgs.toml --allow-bulk --offline --output-dir data/history/reproduzido/2022_2024
```
