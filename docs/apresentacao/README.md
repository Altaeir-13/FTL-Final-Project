# Apresentação final AquaClima

[PPTX editável](aquaclima-ftl.pptx), com oito slides, gráfico nativo com workbook incorporado, tabelas nativas, textos editáveis e notas de fonte. [PDF de apresentação](aquaclima-ftl.pdf), com as mesmas oito páginas como **backup raster**. O PDF não tem texto selecionável; o PPTX é o documento mestre editável.

O conteúdo usa resultados reais do pacote congelado de Paracatu e do [snapshot independente de Guadalupe](../evidencias/guadalupe-pi/manifest.json). A captura de tela do slide 5 é autêntica, já existente no projeto, e mostra o caso concluído. Não foi encontrado template oficial FTL nos arquivos do repositório ou nos anexos locais pesquisados, por isso o material segue a identidade cromática do AquaClima, sem afirmar identidade oficial do programa.

## Geração reproduzível

Os scripts não ajustam modelos, não alteram datasets e não fazem aquisição. Python do projeto gera/verifica as evidências. O autor de slides usa JavaScript ES modules e `@oai/artifact-tool` do runtime Codex. Caminhos do runtime devem ser obtidos com `load_workspace_dependencies`, sem instalar versões substitutas ou copiar o ambiente científico original.

```powershell
# Ambiente Python do projeto já instalado pelo lock.
.venv/Scripts/python.exe scripts/prepare_ftl_evidence.py

# Defina pelos caminhos retornados por load_workspace_dependencies.
$env:AQUACLIMA_ARTIFACT_MODULES = '<Node.js packages do runtime>'
$env:AQUACLIMA_PRESENTATIONS_SKILL = '<diretório da skill presentations>'
$env:AQUACLIMA_RUNTIME_PYTHON = '<Python executable do runtime>'
$env:AQUACLIMA_DECK_NAME = 'aquaclima-ftl-reproduzida.pptx'

# Execute com o Node.js executable retornado pelo runtime.
node scripts/generate_ftl_presentation.mjs

# Backup PDF a partir dos oito renders. Requer reportlab, incluído no Python do runtime.
# Execute com o Python executable retornado pelo runtime.
python scripts/export_ftl_pdf.py --output docs/apresentacao/aquaclima-ftl-reproduzida.pdf
```

O finalizador recusa sobrescrever um PPTX existente. Usar um nome novo na variável `AQUACLIMA_DECK_NAME` ao reproduzir. As saídas temporárias e os renders ficam em `build/ftl-presentation/`, ignorado pelo Git. O gerador de PDF utiliza os renders atuais e aceita `--output` para preservar versões anteriores.

`prepare_ftl_evidence.py` lê o pacote público versionado. As figuras científicas de Paracatu são cópias byte a byte do pipeline original. Se o cache privado `data/` estiver ausente, o script usa as cópias versionadas e as tabelas pequenas em `docs/evidencias/guadalupe-pi/`, permitindo repetir os materiais em um clone sem rasters. Os JSONs de evidência registram hashes e denominadores de cobertura.

## Verificações executadas em 15/11/2026

O Artifact Tool exportou e reimportou o PPTX. O finalizador aprovou integridade estrutural, oito slides, geometria de texto, fonte Arial, tabelas nativas nos slides 6/7 e gráfico nativo no slide 2, com dados completos e workbook incorporado. Os oito renders foram inspecionados visualmente, incluindo os números da tabela de sete meses e os valores regionais. Isso não equivale a abrir o arquivo no PowerPoint. A preparação de evidências também foi repetida numa cópia contendo somente scripts, pacote público, figuras e snapshot regional, sem pasta `data/`, rasters ou caches privados, reproduzindo os totais de 256 observações/141 espaços em Paracatu e 29 observações em Guadalupe.

A exportação PDF nativa do runtime falhou por ausência do módulo `#standard-fonts/Helvetica`. O backup foi gerado com ReportLab a partir dos PNGs autênticos do próprio deck. `pdfinfo` confirmou oito páginas 16:9, sem criptografia. O Poppler renderizou todas as páginas e as oito imagens foram inspecionadas. Nenhuma exportação PDF do relatório científico é alegada.

Fontes bibliográficas verificadas em 15/11/2026: [Tucker, 1979](https://doi.org/10.1016/0034-4257(79)90013-0), [Gao, 1996](https://doi.org/10.1016/S0034-4257(96)00067-3), [Funk et al., CHIRPS v3, 2026](https://doi.org/10.1038/s41597-026-07096-4), [produtor CHIRPS](https://chc.ucsb.edu/data/chirps3), [USGS NDMI](https://www.usgs.gov/landsat-missions/normalized-difference-moisture-index) e [ONU ODS](https://sdgs.un.org/goals).

O [relatório científico](../relatorio-final-ftl.md) contém os resultados completos e limitações. O [roteiro](../roteiro-final-ftl.md) organiza cinco minutos de slides, três de demonstração, versão rápida e perguntas da banca. O [checklist](../checklist-entrega-ftl.md) preserva as ações de revisão, merge e submissão que dependem do responsável.
