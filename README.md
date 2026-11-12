# AquaClima

O AquaClima investiga se o histórico da vegetação e o contexto meteorológico ajudam a identificar comportamentos espectrais atípicos em áreas irrigadas. O primeiro piloto cruza polígonos de pivôs da ANA, reflectância de superfície Sentinel-2 e precipitação mensal CHIRPS na bacia do rio São Marcos. O projeto integra o Capstone do Future Tech Leaders Brasil.

## WebGIS científico — Fases 4 e 5

A aplicação estática em `web/` permite selecionar os cinco polígonos ANA reais e explorar índices NDVI/NDMI, chuva regional, cobertura, mudanças espectrais e reconstrução por baselines. Consome exclusivamente o snapshot público validado de `2022_2024_recovery_v1`: 256 observações, 57 cenas e 141 de 180 espaços mensais observados (78,3%). Não executa aquisição ou ajuste de modelos. Mapa, gráficos e dependências são empacotados, sem CDNs ou tiles externos.

Clone a branch de implementação para executar o frontend em uma máquina nova. O snapshot científico público acompanha o repositório; essa execução não exige Python, rasters, caches nem a pasta científica `data/` original. Node.js 22.12 ou posterior e npm são suficientes:

```powershell
git clone --branch codex/aquaclima-webgis --single-branch https://github.com/Altaeir-13/FTL-Final-Project.git
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

URL de produção esperada: [AquaClima no GitHub Pages](https://altaeir-13.github.io/FTL-Final-Project/). A publicação só deve ser considerada confirmada com deployment aprovado e testes nessa URL, registrados no [relatório de finalização da Fase 5](docs/finalizacao-webgis.md). O workflow presente no repositório, isoladamente, não comprova um site publicado.

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
