# Recuperação histórica de 2022 — execução de 11/11/2026

## Resultado e decisão científica

A versão `2022_2024_recovery_v1` acrescentou **53 observações aceitas, 12 cenas e seis meses de 2022**: abril, maio, julho, agosto, setembro e outubro, nos cinco pivôs. O dataset consolidado contém 256 observações, 57 cenas, 285 tentativas e 180 espaços mensais. Há 141 espaços observados, contra 111 anteriormente. A base C1 original e o piloto foram preservados por inventário SHA-256; suas 203 observações aceitas mantêm os valores espectrais e a qualidade, e os 180 valores de precipitação permanecem iguais.

| Ano | Espaços observados antes | Depois | Cobertura antes | Depois |
|---|---:|---:|---:|---:|
| 2022 | 5/60 | 35/60 | 8,3% | 58,3% |
| 2023 | 57/60 | 57/60 | 95,0% | 95,0% |
| 2024 | 49/60 | 49/60 | 81,7% | 81,7% |
| Total | 111/180 | 141/180 | 61,7% | 78,3% |

| Pivô ANA | Meses antes | Meses depois | Meses recuperados em 2022 |
|---|---:|---:|---:|
| 8087 | 23/36 | 29/36 | 6 |
| 16708 | 23/36 | 29/36 | 6 |
| 17373 | 22/36 | 28/36 | 6 |
| 17382 | 21/36 | 27/36 | 6 |
| 19997 | 22/36 | 28/36 | 6 |

Em 2022 todos os cinco pivôs têm março, abril, maio, julho, agosto, setembro e outubro observados. Janeiro, fevereiro, junho, novembro e dezembro continuam ausentes. As tabelas `coverage_before_after.csv` e `collection_quality_coverage.csv` detalham cada pivô/mês e a qualidade por provedor/coleção. O limite de aceitação continua sendo 70% de pixels conjuntos válidos e, por padrão, duas datas por mês, selecionadas pela SCL local.

## Catálogos e radiometria

O diagnóstico começou em janeiro (estação chuvosa) e julho (seca), usando a união dos mesmos cinco polígonos ANA. Nenhum filtro global de nuvens excluiu produtos antecipadamente.

| Catálogo | Janeiro: produtos/aquisições | Julho: produtos/aquisições | Acesso aos ativos |
|---|---:|---:|---|
| Earth Search C1 | 0/0 | 0/0 | COG HTTPS público quando disponível |
| Earth Search legado | 6/6 | 6/6 | COG público; calibração inconsistente entre produtos |
| Planetary Computer | 6/6 | 9/6 | COG público, assinatura SAS efêmera gratuita |
| Copernicus Data Space | 6/6 | 6/6 | JP2; ativos S3 exigem conta gratuita e credenciais CDSE |

Os três catálogos alternativos possuem B04/B08/B11/SCL e footprints cobrindo os cinco polígonos. A lacuna da C1 consultada representa disponibilidade dessa coleção, não ausência de passagens orbitais. Não foi possível atribuir a causa interna da ingestão. Detalhes, datas e URLs em [catalogos-radiometria.md](catalogos-radiometria.md).

O mesmo produto SAFE de 20/03/2022, PB05.10, apresentou **86.780 pixels digitais idênticos**, com CRS/grades iguais, entre PC e C1 nas quatro bandas. A conversão PC usa quantificação e offsets do próprio XML SAFE. Não há parâmetro padrão presumido pela data: identidade, baseline, offsets, NoData e bandas são verificados por produto.

PB04 tem conversão física determinável, porém não passou no critério de consistência entre versões definido antes da comparação: em março, o pivô 8087 apresentou diferenças de 0,0352454 em NDVI e 0,0330517 em NDMI, acima de 0,02. PB03 também ficou excluído por falta de comparação local de harmonização. Portanto, **somente PB05.10 foi integrado**. Essa é uma autorização local limitada; não constitui validação global dos sensores ou verdade agronômica de campo.

O legado mostrou em julho diferença de reflectância próxima de −0,10 quando se segue seu offset STAC, comparado a uma aquisição PC/PB04 equivalente, com geração diferente. Esses recortes ficaram restritos ao diagnóstico. Não houve ajuste arbitrário para obter índices plausíveis. O [relatório radiométrico](radiometria.md) registra todos os testes, inclusive os que falharam.

Depois do piloto de dois meses, o plano dos 11 meses de 2022 sem observação C1 aceita inventariou 86 produtos PC, correspondentes a 66 aquisições. Dezenove aquisições tinham PB05.10 aprovado; 12 foram selecionadas. As 60 combinações pivô/cena adicionais produziram 53 aceitas e sete rejeitadas. Janeiro permaneceu vazio por exclusão radiométrica. Não foi baixado um ano inteiro de bandas.

