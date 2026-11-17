# Checklist de entrega FTL

Referência: 16/11/2026, fuso America/Sao_Paulo. Prazo oficial: **24/11/2026**. Os itens abertos são ações de entrega/validação pendentes, não declarações de execução. A Fase 6 foi integrada pelo PR #2 em `ffb7ba41d5286fd58c47acd8007903fd38b799d4`.

## Materiais

- [x] [Relatório científico em Markdown](relatorio-final-ftl.md), estruturado para exportação posterior.
- [x] [Roteiro de cinco minutos, demonstração de três minutos e perguntas da banca](roteiro-final-ftl.md).
- [x] Atualizar o roteiro para investigação guiada, ficha de evidências e os cinco passos do modo demonstração; manter problema, ODS, metodologia, resultados e conclusão nos slides.
- [x] Resultados concluídos de Paracatu, fontes, limitações e 2025 excluído da avaliação.
- [x] Consolidar a seção regional do relatório e o slide 7: Guadalupe, 29 observações, cinco pivôs, seis datas e reprodução offline.
- [x] Conferir o PPTX editável e os oito slides renderizados pelo Artifact Tool.
- [ ] Confirmar instruções oficiais de envio e eventuais regras do template FTL. Nenhum template oficial foi encontrado no repositório ou nos anexos locais pesquisados nesta fase.
- [x] PDF de apresentação produzido como backup raster e conferido: oito páginas renderizadas pelo Poppler. O PPTX mantém a edição. O relatório científico permanece em Markdown para exportação posterior.

## Integridade e revisão

- [x] Executar e registrar testes: 216 Python, 37 frontend, cinco de política e 16 de navegador; clone limpo conferido. [Evidências](execucao-fase6.md).
- [x] Executar build de produção e verificação do pacote público; 25 arquivos e mesmo digest no workspace/clone.
- [x] Conferir hashes congelados de Paracatu e separação dos namespaces regionais.
- [x] Conferir nomes, unidades, legendas e referências científicas nas figuras, tabelas e slides.
- [x] Validação histórica da `main` anterior: 12 cenários aprovados, registrada na Fase 6. Não substitui a validação da versão atual.
- [x] PR #2 regional integrado à `main`; workflow de publicação aprovado, conforme estado informado no início da Fase 7.
- [x] Conferir o registro final da [Fase 7](investigacao-guiada-ftl.md): 216 Python, 60 frontend, cinco de política e 25 Playwright aprovados; build e SHA-256 idêntico em clone limpo; hashes científicos preservados.
- [ ] Revisar o PR da Fase 7 e decidir o merge manual. Não há merge automático ou publicação pela branch de investigação.
- [ ] Após o merge, validar a Fase 7 efetivamente publicada com a suíte completa de navegador e registrar o deployment.

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
- [ ] Concluir funcionalidades até **20/11**; depois, corrigir apenas defeitos e revisar os materiais.
- [ ] Congelar a versão de entrega em **23/11** e registrar o commit final.
- [ ] Guardar cópia dos materiais finais e dos links públicos.
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

A prova regional existente conserva seu caráter exploratório. Nenhum resultado científico é alterado para sustentar as novas interações. Em caso de risco ao prazo, priorizar investigação guiada, ficha, demonstração, visão territorial e polimentos, nessa ordem. Não iniciar novas aquisições ou treinamentos. O aplicativo publicado só recebe a Fase 7 após revisão e merge manual.
