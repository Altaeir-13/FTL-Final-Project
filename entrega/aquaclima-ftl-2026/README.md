# AquaClima — entrega do Capstone FTL

Autor: **Randerson Sousa de Sá Nunes**. Referência: **17/11/2026**. Prazo: **24/11/2026**.
Aplicação **1.1.0**, release proposta **v1.1.0-ftl**, preparada para revisão. Não constitui submissão oficial.

| Arquivo | Uso |
|---|---|
| 01-relatorio-cientifico-aquaclima.pdf | Relatório completo, 13 páginas A4, texto selecionável, figuras e referências |
| 02-apresentacao-editavel.pptx | Mestre editável, oito slides |
| 03-apresentacao-apoio.pdf | Backup raster de oito páginas; sem texto selecionável |
| 04-roteiro-apresentacao-e-demo.md | Fala de cinco minutos, demonstração de três minutos e perguntas da banca |
| 05-ficha-exemplo-guadalupe.pdf | Ficha real do site público, cenas 18/07/2023 e 22/07/2024, quatro páginas |
| 06-ficha-exemplo-paracatu.pdf | Ficha real do site público, agregados julho/2023 e julho/2024, cinco páginas |
| LINKS-PUBLICOS.md | Site, código, deployment e investigações reproduzíveis |
| CHECKLIST-ENTREGA.md | Verificações concluídas e tarefas do responsável |
| AUDITORIA-DE-LANCAMENTO.md / REVISAO-APRESENTACAO.md | Escopo, limites e evidências da revisão |
| evidencias/ | Resultados por cenário, hashes, fidelidade de documentos e capturas autênticas |
| VERSAO-E-INTEGRIDADE.json / SHA256SUMS.txt | Proveniência da versão e checksums individuais |
| VERIFICAR.py | Verificação local da pasta, apenas biblioteca padrão Python |

Os PDFs e o PPTX abrem sem backend, rasters privados ou APIs pagas. Os links de demonstração acessam o site público. Nos documentos Markdown, links para arquivos incluídos são locais; referências adicionais apontam para suas versões no GitHub e exigem conexão. Nenhum arquivo de aquisição científica está incluído.

Paracatu é o estudo científico concluído. Guadalupe é prova exploratória, sem modelo regional validado. Caxias é origem e motivação, sem observações processadas. As fichas não comprovam causas, falhas de irrigação, economia de água ou ganhos financeiros. A data de geração das fichas é distinta das datas observadas.

Para conferir a pasta isoladamente, execute `python VERIFICAR.py`. Com sha256sum disponível: `sha256sum --check SHA256SUMS.txt`. O checksum não se inclui em si próprio. O ZIP adjacente contém exatamente esta pasta e tem checksum separado no diretório entrega/.

O responsável ainda deve confirmar as regras oficiais de submissão, revisar os materiais e o rascunho de release, abrir o PPTX no editor/projetor, ensaiar com cronômetro, congelar a entrega em 23/11 e submeter oficialmente em 24/11, guardando o comprovante. A verificação de 390 px em navegador não substitui teste em aparelho físico.
