# Execução e validação da fase 6 — 15/11/2026

Autor: Randerson Sousa de Sá Nunes. Prazo FTL: **24/11/2026**. A implementação está na branch `codex/aquaclima-regional-ftl`, criada sobre a `main` remota em `0fb58274ca9c8364881ddd5b366b5fa5e7958743`. Não houve merge ou deployment da branch.

## Resultado e decisão científica

A auditoria estadual completa recuperou **136 pivôs no Maranhão e 40 no Piauí**, distribuídos por 26 municípios. A comparação principal considerou os oito municípios solicitados e duas alternativas próximas; uma auditoria suplementar ampliou a conferência detalhada para **14 municípios e 116 polígonos**. Caxias e Landri Sales não apresentaram registros associados nem interseções com os polígonos recuperados. Isso se refere ao inventário ANA 2022, sem afirmar ausência atual de outras formas de irrigação.

Guadalupe/PI foi escolhida antes dos rasters pelo método ponderado registrado: **12 pivôs ANA, dez elegíveis, escore 89,80/100**, cinco pivôs em raio de 1,717 km, centroide a 215,49 km da sede pública de Caxias. A amostra usa os FIDs **5795, 5797, 5798, 5802 e 5804**, com chave `PI:<FID>`. Contagens, áreas, geometrias, centroides, municípios alternativos, critérios e limitações constam do [relatório de seleção](selecao-regional-ma-pi.md) e dos CSV/GeoJSON versionados em `data/regions/selection/`.

O piloto processou seis cenas C1 L2A reais: **29/01, 18/07 e 25/11 de 2023; 24/03, 22/07 e 29/11 de 2024**, todas no tile `23MPN`. Produziu **29 observações aceitas em 30 tentativas**, NDVI/NDMI e CHIRPS nos seis meses alvo. Uma observação de março/2024 teve 52,54% de pixels válidos e foi rejeitada; a menor qualidade aceita foi 80,14%. Na grade de 23 meses, há 29/115 espaços observados (25,2%), distintos dos 29/30 espaços alvo (96,7%). Os 17 meses não adquiridos não foram preenchidos.

Os **14 produtos candidatos** tiveram escala e offset conferidos contra seu próprio XML ESA. As seis cenas selecionadas usam baselines 05.09, 05.10 e 05.11. Não houve ensaio da mesma aquisição reprocessada entre essas três versões nem validação radiométrica de campo. Nenhum modelo regional foi treinado e nenhuma métrica de generalização regional foi publicada. A decisão é incorporar Guadalupe como **prova exploratória de portabilidade**, sem ampliar o histórico nesta entrega. O [resultado regional](resultado-regional-guadalupe.md) registra o protocolo e os números completos.

## Implementação entregue

O novo namespace reutiliza os clientes ANA, STAC, recortes COG, SCL, cálculo dos índices, integração CHIRPS, limites HTTP, cache e verificadores existentes. Há controles para decisões inelegíveis, IDs ambíguos, separação municipal, geometrias, CRS, produtos incompatíveis, corrupção de arquivos e reprodução em diretório independente. Um erro de recomputação não sobrescreve os índices adquiridos.

O WebGIS ganhou narrativa territorial/ODS, seletor de estudos, mapa e gráficos regionais, tentativas rejeitadas, qualidade, chuva e proveniência. O manifesto multirregional é independente de `web/data` e de seu contrato 1.0.0. Duas imagens reais em falsa cor, de julho/2023 e julho/2024, usam a mesma grade, contornos ANA e estiramento fixo. Não houve download adicional para produzir essas figuras. O estudo de Paracatu ganhou contexto de chuva/qualidade nos extremos dos eventos sem recalcular eventos ou modelos. [Arquitetura e testes](webgis-regional.md).

Foram entregues o [relatório científico de 22 seções](relatorio-final-ftl.md), [PPTX editável de oito slides](apresentacao/aquaclima-ftl.pptx), [PDF de apresentação como backup raster](apresentacao/aquaclima-ftl.pdf), [roteiros e perguntas da banca](roteiro-final-ftl.md), scripts geradores e [checklist de submissão](checklist-entrega-ftl.md). Oito slides e oito páginas PDF foram renderizados e inspecionados. O PPTX foi exportado/reimportado e contém textos, tabelas e gráfico nativos; não foi aberto no PowerPoint. Não se declara PDF do relatório científico.

## Recursos efetivamente registrados

| Aquisição científica | Bytes transferidos | HTTP, incluindo falhas | Armazenamento registrado |
|---|---:|---:|---:|
| Auditoria ANA/IBGE/STAC, incluindo suplemento | 25.405.987 | 83 | 25.685.049 bytes de arquivos registrados |
| Piloto Guadalupe, incluindo XML e COG | 53.137.002 | 452 | 144.149.011 bytes antes da reprodução |
| Total de payload científico registrado | **78.542.989** | **535** | Os escopos de armazenamento são descritos separadamente |

