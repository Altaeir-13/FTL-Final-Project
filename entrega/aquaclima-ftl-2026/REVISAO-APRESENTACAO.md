# Revisão da apresentação para a release FTL

Referência: **17/11/2026**. Arquivos conferidos: [PPTX editável da Fase 7](02-apresentacao-editavel.pptx) e [PDF de apresentação](03-apresentacao-apoio.pdf). Esta revisão não alterou os binários, os resultados científicos ou os scripts de geração.

O [PR #3](https://github.com/Altaeir-13/FTL-Final-Project/pull/3) foi integrado no commit `ad107d0c29c63ad9eb9f91a5970d96906676e3df`, com [workflow de publicação aprovado](https://github.com/Altaeir-13/FTL-Final-Project/actions/runs/44067496065). A suíte pública executada em 17/11 aprovou **25 cenários no Microsoft Edge em 57,011 s**, diretamente na URL oficial, sem servidor local, testes ignorados, falhas ou instabilidade registrada. Os resultados individuais estão no [registro Playwright](evidencias/playwright-publico.json).

## Conteúdo e correspondência com o roteiro

| Slide | Conteúdo conferido |
|---|---|
| 1 | AquaClima, autor e Future Tech Leaders |
| 2 | Problema de qualidade e lacunas, com 35/57/49 espaços observados em 2022/2023/2024 |
| 3 | ODS 6 e 13, contexto dos ODS 2 e 9, sem alegação de impacto mensurado |
| 4 | ANA/SNIRH, Sentinel-2 L2A, CHIRPS v3, fórmulas NDVI/NDMI, aceitação de pixels e agregação |
| 5 | Paracatu: cinco pivôs, 256 observações, 57 cenas, 141/180 espaços e 78,3% |
| 6 | Tabela nativa com seis linhas pivô/índice/método de 16708, mesmos sete meses de 2024, MAE/RMSE |
| 7 | Guadalupe: 29 observações de 30 tentativas, cinco pivôs e seis cenas; duas imagens reais de julho |
| 8 | Investigação guiada, ficha A4, link com hash, demonstração, visão territorial e validação de campo pendente |

O [roteiro](04-roteiro-apresentacao-e-demo.md) mantém **cinco minutos de slides e aproximadamente três minutos de demonstração**, com avanço manual. A fala do slide 7 acompanha as imagens de 18/07/2023 e 22/07/2024. A demonstração usa o mesmo modo de cinco passos disponível no site: problema, Paracatu, investigação, Guadalupe e limites. A ficha abre como prévia independente da seleção posterior; o roteiro reserva a impressão para depois da fala, evitando depender do diálogo do sistema durante a apresentação.

Caxias continua sendo a origem e a motivação territorial do pesquisador. Paracatu é o estudo científico concluído; Guadalupe é a prova exploratória. A apresentação e a fala não atribuem validação agronômica, operação em todo o Brasil, consumo ou economia de água aos novos componentes.

## Conferência independente dos arquivos

O Poppler confirmou oito páginas 16:9, sem criptografia ou JavaScript, e renderizou todas em `build/release-presentation/`, diretório ignorado pelo Git. As oito páginas foram inspecionadas individualmente, sem cortes, sobreposição ou páginas vazias observados. O PDF é um backup raster dos slides; não possui texto selecionável. O PPTX permanece o mestre editável.

A leitura direta do ZIP/XML do PPTX conferiu oito slides, suas notas e a tabela nativa do slide 6. As seis linhas de métricas coincidem com `common_month_metrics.csv` do pacote público, arredondadas às três casas exibidas. A contagem de cobertura do gráfico e os números usados pelo gerador coincidem com as observações e a grade mensal publicadas. As duas imagens incorporadas coincidem por SHA-256 com os derivados reais de Guadalupe, e as notas do slide 7 preservam as datas, os IDs completos, os hashes e as fontes correspondentes. As seis cenas regionais referem-se às aquisições efetivamente aceitas; os produtos candidatos auditados não foram contados como observações.

Os pacotes científicos permanecem `7a072a6e29688039b5b775663262ecf6338b35c41386264e75ee789f93068a4d` para Paracatu e `8d7a54f09174e5890f8a8babf153df855699c727d639b7868a94a658a7495131` para Guadalupe. Os hashes dos arquivos revisados permanecem:

| Artefato | SHA-256 |
|---|---|
| PPTX | `ab6ffca022d1dee3d46b16388719781e829d48b04ed17cceea7d235d3882865e` |
| PDF | `90a780fe14061a9a64da03e1dcc085a4cb00550decff544c3885ae3f2f97e39e` |

Para repetir a renderização sem alterar a apresentação:

```powershell
New-Item -ItemType Directory -Path build/release-presentation -Force
pdfinfo docs/apresentacao/aquaclima-ftl-fase7.pdf
pdftoppm -r 96 -png docs/apresentacao/aquaclima-ftl-fase7.pdf build/release-presentation/page
Get-FileHash docs/apresentacao/aquaclima-ftl-fase7.pptx,docs/apresentacao/aquaclima-ftl-fase7.pdf
```

## Limites e revisão humana restante

A conferência automatizada e visual não equivale a abrir o PPTX no PowerPoint nativo, testar o projetor ou ensaiar a fala. Cabe ao apresentador confirmar fontes, proporção de tela, legibilidade no ambiente real e duração de cinco mais três minutos com cronômetro. A captura do slide 5 é um registro autêntico anterior do estudo concluído, com os mesmos resultados científicos; a demonstração ao vivo usa a versão pública atual.

As notas do slide 8 são datadas da autoria de 16/11 e mencionam a publicação então pendente. Esse registro histórico permanece no binário preservado. Para o estado atual de publicação, usar este documento e o roteiro de 17/11. Não foi identificado defeito científico ou visual que exigisse alterar os binários nesta revisão. A submissão final ao FTL e a confirmação do recebimento continuam sendo ações do responsável pelo Capstone.