## Arquitetura e proveniência

- `ingestion/planetary.py`: adaptador separado, assinatura em memória, XML SAFE, normalização dos nomes das bandas, SCL local, recortes por janelas e retomada por ativo. A aquisição C1 conserva seu comportamento padrão.
- `recovery.py`: planejamento, vínculo do lote ao hash da auditoria, orçamento, verificação offline e consolidação em versão separada. Alterar a auditoria cria outra identidade de lotes; lotes anteriores permanecem em disco.
- `ingestion/catalog_diagnostic.py`: comparação pública, paginação verificada, contagens e inventários por fonte. Consultas que atingem 500 sem prova de completude falham explicitamente.
- `modeling/naive_seasonal.py`, `comparison.py`: benchmark retrospectivo e comparação nos mesmos meses, separados do experimento original.
- `reporting/contracts.py`, `recovery.py`: contratos WebGIS versionados e inventário local de recursos.

A identidade de aquisição usa plataforma, instante do SAFE, órbita relativa e tile, sem baseline/data de geração. Entre versões PC, prefere-se o maior baseline e, em seguida, o identificador nativo. Na união por pivô/aquisição, a ordem é C1 aceita, PC aceita, C1 rejeitada, PC rejeitada. Aquisições C1 já aceitas para todos os pivôs dispensam novos recortes. Cada exclusão e cada manifesto continuam auditáveis. Nenhuma duplicata física permaneceu nas 256 observações aceitas.

A tabela mensal usa mediana das medianas de cenas aceitas, com pesos iguais por cena. Preserva lacunas, contagens, datas, área válida, identificadores de origem, coleções, manifests e hashes. A precipitação continua como contexto regional CHIRPS mensal; os cinco pivôs compartilham a célula meteorológica. Não há imputação, diagnóstico hídrico automático ou uso de chuva completa para alegar previsão antecipada.

## Modelagem e contratos

A mediana sazonal tornou-se elegível nos cinco pivôs, com sete meses de validação em 2024. A Ridge tornou-se elegível em 8087 e 16708, com 19 meses de treinamento, todos os 12 meses do calendário e dez referências de validação. Os outros três têm 18 meses, mas apenas 11 meses do calendário: continuam inelegíveis para Ridge. Os critérios originais foram mantidos, inclusive mínimo de seis meses pontuados para métricas.

Nos sete meses comuns dos três métodos, o MAE Ridge é 0,296783/0,334005 (NDVI/NDMI) em 8087 e 0,188342/0,160462 em 16708. A Ridge tem menor MAE nesses quatro contrastes, mas o RMSE de NDVI em 16708 é ligeiramente menor para a mediana. Isso não sustenta um vencedor universal. As tabelas completas, MAE/RMSE e as limitações estão em [modelagem-recuperada.md](modelagem-recuperada.md).

O benchmark ingênuo separado compara os mesmos meses de 2023 e 2024: 49 pares pivô/mês, 98 resíduos contando ambos os índices. Não altera o relatório original de insuficiência. 2025 permanece excluído do ajuste e das métricas; a exposição exploratória prévia a 27/06, 02/07 e 26/08/2025 está registrada.

O [contrato WebGIS 1.0.0](contratos-webgis.md) fornece geometria GeoJSON/WGS84, observações, mensal, precipitação, qualidade, eventos descritivos, métricas, predições, parâmetros, schemas e proveniência. O manifesto aponta para um pacote imutável identificado pelo conteúdo. Nenhum frontend foi implementado.

## Recursos e verificações executadas

O orçamento inicial foi 250 MB para o piloto de dois meses, com estimativa inicial conservadora de 96 MB. Após aprovação PB05.10 e validação do piloto, a expansão recebeu plano de 254 MB, limite rígido de 1 GB por execução e aproximadamente 204 GB livres. Parte dos arquivos já estava em cache; a estimativa não é o volume efetivamente transferido.

Todos os inventários da recuperação e dos diagnósticos somam **58.016.353 bytes de payload HTTP e 566 requisições**. Incluem metadados, assinatura pública, XML, amostras legadas e repetições de planejamento. Excluem cabeçalhos HTTP/TLS e a aquisição C1/CHIRPS da fase anterior. A expansão de bandas levou **131,989 s**, 269 requisições e 27.352.031 bytes. O modo normal reexecutado pelo cache não fez requisições. Não houve nova aquisição de CHIRPS.

A medição após as cópias finais de verificação registrou cerca de **868,15 MB em todo `data/`**, sendo **38,62 MB** de arquivos da recuperação, incluindo catálogos, diagnósticos, pacotes anteriores e cópias de reprodução. `data/recovery/resources.json` é o inventário reproduzível; o tamanho em disco cresce quando são criadas outras cópias locais. A base de código, ambientes e caches de ferramentas não entram nesse total de dados.

