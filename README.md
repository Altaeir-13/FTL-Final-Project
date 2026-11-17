# AquaClima

O AquaClima investiga se o histórico da vegetação e o contexto meteorológico ajudam a identificar comportamentos espectrais atípicos em áreas irrigadas. O primeiro piloto cruza polígonos de pivôs da ANA, reflectância de superfície Sentinel-2 e precipitação mensal CHIRPS na bacia do rio São Marcos. O projeto integra o Capstone do Future Tech Leaders Brasil.

## Entrega do Capstone — auditoria de 17/11/2026

A Fase 7 está publicada na [URL oficial](https://altaeir-13.github.io/FTL-Final-Project/), após o merge do [PR #3](https://github.com/Altaeir-13/FTL-Final-Project/pull/3) em `ad107d0c29c63ad9eb9f91a5970d96906676e3df` e o [deployment aprovado](https://github.com/Altaeir-13/FTL-Final-Project/actions/runs/44067496065). Os **25 testes Playwright passaram diretamente no site público**, sem servidor local, em desktop e viewport móvel de 390 px. Os 24 arquivos efetivamente servidos são idênticos ao build validado; `.nojekyll` é um marcador de deployment, sem função de runtime.

O [registro de lançamento](docs/release-final-ftl.md) reúne verificações, hashes e limitações. A [pasta consolidada de entrega](entrega/aquaclima-ftl-2026/README.md) contém relatório científico em PDF, apresentação editável, PDF de apoio, roteiro, fichas exemplificativas e links. A release permanece destinada à revisão, sem submissão oficial pelo agente. O prazo de entrega é **24/11/2026**.

## Fase 7 — investigação guiada e ficha de evidências

O WebGIS passa a organizar uma investigação por território, pivô e duas observações reais. Em Paracatu, a comparação utiliza os agregados mensais publicados de 2022–2024; em Guadalupe, utiliza as cenas aceitas de 2023–2024. NDVI, NDMI, diferenças assinadas `B − A`, chuva CHIRPS, qualidade, lacunas e proveniência acompanham a seleção. A síntese é determinística e descritiva; nenhuma causa agronômica é atribuída automaticamente.

O botão **Gerar ficha de evidências** abre uma cópia independente da seleção para impressão A4 ou salvamento como PDF no navegador. A ficha inclui fontes, hashes, limitações, data de geração e um identificador científico estável que não depende da data de impressão. As imagens reais de Guadalupe, de 18/07/2023 e 22/07/2024, aparecem somente quando correspondem às observações selecionadas. O contexto visual é o grupo dos cinco pivôs, identificado na legenda.

Links de investigação preservam região, pivô, observações, índice e pacote, mantendo os parâmetros anteriores `pivot`, `indice`, `from` e `to`. O modo **Iniciar demonstração** conduz cinco passos em aproximadamente três minutos, com controle manual e restauração da navegação. A visão territorial distingue Caxias/MA, origem do pesquisador, Paracatu/MG, estudo concluído, e Guadalupe/PI, prova exploratória.

Consulte a [arquitetura, reprodução e capturas da investigação](docs/investigacao-guiada-ftl.md), o [roteiro atualizado da banca](docs/roteiro-final-ftl.md) e a [apresentação editável da Fase 7](docs/apresentacao/aquaclima-ftl-fase7.pptx). São funcionalidades tecnológicas derivadas dos resultados publicados: não houve nova aquisição, treinamento ou alteração científica. A Fase 6 foi integrada pelo [PR #2](https://github.com/Altaeir-13/FTL-Final-Project/pull/2), no commit `ffb7ba41d5286fd58c47acd8007903fd38b799d4`, e a Fase 7 pelo PR #3. Branches experimentais não publicam.

## Fase 6 — seleção regional e entrega FTL

Paracatu/MG permanece congelado em `2022_2024_recovery_v1`. A auditoria real de 14 municípios MA/PI selecionou **Guadalupe/PI**; a prova exploratória processou cinco pivôs, seis cenas de 2023–2024 e **29 observações aceitas em 30 tentativas**, com CHIRPS e reprodução offline. O calendário completo de 23 meses contém 115 espaços pivô/mês, dos quais 29 são observados. Não há modelos ou métricas de generalização para Guadalupe. Caxias é referência territorial do autor; não é apresentada como município monitorado.

Consulte a [seleção territorial](docs/selecao-regional-ma-pi.md), o [resultado regional e protocolo de reprodução](docs/resultado-regional-guadalupe.md), o [relatório científico final](docs/relatorio-final-ftl.md), a [apresentação editável](docs/apresentacao/aquaclima-ftl.pptx), o [roteiro e perguntas da banca](docs/roteiro-final-ftl.md) e o [checklist de entrega](docs/checklist-entrega-ftl.md). A expansão regional foi integrada à `main` pelo PR #2. Não há publicação automática de branches experimentais.

As evidências compactas estão em `data/regions/selection/` e `docs/evidencias/guadalupe-pi/`. Os recortes COG, XML ESA e caches de aquisição permanecem fora do Git. A aquisição é incremental e limitada a 150 MB por execução; os rasters CHIRPS locais já existentes são copiados e verificados antes da nova extração regional.

O [registro de execução da fase 6](docs/execucao-fase6.md) reúne contadores de aquisição, hashes preservados, 216 testes Python, 37 de frontend, 16 de navegador e reprodução do build em clone limpo.

```powershell
uv run --no-sync python scripts/verify_regional_selection.py
uv run --no-sync python -m aquaclima.regions.pilot --region-dir data/regions/guadalupe-pi
uv run --no-sync python -m aquaclima.regions.pilot --region-dir data/regions/guadalupe-pi --offline
```

O comando offline requer o cache local íntegro; o snapshot público permite compilar e explorar o WebGIS em um clone limpo sem os rasters. Para refazer toda a seleção com respostas atuais: `uv run --no-sync python -m aquaclima.regions.audit --directory data/regions/new-selection`; preserve a decisão congelada original.

## WebGIS científico — Fases 4 e 5

A aplicação estática em `web/` permite selecionar os cinco polígonos ANA reais e explorar índices NDVI/NDMI, chuva regional, cobertura, mudanças espectrais e reconstrução por baselines. Consome exclusivamente o snapshot público validado de `2022_2024_recovery_v1`: 256 observações, 57 cenas e 141 de 180 espaços mensais observados (78,3%). Não executa aquisição ou ajuste de modelos. Mapa, gráficos e dependências são empacotados, sem CDNs ou tiles externos.

Após a integração do PR, clone a `main` para executar o frontend em uma máquina nova. O snapshot científico público acompanha o repositório; essa execução não exige Python, rasters, caches nem a pasta científica `data/` original. Node.js 22.12 ou posterior e npm são suficientes:

```powershell
git clone --branch main --single-branch https://github.com/Altaeir-13/FTL-Final-Project.git
Set-Location FTL-Final-Project/web
npm ci
npm run data:validate
npm test
npm run build
npm run verify:dist
npm run preview
```

Abra `http://127.0.0.1:4173/FTL-Final-Project/`. A base de produção é explicitamente `/FTL-Final-Project/`. O build inclui validação de contrato 1.0.0, SHA-256, proveniência e consistência dos arquivos; falha quando um arquivo obrigatório está ausente ou corrompido. `verify:dist` também examina o artefato estático e seus caminhos de runtime. O pacote público permitido está versionado em `web/data/`, separado dos dados de aquisição locais e preservado byte a byte. Em um checkout já aberto, comece apenas com `Set-Location web`.

Consulte [arquitetura, testes e publicação no GitHub Pages](docs/webgis.md) e o [roteiro de demonstração em três minutos](docs/roteiro-demonstracao.md). O workflow `.github/workflows/webgis.yml` valida ciência e frontend em todos os PRs e nos pushes da `main`. Publica somente `web/dist/`, exclusivamente a partir da `main`, após as verificações. A branch de implementação exige revisão humana de PR; não há merge automático.

WebGIS de produção: [AquaClima no GitHub Pages](https://altaeir-13.github.io/FTL-Final-Project/). Confirme a versão publicada pelo deployment aprovado da `main` e pelos testes executados nessa URL. As evidências estão no [relatório de finalização da Fase 5](docs/finalizacao-webgis.md) e no [PR de integração #1](https://github.com/Altaeir-13/FTL-Final-Project/pull/1). O workflow presente no repositório, isoladamente, não comprova um site publicado.

O [relatório de entrega da Fase 4](docs/entrega-webgis.md) é um registro histórico dos resultados locais e das permissões disponíveis em 11/11/2026. A Fase 5 atualiza a autenticação, a política de publicação e a verificação de um clone limpo, sem alterar os resultados científicos.

O PR de `codex/aquaclima-webgis` para `main` inclui também a evolução científica anterior ao frontend: a `main` remota ainda estava no estágio piloto na inspeção da Fase 5. O commit científico `1440f3e` e seus resultados congelados são preservados no histórico; a revisão humana deve considerar esse contexto, além das mudanças da aplicação.

## Instalação no Windows 11

Use Git e uv em PowerShell. O lock fixa as dependências para Python 3.12. O processamento usa CPU e os dados ficam no computador.

```powershell
git clone https://github.com/Altaeir-13/FTL-Final-Project.git
Set-Location FTL-Final-Project
uv python install 3.12
uv sync --locked
uv run --no-sync pytest -q
```

## Aquisição e reprodução

```powershell
uv run --no-sync aquaclima run --dry-run
uv run --no-sync aquaclima check-sources
uv run --no-sync aquaclima run
uv run --no-sync aquaclima run --offline --output-dir data/reproduzido
Get-FileHash data/curated/observacoes.csv,data/reproduzido/observacoes.csv
```

O último comando deve mostrar o mesmo SHA-256 para as duas tabelas. O modo offline relê o GeoJSON e os rasters locais e recalcula a integração. Preserve `data/raw/` e `data/processed/pivots.geojson` para reproduzir o piloto em outra máquina, além do inventário `data/acquisition.jsonl` para auditoria. Os relatórios de duas execuções diferem em tempo e telemetria.

O TOML define cinco pivôs, junho a agosto de 2025, até três cenas, limite de 35% de nuvens no catálogo e pelo menos 70% de pixels válidos no próprio pivô. Use `--config`, `--data-dir`, `--output-dir`, `--start` e `--end` para especificar parâmetros. Para uma configuração ou intervalo diferente, prefira outro diretório de dados. Uma ampliação acima dos limites conservadores exige `--allow-bulk` e planejamento prévio. O piloto usa até 2 GB decimais de corpo HTTP, 2 GB de novos arquivos de aquisição e 2.500 requisições por invocação online.

### Etapas individuais

```powershell
uv run --no-sync aquaclima acquire-pivots
uv run --no-sync aquaclima search-scenes
uv run --no-sync aquaclima plan
uv run --no-sync aquaclima acquire-crops
uv run --no-sync aquaclima download-precip
uv run --no-sync aquaclima process-indices
uv run --no-sync aquaclima integrate
uv run --no-sync aquaclima report
```

`plan` e `--dry-run` são locais. Após `search-scenes`, o plano inclui os IDs e os ativos da seleção. O relatório gerado por `run` mede aquela invocação. O comando `report` gera um resumo cumulativo do inventário, sem cronômetro do fluxo original.

## Arquivos

| Local | Conteúdo |
| --- | --- |
| `configs/pilot.toml` | Recorte temporal e parâmetros de seleção, qualidade e aquisição |
| `src/aquaclima/ingestion` | Consultas ANA/STAC e download de janelas Sentinel-2 e GeoTIFFs CHIRPS |
| `src/aquaclima/processing` | Máscaras, harmonização de grade e índices espectrais |
| `src/aquaclima/features` | Junção de observações a meses e tratamento de lacunas |
| `src/aquaclima/storage`, `reporting` | Cache, integridade, proveniência, gráfico e relatório |
| `data/raw` | Respostas e inventários das fontes, janelas Sentinel-2 e arquivos mensais CHIRPS |
| `data/processed` | GeoJSON, GeoPackage e tabelas espectral e meteorológica |
| `data/curated` | `observacoes.csv`, `serie_temporal.png` e `relatorio_aquisicao.json` |
| `tests` | Verificações matemáticas e de falhas, com pequenas entradas controladas |

A documentação explica [metodologia, fontes e limitações](docs/metodologia.md) e registra os [resultados da aquisição piloto](docs/resultado-piloto.md). Os arquivos raster, dados locais, caches e ambientes virtuais ficam fora do Git. O código usa licença MIT. Os dados de terceiros conservam as condições de suas fontes.

A [fase histórica](docs/historico.md) acrescenta lotes mensais retomáveis, seleção pela qualidade dentro dos pivôs, dataset mensal, exploração e baselines cronológicos. A configuração inicial usa janeiro a março de 2022. Gere a estimativa antes da aquisição e use o mesmo comando com `--offline` para reproduzir os arquivos locais.

O [relatório histórico executado](docs/resultado-historico.md) registra os 36 meses consultados, a cobertura efetiva e a recuperação de precipitação pelo espelho oficial USGS. A base produzida permite explorar os dados e auditar a elegibilidade dos modelos.

```powershell
uv run --no-sync aquaclima history-plan
uv run --no-sync aquaclima history-run
uv run --no-sync aquaclima history-run --offline --output-dir data/history/reproduzido/q1
```

A [recuperação de 2022](docs/recuperacao-2022.md) compara quatro catálogos e integra somente recortes Planetary Computer PB 05.10 aprovados pela [auditoria radiométrica](docs/radiometria.md). A nova versão tem 256 observações, 57 cenas e cobertura mensal de 78,3% em 2022–2024. A base C1 anterior e o piloto continuam verificáveis por seus hashes.

Os [resultados dos baselines](docs/modelagem-recuperada.md) registram mediana sazonal elegível nos cinco pivôs e Ridge em dois, com os critérios originais. Os [contratos WebGIS](docs/contratos-webgis.md) disponibilizam os arquivos locais versionados consumidos pela aplicação das Fases 4 e 5.

```powershell
uv run --no-sync aquaclima recovery-plan
uv run --no-sync aquaclima recovery-run
uv run --no-sync aquaclima recovery-plan --config configs/recovery-2022.toml --allow-bulk
uv run --no-sync aquaclima recovery-run --config configs/recovery-2022.toml --allow-bulk
uv run --no-sync python scripts/verify_recovery_offline.py
```

Uma instalação nova também precisa dos catálogos e evidências da auditoria: os dados adquiridos não são distribuídos no Git. Consulte os procedimentos completos de diagnóstico e aquisição em [recuperacao-2022.md](docs/recuperacao-2022.md).
