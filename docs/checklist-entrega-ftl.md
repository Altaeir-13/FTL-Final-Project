# Checklist de entrega FTL

Referência: 15/11/2026, fuso America/Sao_Paulo. Prazo oficial: **24/11/2026**. Os itens abertos são ações de entrega/validação pendentes, não declarações de execução.

## Materiais

- [x] [Relatório científico em Markdown](relatorio-final-ftl.md), estruturado para exportação posterior.
- [x] [Roteiro de cinco minutos, demonstração de três minutos e perguntas da banca](roteiro-final-ftl.md).
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
- [x] Validar o site público da `main` anterior: 12 cenários aprovados. A versão regional ainda depende de merge e deployment.
- [ ] Após o merge, validar a nova publicação com os 16 cenários de navegador.
- [ ] Revisar o PR e decidir o merge manual. Não há merge automático ou publicação pela branch regional.

## Apresentação e submissão

- [ ] Ensaiar cinco minutos de slides e três minutos de demonstração.
- [x] Preparar preview local compilado para contingência de conexão, identificando quando usado.
- [ ] Conferir legibilidade no projetor e testar abertura do PPTX em um editor compatível.
- [ ] Congelar funcionalidades em **23/11** e registrar o commit final.
- [ ] Guardar cópia dos materiais finais e dos links públicos.
- [ ] Realizar o envio oficial em **24/11** e guardar o comprovante.

## Marcos e critérios de parada

| Data | Decisão/entrega |
|---|---|
| 15–16/11 | Auditoria ANA, geometrias, catálogo e seleção regional baseada em evidências |
| 17–18/11 | Prova limitada e reprodução offline. Até o fim de 18/11, decidir incorporação regional ao Capstone |
| 19–20/11 | Integração viável e consolidação dos materiais. Não iniciar novos experimentos após 20/11 |
| 21–22/11 | Validação, site público, referências e ensaio |
| 23/11 | Congelamento final |
| 24/11 | Entrega oficial |

Se a prova regional não atingir o mínimo de qualidade, conservar o relatório de auditoria e concluir a entrega com Paracatu. A prioridade acadêmica não depende de uma segunda região validada. A comparação visual de imagens de satélite é opcional e só entra com recortes reais adequados.