Foram registradas quatro requisições diagnósticas com erro nos inventários; a retomada e as fontes alternativas permitiram concluir todos os lotes configurados. A primeira execução do novo adaptador revelou o caso de catálogo sem produtos aprovados: foi corrigido e ganhou teste. A extensão dos hashes de evidência gerou uma nova identidade de lotes, preservando os anteriores. Esses episódios não foram interpretados como observações científicas.

A suíte ampliada foi executada integralmente: **193 testes aprovados em 15,09 s**, incluindo os 106 existentes. Também foram executadas:

- Auditoria PC e legado offline: zero HTTP/bytes, com recomputação de pixels, reflectâncias e comparações.
- Reprodução em **diretório novo**, com `requests.Session.request` proibido: 40 arquivos ativos idênticos byte a byte, incluindo tabelas, gráficos, experimentos e pacote WebGIS; 6,031 s, zero HTTP/bytes.
- Reexecução normal usando apenas cache, também com HTTP proibido: os mesmos 40 arquivos idênticos; 6,061 s, zero HTTP/bytes.
- Fluxo C1 original offline: observações, tentativas, mensal, relatório e métricas sazonais originais reproduzidos por seus cinco hashes. O snapshot original completo também foi verificado.
- Auditoria independente das medianas, predições, coeficientes por SVD e MAE/RMSE, com diferenças inferiores a `1e-12`.

## Reprodução no PowerShell

Pré-requisito: instalação original com `uv sync --frozen`, Python 3.12 e o inventário ANA/C1/CHIRPS da fase anterior. Os arquivos adquiridos são locais e ficam fora do Git. Para repetir o diagnóstico/aquisição a partir desse inventário:

```powershell
uv run --no-sync aquaclima catalog-diagnostic
uv run --no-sync python scripts/prepare_radiometry.py
uv run --no-sync python scripts/audit_radiometry.py
uv run --no-sync python scripts/audit_legacy_radiometry.py
uv run --no-sync aquaclima recovery-plan
uv run --no-sync aquaclima recovery-run
uv run --no-sync aquaclima recovery-plan --config configs/recovery-2022.toml --allow-bulk
uv run --no-sync aquaclima recovery-run --config configs/recovery-2022.toml --allow-bulk
```

O preparo copia o protocolo científico versionado antes dos testes e consulta somente 20/03/2022 para a comparação coincidente. A auditoria exige o recorte C1 desse dia já disponível na fase anterior. Se o catálogo futuro mudar ou o teste falhar, a recuperação falha explicitamente; não produz aprovação automaticamente para uma fonte diferente.

Com os arquivos desta execução disponíveis:

```powershell
uv run --no-sync python scripts/prepare_radiometry.py --offline
uv run --no-sync python scripts/audit_radiometry.py --offline
uv run --no-sync python scripts/audit_legacy_radiometry.py --offline
uv run --no-sync aquaclima recovery-plan --config configs/recovery-2022.toml --allow-bulk --dry-run
uv run --no-sync python scripts/verify_recovery_offline.py
uv run --no-sync python scripts/verify_recovery_offline.py --check-online-cache --output-dir data/recovery/idempotente/verificacao
uv run --no-sync python -m pytest -q
```

No ambiente restrito desta sessão, os testes usaram `--basetemp .local-review/pytest-phase3-complete` e `MPLCONFIGDIR` dentro do workspace, devido às permissões da pasta temporária. Isso não é uma dependência científica do pipeline.

O dataset está em `data/recovery/curated/2022_2024_recovery_v1/`; os lotes ativos usam a identidade `a914138bed2c`. Os hashes principais são:

- `observations.csv`: `0b1341b57615a5503a68fc8e3e54983f96fd6129ab463c63a517dce6cf05a780`.
- `monthly.csv`: `d78469f3dd13287d390aa75cceaa745e1dbf9ed83a1b4efbf18a17718e64fc7a`.
- Auditoria: `5c90b29fbc920fbc41ff33d27857acd7c3fc64932e4a766870fe2bae506ea124`.
- Pacote WebGIS ativo: `16094dc7ef7ae3e6881b86bc0cbb0ff7b146f0558fc0947957865026882360a3`.

Recomenda-se congelar esta versão para o Capstone, apresentar cobertura e limitações junto aos resultados e iniciar a integração WebGIS sobre os contratos publicados. A dependência temporal, os pivôs próximos, a seleção irregular de datas e a ausência de culturas/rótulos agronômicos limitam a interpretação. Novas tentativas de recuperação não devem atrasar a entrega de 24/11/2026. A avaliação cronológica de 2025 deve usar parâmetros previamente congelados e registrar a exposição exploratória já conhecida.
