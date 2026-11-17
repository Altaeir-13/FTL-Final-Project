# AquaClima 1.1.0 — entrega do Capstone Future Tech Leaders

**Release preparada para revisão.** Prazo oficial do Capstone: **24/11/2026**. Autor: Randerson Sousa de Sá Nunes.

O WebGIS da Fase 7 está publicado em [altaeir-13.github.io/FTL-Final-Project](https://altaeir-13.github.io/FTL-Final-Project/), commit `ad107d0c29c63ad9eb9f91a5970d96906676e3df`, após merge manual do PR #3 e [deployment aprovado](https://github.com/Altaeir-13/FTL-Final-Project/actions/runs/44067496065). Esta preparação de release não altera o aplicativo ou os resultados científicos, nem constitui submissão oficial do autor.

## Auditoria de lançamento em 17/11/2026

- **25 testes Playwright aprovados diretamente no site público**, em 57,011 s, sem servidor local, testes ignorados, falhas ou instabilidades. Desktop e viewport móvel de 390 px, duas regiões e todos os fluxos da Fase 7 conferidos.
- **24 arquivos servidos idênticos byte a byte** ao build validado. `.nojekyll` é marcador vazio de deployment e não é recurso de runtime; seu 404 público está documentado.
- Produção em Ubuntu: **216 testes Python, 60 frontend, cinco de política e 25 Chromium aprovados**, build e deployment concluídos.
- **Nenhum defeito funcional identificado** que exigisse alteração do aplicativo; nenhuma aquisição, treinamento ou funcionalidade adicional.

## Arquivos para revisão

O ZIP consolidado inclui relatório científico final em PDF (13 páginas A4, texto selecionável, seis figuras e seis tabelas), apresentação editável de oito slides, PDF de apoio raster, roteiro de cinco minutos mais três de demonstração, fichas de evidências reais de Paracatu e Guadalupe, checklist, links reproduzíveis, capturas autênticas e registros de verificação.

O pacote contém `SHA256SUMS.txt`, `VERSAO-E-INTEGRIDADE.json` e `VERIFICAR.py`. Para verificar a pasta isoladamente: `python VERIFICAR.py`. O checksum do ZIP é distribuído como arquivo separado. O relatório preservou 235 blocos de conteúdo e todas as páginas dos documentos exportados foram renderizadas e inspecionadas. A apresentação anterior foi preservada byte a byte.

## Identidades preservadas

| Artefato científico ou de aplicação | SHA-256 |
|---|---|
| Build estático completo | `30c96116b9f84daa8dfee0fe4fa3dbd4a7457d2895524d423e56c44f89f8ba3f` |
| Pacote público Paracatu | `7a072a6e29688039b5b775663262ecf6338b35c41386264e75ee789f93068a4d` |
| Pacote Guadalupe | `8d7a54f09174e5890f8a8babf153df855699c727d639b7868a94a658a7495131` |
| Relatório PDF | `cd771484662b9833aac8ba314da8c33cc8a6a0adefdd36bfe107cc529f96a813` |
| Apresentação editável | `ab6ffca022d1dee3d46b16388719781e829d48b04ed17cceea7d235d3882865e` |
| PDF de apoio dos slides | `90a780fe14061a9a64da03e1dcc085a4cb00550decff544c3885ae3f2f97e39e` |

## Limites e ações do responsável

Paracatu é o estudo concluído de cinco pivôs em 2022–2024. Guadalupe é a prova exploratória de 29 observações em seis datas, sem modelo regional validado. Caxias é a origem territorial, sem observações processadas. O sistema não diagnostica falhas de irrigação nem comprova economia de água ou ganhos financeiros.

A validação móvel em navegador não substitui aparelho físico. A impressão foi conferida em Chromium/Edge, e outros drivers podem paginar de forma diferente. O PDF dos slides é raster; o PPTX é o mestre editável. Não se afirma ensaio em PowerPoint nativo ou projetor. As notas do slide 8 conservam o registro histórico datado de 16/11; a publicação de 17/11 consta do roteiro e da auditoria atual.

O responsável deve revisar e aprovar os materiais e este rascunho, decidir o merge da documentação e a publicação da release, conferir regras oficiais e limite dos arquivos, testar o PPTX no editor/projetor, ensaiar, guardar cópia pessoal, congelar a submissão em **23/11** e enviá-la oficialmente em **24/11**, preservando o comprovante.
