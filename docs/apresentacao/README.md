# Apresentação final AquaClima

Versão da **Fase 7**, integrada pelo PR #3 e revista para release em 17/11/2026: [PPTX editável](aquaclima-ftl-fase7.pptx), com oito slides, gráfico nativo com workbook incorporado, tabela nativa de métricas, textos editáveis e notas de fonte. O [PDF da Fase 7](aquaclima-ftl-fase7.pdf) contém as mesmas oito páginas como **backup raster**. O PDF não tem texto selecionável; o PPTX é o documento mestre editável. A [apresentação anterior](aquaclima-ftl.pptx) e seu [PDF](aquaclima-ftl.pdf) permanecem preservados.

O conteúdo usa resultados reais do pacote congelado de Paracatu e do [snapshot independente de Guadalupe](../evidencias/guadalupe-pi/manifest.json). A captura de tela do slide 5 é autêntica, já existente no projeto, e mostra o caso concluído. O slide 7 inclui os dois derivados Sentinel-2 reais já publicados, de 18/07/2023 e 22/07/2024, com a mesma grade e parâmetros de falsa cor. O slide 8 apresenta a investigação guiada, a ficha A4, os links reproduzíveis, a demonstração e a visão territorial como funcionalidades derivadas dos resultados científicos. Não foi encontrado template oficial FTL nos arquivos do repositório ou nos anexos locais pesquisados, por isso o material segue a identidade cromática do AquaClima, sem afirmar identidade oficial do programa.

## Revisão da Fase 7 em 16/11/2026

A revisão mantém oito slides e o conteúdo de problema, ODS, metodologia, resultados de Paracatu e conclusão. As mudanças de conteúdo concentram-se nos slides 7 e 8. O gerador verifica os SHA-256 dos dois PNGs contra a [proveniência congelada](../evidencias/guadalupe-pi/comparison/provenance.json) antes de incorporá-los. As notas do slide 7 preservam IDs completos, fontes STAC, baselines, hashes dos PNGs/recortes/manifestos, a composição B08/B04/B11, EPSG:32723, grade de 20 m e estiramento fixo 0–0,6. A contagem de 29/30 tentativas não substitui a cobertura de 29/115 espaços do calendário.

O finalizador aprovou oito slides, integridade estrutural, geometria, fonte Arial, tabela editável no slide 6, gráfico nativo e workbook no slide 2, além da reimportação pelo Artifact Tool. Os oito renders foram inspecionados individualmente. O Poppler confirmou oito páginas 16:9 no PDF e renderizou todas para inspeção visual. Essa verificação não equivale a abrir o arquivo no PowerPoint. O PDF continua sendo backup raster dos renders, sem texto selecionável. Nenhum raster científico foi adquirido e nenhuma figura ou métrica científica foi recalculada.

| Artefato da Fase 7 | SHA-256 |
|---|---|
| PPTX | `ab6ffca022d1dee3d46b16388719781e829d48b04ed17cceea7d235d3882865e` |
| PDF | `90a780fe14061a9a64da03e1dcc085a4cb00550decff544c3885ae3f2f97e39e` |

