# Prova regional real — Guadalupe, Piauí

Executada em 15/11/2026 após a [seleção oficial ANA/IBGE/STAC](selecao-regional-ma-pi.md). O resultado demonstra portabilidade de aquisição e processamento em uma amostra exploratória. Não valida modelos regionais, diagnóstico agronômico ou sazonalidade anual completa. A incorporação exploratória ao Capstone foi decidida em 15/11, antes do limite de 18/11.

## Amostra, período e protocolo

Cinco polígonos oficiais ANA 2022, integralmente contidos na malha municipal IBGE recuperada: FIDs **5795, 5797, 5798, 5802 e 5804**, com chaves `PI:<FID>` e namespace `guadalupe-pi`. O raio do grupo é 1,717 km e seu centroide fica a 215,49 km da sede pública de Caxias. Pivôs de Paracatu e seus modelos não participaram do experimento.

Foram declarados seis meses após a inspeção do catálogo e antes da aquisição de rasters: janeiro, julho e novembro de 2023; março, julho e novembro de 2024. Março de 2023 não apresentou candidato com nuvens de cena ≤40% na triagem; janeiro de 2023 foi escolhido ainda no planejamento. Isso introduz seleção por disponibilidade e impede tratar a amostra como aleatória ou contínua. Janeiro/2023 a novembro/2024 é uma grade de **23 meses**, com todos os meses não adquiridos explicitamente registrados como `not_queried`.

O pipeline selecionou até três candidatos por mês, priorizando cobertura integral dos polígonos e menor nuvem da cena. A SCL local determinou a cena de melhor cobertura, limitada a uma data por mês. O filtro de nuvens de 40% é de planejamento; a aceitação final requer **≥70% de pixels conjuntos válidos** no pivô, SCL 4/5 e reflectâncias não negativas. B04/B08 a 10 m foram agregadas à grade nativa B11 a 20 m antes das razões. NDVI e NDMI são medianas espaciais; o agregador mensal preserva a mediana das medianas, com pesos iguais e sem imputação.

Foram conferidos os XML ESA dos **14 produtos candidatos** contra seus próprios atributos C1 `raster:bands`: identidade SAFE, baseline, quantificação, offsets por banda, NoData e saturação. Os três baselines das cenas finais são 05.09, 05.10 e 05.11. Todos informaram escala 0,0001 e offset −0,1 nas bandas espectrais. As grades, resoluções e metadados foram verificados no COG adquirido. Essa auditoria por produto é independente da autorização anterior para produtos Planetary Computer em Paracatu; não é uma validação radiométrica de campo.

## Cenas e resultados observados

Todas as aquisições abaixo são Sentinel-2B L2A C1, tile `23MPN`, provedor Earth Search/Element 84. Os intervalos representam o mínimo e o máximo entre os pivôs aceitos nessa data; não representam erro de estimação.

| Data | Baseline | Pivôs aceitos / 5 | NDVI mínimo–máximo | NDMI mínimo–máximo | CHIRPS mensal, mm mínimo–máximo |
|---|---|---:|---:|---:|---:|
| 29/01/2023 | 05.09 | 5 | 0,5529–0,8646 | −0,0379–0,3773 | 134,59–140,03 |
| 18/07/2023 | 05.09 | 5 | 0,4108–0,8320 | −0,1082–0,3000 | 1,95–2,89 |
| 25/11/2023 | 05.09 | 5 | 0,1637–0,8979 | −0,2725–0,4155 | 76,12–87,77 |
| 24/03/2024 | 05.10 | 4 | 0,7243–0,8652 | 0,2230–0,3804 | 204,51–209,16 |
| 22/07/2024 | 05.10 | 5 | 0,3922–0,9257 | −0,0996–0,4682 | 2,08–3,13 |
| 29/11/2024 | 05.11 | 5 | 0,4552–0,8601 | −0,0137–0,4188 | 116,24–135,70 |

Os identificadores completos estão em [scene-summary.csv](evidencias/guadalupe-pi/scene-summary.csv), com observações, tentativas e chuva no [snapshot de evidências](evidencias/guadalupe-pi/manifest.json). Os 14 XML candidatos e os recortes ficam no cache local, identificados por SHA-256 no inventário.

**29 observações aceitas em 30 tentativas (96,7% dos espaços planejados)**. A menor qualidade entre observações aceitas foi 80,14%. Em março de 2024, uma observação teve 52,54% de pixels conjuntos válidos e foi rejeitada. Nenhum índice dessa observação foi publicado como válido. Na grade contínua de 115 espaços pivô/mês, há **29 espaços observados (25,2%)**; o denominador distingue a cobertura do experimento direcionado da cobertura do calendário.

CHIRPS v3 Final foi extraído para os 30 espaços planejados a partir de seis rasters globais já adquiridos, verificados por hash e copiados para o namespace regional. A reutilização foi do raster meteorológico, com nova extração nas coordenadas reais de Guadalupe. Os pivôs ocupam células de aproximadamente 0,05°; chuva é contexto regional e não medição em cada talhão. Meses não adquiridos permanecem ausentes, sem preenchimento.

## Recursos e reprodução

O inventário acumulado do piloto registra **53.137.002 bytes transferidos em 452 requisições HTTP**, incluindo catálogos, leituras Range de COG e XML ESA. O armazenamento registrado ao fim da aquisição foi **144.149.011 bytes**, incluindo as cópias locais dos seis rasters CHIRPS. A reprodução acrescenta somente tabelas pequenas. São contadores observados nesta execução, não estimativa de custo de operação contínua.

```powershell
.venv/Scripts/python.exe -m aquaclima.regions.pilot --region-dir data/regions/guadalupe-pi
.venv/Scripts/python.exe -m aquaclima.regions.pilot --region-dir data/regions/guadalupe-pi --offline
.venv/Scripts/python.exe scripts/export_regional_evidence.py
```

Com o cache local íntegro, o segundo comando proíbe requisições via `requests.Session.request`, verifica todos os arquivos do inventário e refaz índices, agregações e extração meteorológica. **Cinco arquivos finais foram byte a byte idênticos, com zero HTTP e zero bytes transferidos**. O snapshot pequeno permite consultar os resultados em clone limpo; a reprodução a partir de pixels requer os rasters locais, deliberadamente fora do Git. A aquisição online depende da disponibilidade atual das fontes; não se promete identidade de um produto republicado sem seu hash original.

## Decisão e limites

O piloto alcança uma prova de portabilidade e uma série exploratória com seis meses distribuídos entre 2023 e 2024. Não foram ajustados modelos para Guadalupe, nem calculados MAE/RMSE regionais. Culturas, manejo, solos, estágio fenológico e irrigação não foram verificados em campo. A diferença de índices e precipitação não demonstra causa, consumo hídrico ou economia de água. A seleção de uma cena por mês não permite comparação direta de desempenho com o estudo histórico de Paracatu.

A concordância XML/STAC verifica a conversão radiométrica declarada de cada produto. Não foi realizado um ensaio com a mesma aquisição reprocessada nas três baselines C1 regionais; diferenças de processamento também podem contribuir para contrastes entre datas. Não se afirma equivalência radiométrica absoluta entre versões nem validação contra reflectância medida em campo.

A decisão é integrar Guadalupe ao WebGIS como **estudo exploratório separado** e concluir os materiais FTL. A comparação de imagens só deve ser oferecida se os recortes reais e a proveniência forem adequados. Não se inicia expansão histórica adicional nesta entrega. O prazo final permanece **24/11/2026**, com congelamento de funcionalidades em 23/11 e sem novos experimentos após 20/11.
