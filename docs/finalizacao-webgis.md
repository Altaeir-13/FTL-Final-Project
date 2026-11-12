# Integração, publicação e validação final do WebGIS — Fase 5

Auditoria iniciada em **12/11/2026**, para a entrega de 24/11/2026. Este registro complementa a [entrega da Fase 4](entrega-webgis.md), preservada como histórico.

## Estado auditado e ciência congelada

A branch local `codex/aquaclima-webgis` começou limpa, em `9ca26793a02f51b7c72fde4840d0084e1494ad12`, com os três commits `1fc2e42`, `e54427a` e `9ca2679`. A `main` local/remota estava em `b5d45f8133e229ca5b156b64781599cadfc269a6`.

O pacote público já está versionado: **16 arquivos**, incluindo o manifesto e seus 15 arquivos declarados. Os bytes rastreados pelo Git correspondem aos bytes do workspace; a regra `web/data/** -text` evita conversões de fim de linha no checkout. Não é necessário distribuir os dados brutos, caches ou o ambiente científico local para compilar o frontend.

- Versão científica: `2022_2024_recovery_v1`.
- Commit científico congelado: `1440f3e5b28736d12ded226d6baa6b5ca9005262`.
- Pacote científico: `16094dc7ef7ae3e6881b86bc0cbb0ff7b146f0558fc0947957865026882360a3`.
- Pacote público: `7a072a6e29688039b5b775663262ecf6338b35c41386264e75ee789f93068a4d`.
- CSV científico original de observações: `0b1341b57615a5503a68fc8e3e54983f96fd6129ab463c63a517dce6cf05a780`.
- CSV científico original mensal: `d78469f3dd13287d390aa75cceaa745e1dbf9ed83a1b4efbf18a17718e64fc7a`.

Os hashes dos CSVs originais foram conferidos novamente nesta fase. O diff contra o estado inicial da Fase 5 em `src/`, `tests/`, `configs/`, `pyproject.toml` e `uv.lock` permanece vazio. A integração com `main` inclui os commits históricos das fases anteriores que ainda não estavam naquela branch; isso deve ser visível na revisão do PR.

A validação existente verifica contrato 1.0.0, SHA-256, esquemas, integridade cruzada das tabelas, ausências e interseções dos meses dos modelos. A varredura do pacote público não encontrou credenciais, URLs temporárias assinadas ou caminhos absolutos privados.

## Correções de integração

O Vite usa explicitamente `base: '/FTL-Final-Project/'`. O build valida o pacote, compila, copia os dados públicos e executa `verify:dist`, que verifica HTML/CSS/JavaScript e seus assets, caminho-base, `.nojekyll`, ausência de arquivos extras e identidade byte a byte do snapshot científico copiado.

O workflow executa validação científica e frontend em todos os pull requests e em pushes para `main`. O artefato Pages e o job de deploy exigem a ref `refs/heads/main` e um push ou execução manual dessa mesma branch. Pull requests e branches experimentais não publicam. As permissões Pages e OIDC estão limitadas ao job de deployment, que depende da aprovação dos dois jobs de validação.

A suíte Playwright aceita `PLAYWRIGHT_BASE_URL=https://altaeir-13.github.io/FTL-Final-Project/` para testar o site publicado diretamente. Nesse modo não inicia nem reutiliza servidor local. Os cenários com HTTP 404 e bytes adulterados interceptam somente as respostas do navegador de teste, sem modificar o site público.

## Autenticação e configuração observadas

Após o fluxo oficial de login concluído pelo usuário, a CLI confirmou a conta `Altaeir-13` e permissões de escrita/administração. As credenciais são gerenciadas pelo keyring do sistema; nenhum token foi copiado para arquivos do projeto. O conector GitHub continua somente leitura, portanto as operações autorizadas de Git e CI usam a CLI autenticada.

O GitHub Pages já estava com `build_type=workflow`, fonte `main`, URL configurada `https://altaeir-13.github.io/FTL-Final-Project/` e ambiente `github-pages` com política permitindo a branch `main`. Nenhuma ampliação de permissões do ambiente foi necessária.

## Reprodução, integração e publicação

A branch foi publicada e seu SHA remoto conferido. O [PR #1](https://github.com/Altaeir-13/FTL-Final-Project/pull/1) reúne a integração, sem auto-merge.

O primeiro clone remoto independente, em `6372e0c46aab78052e7aed6508630a5619a9c172`, começou sem `data/`, `.venv` ou `web/node_modules`. `npm ci`, validação do pacote, 31 testes frontend/dados, build de produção e quatro testes iniciais de política passaram. Foi criado um ambiente Python novo com `uv sync --locked --python 3.12 --group dev`; os **193 testes científicos passaram em 20,98 s**. Nenhum arquivo adquirido foi copiado para esse clone.

O [primeiro CI remoto](https://github.com/Altaeir-13/FTL-Final-Project/actions/runs/43148142235) aprovou ciência e build/testes do frontend, mas falhou na instalação de Chromium: `ubuntu-latest` passou a fornecer Ubuntu 26.04, que o Playwright 1.56.1 fixado não suporta. Os jobs foram fixados em `ubuntu-24.04`, com teste que impede o retorno involuntário a um runner variável. Os parâmetros e dependências científicos foram preservados.

O clone Windows também revelou conversão CRLF no SVG da marca, mudando apenas os nomes/hash dos bundles. A regra `web/** text eol=lf`, com exceção posterior `web/data/** -text`, estabiliza os arquivos do frontend entre checkouts; os dados científicos continuam sem conversão. Uma nova reprodução limpa confirma o artefato após essa correção.

Uma URL configurada não é, por si só, prova de deployment concluído. Os resultados finais do CI, merge e validação pública serão acrescentados após sua observação.

O [roteiro técnico de três minutos](roteiro-demonstracao.md) utiliza exclusivamente os valores científicos congelados. A [documentação da aplicação](webgis.md) descreve execução, arquitetura, dados e diferenças entre preview local e GitHub Pages.