Na revisão de 16/11, as funcionalidades ainda aguardavam revisão e merge. Esse estado é histórico: o [PR #3](https://github.com/Altaeir-13/FTL-Final-Project/pull/3) foi integrado à `main` no commit `ad107d0c29c63ad9eb9f91a5970d96906676e3df`, com [publicação aprovada](https://github.com/Altaeir-13/FTL-Final-Project/actions/runs/44067496065). Em 17/11, **25 cenários Playwright passaram na URL pública**, diretamente no Edge, sem servidor local, cenários ignorados, falhas ou instabilidade registradas. O [registro público](../evidencias/release-publica/playwright-publico.json) e a [revisão final da apresentação](../revisao-apresentacao-release.md) documentam essa conferência.

Os binários da apresentação permanecem idênticos aos hashes acima. A revisão de release reabriu as oito páginas do PDF pelo Poppler e conferiu textos, notas, tabela de métricas e imagens incorporadas no ZIP do PPTX contra os pacotes públicos. O [roteiro atualizado](../roteiro-final-ftl.md) descreve a demonstração publicada. As notas do slide 8 datadas de 16/11 preservam o contexto de publicação pendente daquela revisão; o estado atual é o registrado neste parágrafo. PowerPoint nativo, projetor e duração oral ainda dependem de ensaio humano.

## Geração reproduzível

Os scripts não ajustam modelos, não alteram datasets e não fazem aquisição. Python do projeto gera/verifica as evidências. O autor de slides usa JavaScript ES modules e `@oai/artifact-tool` do runtime Codex. Caminhos do runtime devem ser obtidos com `load_workspace_dependencies`, sem instalar versões substitutas ou copiar o ambiente científico original.

```powershell
# Ambiente Python do projeto já instalado pelo lock.
.venv/Scripts/python.exe scripts/prepare_ftl_evidence.py

# Defina pelos caminhos retornados por load_workspace_dependencies.
$env:AQUACLIMA_ARTIFACT_MODULES = '<Node.js packages do runtime>'
$env:AQUACLIMA_PRESENTATIONS_SKILL = '<diretório da skill presentations>'
$env:AQUACLIMA_RUNTIME_PYTHON = '<Python executable do runtime>'
$env:AQUACLIMA_DECK_NAME = 'aquaclima-ftl-fase7-reproduzida.pptx'

# Execute com o Node.js executable retornado pelo runtime.
node scripts/generate_ftl_presentation.mjs

# Backup PDF a partir dos oito renders. Requer reportlab, incluído no Python do runtime.
# Execute com o Python executable retornado pelo runtime.
python scripts/export_ftl_pdf.py --output docs/apresentacao/aquaclima-ftl-fase7-reproduzida.pdf
```

O finalizador recusa sobrescrever um PPTX existente. Usar um nome novo na variável `AQUACLIMA_DECK_NAME` ao reproduzir. As saídas temporárias e os renders ficam em `build/ftl-presentation/`, ignorado pelo Git. O gerador de PDF utiliza os renders atuais e aceita `--output` para preservar versões anteriores.

`prepare_ftl_evidence.py` lê o pacote público versionado. As figuras científicas de Paracatu são cópias byte a byte do pipeline original. Se o cache privado `data/` estiver ausente, o script usa as cópias versionadas e as tabelas pequenas em `docs/evidencias/guadalupe-pi/`, permitindo repetir os materiais em um clone sem rasters. Os JSONs de evidência registram hashes e denominadores de cobertura.

## Verificações históricas da apresentação anterior em 15/11/2026

O Artifact Tool exportou e reimportou o PPTX. O finalizador aprovou integridade estrutural, oito slides, geometria de texto, fonte Arial, tabelas nativas nos slides 6/7 e gráfico nativo no slide 2, com dados completos e workbook incorporado. Os oito renders foram inspecionados visualmente, incluindo os números da tabela de sete meses e os valores regionais. Isso não equivale a abrir o arquivo no PowerPoint. A preparação de evidências também foi repetida numa cópia contendo somente scripts, pacote público, figuras e snapshot regional, sem pasta `data/`, rasters ou caches privados, reproduzindo os totais de 256 observações/141 espaços em Paracatu e 29 observações em Guadalupe.

A exportação PDF nativa do runtime falhou por ausência do módulo `#standard-fonts/Helvetica`. O backup foi gerado com ReportLab a partir dos PNGs autênticos do próprio deck. `pdfinfo` confirmou oito páginas 16:9, sem criptografia. O Poppler renderizou todas as páginas e as oito imagens foram inspecionadas. Nenhuma exportação PDF do relatório científico é alegada.

Fontes bibliográficas verificadas em 15/11/2026: [Tucker, 1979](https://doi.org/10.1016/0034-4257(79)90013-0), [Gao, 1996](https://doi.org/10.1016/S0034-4257(96)00067-3), [Funk et al., CHIRPS v3, 2026](https://doi.org/10.1038/s41597-026-07096-4), [produtor CHIRPS](https://chc.ucsb.edu/data/chirps3), [USGS NDMI](https://www.usgs.gov/landsat-missions/normalized-difference-moisture-index) e [ONU ODS](https://sdgs.un.org/goals).

O [relatório científico](../relatorio-final-ftl.md) contém os resultados completos e limitações. O [roteiro](../roteiro-final-ftl.md) organiza cinco minutos de slides, três de demonstração, versão rápida e perguntas da banca. O [checklist](../checklist-entrega-ftl.md) preserva as ações de revisão, merge e submissão que dependem do responsável.