O piloto reutilizou seis rasters CHIRPS v3 preexistentes, conferidos por hash e copiados para seu próprio namespace. O armazenamento inclui essas cópias; a transferência do piloto não contabiliza novamente sua aquisição original. Dependências npm/Python e operações Git ficam fora destes contadores de aquisição científica. Rasters, XMLs e caches volumosos continuam fora do Git. São versionados apenas inventários, tabelas pequenas, manifestos e derivados visuais.

## Verificações executadas

| Verificação | Resultado observado |
|---|---|
| Suíte Python no workspace, incluindo 23 testes novos | **216 aprovados**, 17,50 s |
| Suíte Python em ambiente novo no clone limpo | **216 aprovados**, 17,43 s |
| Frontend/contratos/integridade no clone final | **37 aprovados** |
| Política de CI/publicação | **5 aprovados**; workflow main-only inalterado |
| Navegador Edge no clone, servidor próprio na porta 4276 | **16 aprovados**, 16,7 s |
| Build Vite 7.3.8 e inspeção estática | **25 arquivos, três assets**, base `/FTL-Final-Project/` |
| Reprodução offline de Paracatu | **40 arquivos idênticos**, zero HTTP/bytes |
| Reprodução offline do piloto regional | **Cinco arquivos idênticos**, zero HTTP/bytes |
| Conferência dos índices regionais | Seis adquiridos preservados e seis recomputados com os mesmos hashes |
| Auditoria regional offline | Zero HTTP/bytes; verificador portátil aprovou os 18 arquivos declarados |
| Preparação dos materiais sem rasters no clone | Totais e figuras públicas reproduzidos; Git permaneceu limpo |
| PPTX/PDF no clone | Mesmos SHA-256 dos arquivos conferidos no workspace |
| Site publicado da main, antes do merge regional | **12 cenários originais aprovados**, 16,7 s |

O clone em `.local-review/phase6-clean` recebeu somente arquivos rastreados, sem `data/raw`, `data/recovery`, ambientes ou `node_modules` copiados. `uv sync --locked --group dev` criou um ambiente novo e `npm ci` instalou as dependências pelo lock. O diretório temporário dos testes foi configurado dentro do clone; o temporário padrão do sandbox apresentou restrições de criação. Os testes finais usaram o diretório válido.

O clone revelou alertas no Vite herdado 7.2.2. A versão foi fixada em **7.3.8**, da mesma série, conforme a [release oficial](https://github.com/vitejs/vite/releases/tag/v7.3.8). `npm ci` passou a reportar zero vulnerabilidades conhecidas no conjunto instalado. Os testes e o build foram repetidos; o artefato estático conservou o mesmo digest. Esse resultado é do npm no momento da execução, sem equivaler a uma auditoria de segurança completa.

## Integridade preservada

O diff contra a main permanece vazio em `web/data`, ingestão, índices, modelagem, protocolo radiométrico congelado e workflow de publicação. Nenhum resultado de 2025 foi incorporado à avaliação. Atributos Git preservam bytes dos snapshots, PDF e PPTX entre checkouts.

| Evidência | SHA-256 |
|---|---|
| Observações científicas congeladas de Paracatu | `0b1341b57615a5503a68fc8e3e54983f96fd6129ab463c63a517dce6cf05a780` |
| Tabela mensal científica congelada de Paracatu | `d78469f3dd13287d390aa75cceaa745e1dbf9ed83a1b4efbf18a17718e64fc7a` |
| Pacote público Paracatu | `7a072a6e29688039b5b775663262ecf6338b35c41386264e75ee789f93068a4d` |
| Decisão inicial regional | `43f1c57db963fe29ec3f57a085f705e421ff3b762ee255fc7d6b1d2d8968ccf0` |
| Artefato estático, workspace e clone | `753605cd4fc2caff31b7420fc8568bd816e9ef96455bf1d956cc093d14f14a71` |
| PPTX editável | `67ecf5c15c9bc6a9c1593de30702fa7579bdd4dc42f794c421e27274fc73b390` |
| PDF de apresentação | `15cad8b2be213daf6344cbeb3f771b5be75e7d1d7060af2c221105f43073828b` |

## Estado do prazo e ações seguintes

A seleção, prova e incorporação exploratória foram concluídas em **15/11**, antecipando a decisão obrigatória de 18/11. Os materiais acadêmicos e o build estão preparados com nove dias até a entrega de 24/11. As limitações científicas permanecem explícitas; não há necessidade de novos experimentos para concluir o Capstone.

O responsável deve revisar o PR, decidir o merge manual na `main`, acompanhar o deployment e conferir a nova versão pública com os 16 cenários. O site atual permanece em [AquaClima](https://altaeir-13.github.io/FTL-Final-Project/) com a versão aprovada anteriormente. Restam ensaio cronometrado, conferência no editor/projetor e submissão segundo as instruções do FTL. Não houve envio oficial em nome do autor. O congelamento formal de 23/11 e a entrega de 24/11 constam do checklist.
