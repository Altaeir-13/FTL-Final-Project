# AquaClima

O AquaClima investiga se o histórico da vegetação e o contexto meteorológico ajudam a identificar comportamentos espectrais atípicos em áreas irrigadas. O primeiro piloto cruza polígonos de pivôs da ANA, reflectância de superfície Sentinel-2 e precipitação mensal CHIRPS na bacia do rio São Marcos. O projeto integra o Capstone do Future Tech Leaders Brasil.

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
