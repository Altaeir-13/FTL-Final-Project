# Checklist de entrega FTL

Referência: **17/11/2026**, fuso America/Sao_Paulo. Prazo oficial: **24/11/2026**. Os itens abertos dependem de revisão ou atuação do responsável. A Fase 7 está na `main` em `ad107d0c29c63ad9eb9f91a5970d96906676e3df`, com [deployment 44067496065 aprovado](https://github.com/Altaeir-13/FTL-Final-Project/actions/runs/44067496065). Consulte o [registro de lançamento](AUDITORIA-DE-LANCAMENTO.md).

## Materiais

- [x] [Relatório científico em Markdown](https://github.com/Altaeir-13/FTL-Final-Project/blob/ad107d0c29c63ad9eb9f91a5970d96906676e3df/docs/relatorio-final-ftl.md), preservando os resultados congelados.
- [x] [Roteiro de cinco minutos, demonstração de três minutos e perguntas da banca](04-roteiro-apresentacao-e-demo.md).
- [x] Atualizar o roteiro para investigação guiada, ficha de evidências e os cinco passos do modo demonstração; manter problema, ODS, metodologia, resultados e conclusão nos slides.
- [x] Resultados concluídos de Paracatu, fontes, limitações e 2025 excluído da avaliação.
- [x] Consolidar a seção regional do relatório e o slide 7: Guadalupe, 29 observações, cinco pivôs, seis datas e reprodução offline.
- [x] Conferir o PPTX editável e os oito slides renderizados pelo Artifact Tool.
- [ ] Confirmar instruções oficiais de envio e eventuais regras do template FTL. Nenhum template oficial foi encontrado no repositório ou nos anexos locais pesquisados nesta fase.
- [x] PDF de apresentação produzido como backup raster e conferido: oito páginas renderizadas pelo Poppler. O PPTX mantém a edição.
- [x] [Relatório científico em PDF](01-relatorio-cientifico-aquaclima.pdf): 13 páginas A4, texto selecionável, seis figuras incorporadas, seis tabelas completas, 22 seções e referências clicáveis; todas as páginas renderizadas e inspecionadas.
- [x] Revisar os oito slides e o roteiro contra dados públicos; apresentação preservada byte a byte, com os dois derivados reais Sentinel-2 conferidos por hash.
- [x] Gerar pelo site público e revisar as duas fichas exemplificativas A4: Paracatu em cinco páginas e Guadalupe em quatro, com datas de geração próprias e identidade científica estável.

## Integridade e revisão

- [x] Executar e registrar testes: 216 Python, 37 frontend, cinco de política e 16 de navegador; clone limpo conferido. [Evidências](https://github.com/Altaeir-13/FTL-Final-Project/blob/ad107d0c29c63ad9eb9f91a5970d96906676e3df/docs/execucao-fase6.md).
- [x] Executar build de produção e verificação do pacote público; 25 arquivos e mesmo digest no workspace/clone.
- [x] Conferir hashes congelados de Paracatu e separação dos namespaces regionais.
- [x] Conferir nomes, unidades, legendas e referências científicas nas figuras, tabelas e slides.
- [x] Validação histórica da `main` anterior: 12 cenários aprovados, registrada na Fase 6. Não substitui a validação da versão atual.
- [x] PR #2 regional integrado à `main`; workflow de publicação aprovado, conforme estado informado no início da Fase 7.
- [x] Conferir o registro final da [Fase 7](https://github.com/Altaeir-13/FTL-Final-Project/blob/ad107d0c29c63ad9eb9f91a5970d96906676e3df/docs/investigacao-guiada-ftl.md): 216 Python, 60 frontend, cinco de política e 25 Playwright aprovados; build e SHA-256 idêntico em clone limpo; hashes científicos preservados.
- [x] PR #3 revisado e integrado pelo responsável em `ad107d0`; nenhum merge automático foi feito nesta auditoria.
- [x] Validar a Fase 7 publicada com os **25 testes Playwright**, sem servidor local: 25 aprovados, zero falhas, zero instabilidades, 57,011 s.
- [x] Conferir desktop e viewport móvel de 390 px, duas regiões, investigação, imagens, URLs, ficha A4, território e demonstração na URL pública.
- [x] Comparar os **24 arquivos servidos** byte a byte com o build íntegro. O marcador `.nojekyll` foi conferido separadamente: 404 público, sem dependência de runtime.
- [x] Confirmar pacotes científicos, fontes, imagens e workflow preservados; nenhum defeito funcional foi encontrado que exigisse alteração do aplicativo.

## Investigação e ficha — revisão funcional da Fase 7

- [x] Abrir Paracatu e Guadalupe; conferir separação dos estados científico concluído e exploratório.
- [x] Selecionar pivô e duas observações aceitas distintas; conferir NDVI, NDMI, `B − A`, chuva, qualidade, lacunas e cenas com o pacote público.
- [x] Conferir as imagens de Guadalupe em 18/07/2023 e 22/07/2024 e a mensagem de indisponibilidade nas demais observações.
- [x] Gerar a ficha; conferir valores, fontes, hashes, identificador, data de geração e independência de mudanças posteriores na seleção.
- [x] Imprimir/salvar a ficha em A4; conferir páginas, tabelas, identificadores completos e legibilidade em escala de cinza.
- [x] Abrir um link compartilhado, recarregar e conferir a mesma investigação; testar links anteriores de Paracatu e entrada inválida.
- [x] Percorrer os cinco passos da demonstração, testar Voltar/Reiniciar/Escape e conferir restauração da navegação.
- [x] Conferir visão territorial e interação por teclado em desktop e celular, sem tiles externos e com Caxias apenas como origem.

## Apresentação e submissão

- [ ] Ensaiar cinco minutos de slides e três minutos de demonstração.
- [x] Preparar preview local compilado para contingência de conexão, identificando quando usado.
- [ ] Conferir legibilidade no projetor e testar abertura do PPTX em um editor compatível.
- [x] Funcionalidades concluídas e publicadas até **17/11**, antes do limite de 20/11; não iniciar novas funcionalidades ou experimentos.
- [ ] Congelar a versão de entrega em **23/11** e registrar o commit final.
- [x] Preparar a [pasta consolidada](README.md) e o ZIP com 27 arquivos, links públicos, fichas reais, registro de versão, checksums individuais e verificador independente.
- [ ] Guardar uma cópia pessoal externa do pacote revisado e dos links antes da submissão.
- [ ] Revisar e aprovar a release preparada; decidir a publicação da release e o merge dos materiais de finalização.
- [ ] Realizar o envio oficial em **24/11** e guardar o comprovante.

## Marcos e critérios de parada

| Data | Decisão/entrega |
|---|---|
| 16–17/11 | Núcleo de investigação guiada sobre os dois pacotes já publicados |
| 18/11 | Ficha exportável, impressão e consistência com a seleção |
| 19/11 | Modo demonstração e visão territorial |
| 20/11 | Concluir integração, testes, documentação e preparar PR. Não iniciar novas funcionalidades ou experimentos após esta data |
| 21–22/11 | Correções de defeitos, revisão da apresentação, testes e ensaio |
| 23/11 | Congelamento final |
| 24/11 | Entrega oficial |

A prova regional conserva seu caráter exploratório. Não houve alteração científica, aquisição nova ou treinamento nesta finalização. A Fase 7 já está publicada após o merge manual autorizado e o deployment aprovado. A preparação da pasta e da release para revisão não equivale à submissão oficial do Capstone.
