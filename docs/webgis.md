# WebGIS científico — Fases 4 e 5

O frontend estático em `web/` explora os cinco pivôs de demonstração do AquaClima. Consome exclusivamente o dataset `2022_2024_recovery_v1` congelado no commit `1440f3e5b28736d12ded226d6baa6b5ca9005262`. Aquisição, ajuste de modelos e produção de resultados científicos continuam fora do frontend e do processo de publicação.

## Arquitetura e execução

HTML, CSS e módulos JavaScript são compilados pelo Vite. O Leaflet é instalado pelo lock npm e empacotado no build. O mapa desenha as geometrias ANA e uma grade geográfica própria; zoom, enquadramento, escala e navegação funcionam sem tiles. Não há backend obrigatório, CDN, raster bruto ou chamada a serviço comercial em runtime. Links de documentação levam ao repositório; não fornecem dados ao aplicativo.

O estado de seleção sincroniza pivô, índice e período entre séries, cobertura, mudanças e avaliação. Os gráficos representam meses ausentes sem convertê-los em zero ou ligar segmentos através das lacunas. Índices são adimensionais; a precipitação é acumulada mensal em mm. Valores individuais de cenas, contagens, qualidade e proveniência permanecem no pacote. O mapa representa a localização dos polígonos, sem deduzir estado operacional dos equipamentos.

O build usa a base explícita **`/FTL-Final-Project/`**, configurada em `web/vite.config.js`. A navegação interna usa âncoras e parâmetros de consulta; não depende de rotas de servidor. JavaScript, CSS, ícones e dados precisam permanecer nesse caminho no GitHub Pages ou no servidor de preview. Hospedar o mesmo build sob outro nome de projeto exige alterar a base e repetir os testes de caminhos. Abrir `index.html` por `file://` não atende às regras de carregamento de dados do navegador.

Pré-requisitos do frontend: Node.js 22.12 ou posterior e npm. Para obter um clone limpo da branch de implementação em PowerShell:

```powershell
git clone --branch codex/aquaclima-webgis --single-branch https://github.com/Altaeir-13/FTL-Final-Project.git
Set-Location FTL-Final-Project/web
npm ci
npm run data:validate
npm test
npm run build
npm run verify:dist
npm run preview
```

O clone contém `web/data/`; não exige `data/raw/`, caches, catálogos locais, Python, uv ou resultados gerados de novo. `npm ci` instala as dependências do lock e requer acesso ao registro npm. A aplicação compilada busca somente seus próprios arquivos estáticos. Após a revisão e o merge do PR, o clone padrão da `main` passa a ser a referência de produção. Em um checkout já existente, a partir da raiz:

```powershell
Set-Location web
npm ci
npm run data:validate
npm test
npm run build
npm run verify:dist
npm run preview
```

Abra `http://127.0.0.1:4173/FTL-Final-Project/`. O servidor de preview usa o build estático final. Para desenvolvimento com atualização automática, execute `npm run dev`; o Vite informa a URL local. Para encerrar qualquer servidor em primeiro plano, use `Ctrl+C`.

O Vite de desenvolvimento também usa `/FTL-Final-Project/` na URL. Se escolher outro servidor HTTP estático, monte o conteúdo de `dist/` nesse prefixo: por exemplo, coloque os arquivos dentro de `<staging>/FTL-Final-Project/` e sirva `<staging>/`. Servir `dist/` diretamente na raiz de um servidor genérico não reproduz o endereço de produção dos assets. `npm run preview` já faz a montagem correta.

Os testes de navegação usam Chromium local, sem depender de um navegador já aberto:

```powershell
Set-Location web
npx playwright install chromium
npm run test:browser
```

Os testes do navegador iniciam o servidor configurado pelo Playwright e exercitam o build. Execute `npm run build` antes, caso tenha alterado o frontend. A integração contínua fixa o runner em `ubuntu-24.04`, compatível com o Playwright 1.56.1 do lock, e instala Chromium com `--with-deps`. A regra `web/** text eol=lf` estabiliza fontes e assets do frontend entre checkouts; `web/data/** -text` preserva os bytes científicos. Para usar o Edge instalado no Windows, sem alterar as dependências do projeto:

```powershell
$env:PLAYWRIGHT_CHANNEL = 'msedge'
npm run test:browser
Remove-Item Env:PLAYWRIGHT_CHANNEL
```

Após um deployment concluído, execute os mesmos **12 cenários** diretamente na URL pública. Esse modo não inicia nem reutiliza servidor local:

```powershell
$env:PLAYWRIGHT_BASE_URL = 'https://altaeir-13.github.io/FTL-Final-Project/'
npm run test:browser
Remove-Item Env:PLAYWRIGHT_BASE_URL
```

`PLAYWRIGHT_BASE_URL` só aceita a origem HTTPS e o caminho público acima, com a barra final. `PLAYWRIGHT_CHANNEL=msedge` pode ser combinado com esse modo no Windows. Remova as variáveis ao voltar aos testes locais. A aprovação local não substitui a execução pública, que confirma caminhos, assets e dados efetivamente publicados.

## Pacote científico e integridade

O ponto de entrada científico real é `data/recovery/curated/2022_2024_recovery_v1/webgis/manifest.json`. O manifesto aponta para `packages/16094dc7ef7ae3e6881b86bc0cbb0ff7b146f0558fc0947957865026882360a3/`. O exportador original está em `aquaclima.reporting.contracts.export_contracts`, implementado em `src/aquaclima/reporting/contracts.py`.

| Artefato congelado | SHA-256 |
| --- | --- |
| Pacote WebGIS científico | `16094dc7ef7ae3e6881b86bc0cbb0ff7b146f0558fc0947957865026882360a3` |
| Pacote público derivado | `7a072a6e29688039b5b775663262ecf6338b35c41386264e75ee789f93068a4d` |
| Dataset original `observations.csv` | `0b1341b57615a5503a68fc8e3e54983f96fd6129ab463c63a517dce6cf05a780` |
| Dataset original `monthly.csv` | `d78469f3dd13287d390aa75cceaa745e1dbf9ed83a1b4efbf18a17718e64fc7a` |
| Contrato exportado `observations.csv` | `f1f49735587af9c8509326b5613954211d03d2a8b3585706ba76d600b45bd2bf` |
| Contrato exportado `monthly.csv` | `ddffa80c402fc089f20d7c3cab52f678b3239335487ee9cdaea0c2c061832fb4` |
| Contrato `schemas.json` | `1fb29b98d832a3ed625f0fd2c514626c34edda2c17ecf69626aeed46ffbc3172` |

Os contratos exportados conservam e acrescentam proveniência; seus hashes diferem dos CSVs de consolidação. O manifesto é a autoridade para cada arquivo, tamanho, quantidade de linhas e referência de esquema. A identidade do pacote é o SHA-256 calculado sobre os nomes ordenados e os digests binários de seus arquivos, seguindo o exportador original.

O snapshot público versionado está em `web/data/manifest.json`. Ele mantém os **11 arquivos centrais do contrato 1.0.0 byte a byte**, soma os três arquivos de comparação comum já congelados e um registro `publication.json`. Por isso recebe identidade própria, indicada pelo `package_sha256` do manifesto público. `source_package_sha256`, hashes de origem e commit científico em `publication.json` vinculam o derivado à ciência original. O manifesto público não substitui o científico.

O build valida versão 1.0.0, arquivos obrigatórios, caminhos relativos seguros, tamanho, SHA-256 de cada arquivo, identidade do pacote, esquema e tipos dos registros, chaves, geometrias e correspondência entre tabelas. Confere os valores científicos congelados, contagens, ausências, qualidade, vínculos de modelos e interseções exatas da comparação comum. Uma ausência, corrupção ou inconsistência encerra o processo com erro explícito antes da compilação. Essa verificação lê os resultados; não os reajusta nem os reescreve.

Depois da compilação, `npm run verify:dist` verifica a árvore efetivamente publicável, os contratos copiados e as referências de assets sob `/FTL-Final-Project/`. Essa etapa faz parte do build e também pode ser executada isoladamente. Ela impede confundir um build aprovado com um diretório de publicação contendo arquivos laterais, dependências de desenvolvimento ou caminhos impróprios. O navegador ainda confere tamanho e SHA-256 dos arquivos ao carregar.

`pivot_id` e `processing_baseline` permanecem textos. Campos CSV vazios tornam-se `null`; datas ISO, meses `YYYY-MM`, IDs das cenas e métodos radiométricos são preservados. Métricas indisponíveis conservam `null`. Os esquemas originais estão em `schemas.json`; `publication.json` documenta a extensão independente para os arquivos de comparação comum.

## Exportação pública determinística e privacidade

Uma instalação nova pode compilar usando apenas o snapshot público versionado, sem baixar os dados de aquisição. Para gerar novamente o snapshot a partir da cópia científica **já existente** no computador:

```powershell
Set-Location web
npm run data:export
npm run data:validate
```

O comando `data:export` apenas valida e copia os contratos e a comparação já calculada em `data/recovery/curated/2022_2024_recovery_v1/comparison/`. Falha se a cópia local congelada estiver ausente ou divergente. Não consulta catálogos, não adquire imagens, não calcula novos índices e não ajusta modelos. Mesmos insumos produzem os mesmos bytes e hashes; arquivos já idênticos não são regravados.

A seleção pública é uma lista fechada de arquivos de contrato, comparação e registro de publicação. A revisão automática rejeita caminhos absolutos privados, assinaturas temporárias, padrões de credenciais e URLs com parâmetros ou fora dos hosts científicos permitidos. A versão revisada não exigiu remoção de campos dos arquivos científicos. Caminhos **relativos** dos inventários são conservados como identificadores de proveniência; não são assets a buscar no site.

Rasters, caches, catálogos completos, ambientes Python, `data/` original e credenciais não integram o artefato Pages. O workflow envia somente `web/dist/`, formado pela interface compilada e o subconjunto público validado. Dependências de desenvolvimento, testes e código Python também ficam fora do site estático.

## Modelos e interpretação

As métricas individuais descrevem conjuntos distintos de meses e são identificadas como avaliação própria de cada método. A comparação usa exclusivamente `common_month_metrics.csv`, `common_month_predictions.csv` e `comparison_report.json` congelados. Mostra a interseção explícita de meses de 2024 e só publica métricas quando há pelo menos seis referências comuns. Não escolhe um vencedor universal nem compara diretamente números calculados sobre períodos diferentes.

A mediana sazonal é elegível nos cinco pivôs. A Ridge harmônica é elegível somente em 8087 e 16708; os outros três exibem insuficiência de dados, sem métricas zero. O benchmark ingênuo usa o mesmo mês de 2023 como referência retrospectiva. Os resultados são reconstrução espectral exploratória, não validação agronômica de falhas.

CHIRPS representa uma única célula regional compartilhada, de aproximadamente 0,05°, nos 36 meses; as cinco linhas por mês não são cinco estações independentes. O acumulado mensal completo fornece contexto retrospectivo, disponível depois do encerramento do mês. Os modelos desta versão não sustentam previsão antecipada de chuva ou diagnóstico de irrigação.

## Testes e preservação da ciência

`npm test` verifica o contrato e suas falhas, CSV/GeoJSON, tipos, ausência, filtragem por pivô e período, correspondência de séries e valores, elegibilidade e comparação nos mesmos meses. `npm run test:browser` cobre navegação real, seleção sincronizada, assets sob o caminho de projeto, tamanhos de tela e erros de console. Confere também que a aplicação funciona com recursos fora do diretório público bloqueados, sem localhost remoto, tiles, APIs, CDNs ou WebSockets. O build repete a validação integral do pacote e a inspeção de `dist` como condições obrigatórias para produzir o site.

`node --test .github/tests/webgis-workflow.test.mjs`, executado a partir da raiz, verifica a política do CI. Testa que PRs, branches experimentais, tags e execuções manuais fora da `main` não enviam artefato Pages nem fazem deploy. A leitura normaliza CRLF/LF para funcionar também em clones Windows com `core.autocrlf`.

Execute também a suíte científica a partir da raiz:

```powershell
uv sync --locked
uv run --no-sync python -m pytest -q
```

O workflow executa essa suíte de forma independente do frontend, preservando os 193 testes científicos existentes. A reprodução científica offline completa continua documentada em [recuperacao-2022.md](recuperacao-2022.md) e requer os dados locais anteriores; não é executada durante o deployment. Os totais e as capturas efetivamente obtidos na Fase 5 devem ser consultados no [relatório de finalização](finalizacao-webgis.md). O [relatório da Fase 4](entrega-webgis.md) permanece como registro histórico, com as condições de acesso e política de publicação daquele momento.

## Publicação gratuita no GitHub Pages

O workflow [.github/workflows/webgis.yml](../.github/workflows/webgis.yml) instala dependências com os locks, valida o pacote público, executa testes de dados, compila, examina `dist`, testa no navegador e executa a suíte científica. Roda em **todos os pull requests**, sem filtro de caminhos, e em **pushes da `main`**. `workflow_dispatch` permite verificação manual.

Somente **push na `main` ou execução manual selecionando `main`** pode enviar o artefato Pages e iniciar deployment. As duas condições são explícitas no workflow. PRs e branches experimentais nunca publicam, mesmo quando iniciados manualmente. O job `deploy` depende da aprovação dos jobs `science` e `frontend`. O único diretório enviado é `web/dist/`.

O fluxo de revisão é: enviar `codex/aquaclima-webgis`, abrir PR para `main`, aguardar as verificações e a revisão humana, fazer o merge pela política do repositório e acompanhar o workflow disparado na `main`. Não existe merge automático no workflow. O CI não adquire novos dados nem altera o commit científico congelado.

A inspeção da Fase 5 confirmou login local de `Altaeir-13` no gerenciador de credenciais, permissões de escrita/administração e Pages com `build_type=workflow`, fonte `main`. O environment `github-pages` já possui política que permite `main`. Isso confirma a configuração, não a conclusão de um deployment. Antes de publicar, conferir:

1. Em **Settings → Pages → Build and deployment → Source**, manter **GitHub Actions**.
2. Em **Settings → Environments → github-pages**, manter `main` entre as branches permitidas e conservar as revisões obrigatórias existentes. Não é necessário autorizar a branch experimental.
3. Conferir que Actions e as ações utilizadas pelo workflow estão permitidos no repositório/organização.
4. Confirmar o acesso e enviar a branch de trabalho. Nenhum comando abaixo modifica `main`:

```powershell
gh auth status --hostname github.com
git push -u origin codex/aquaclima-webgis
```

5. Abrir o PR para `main`, aguardar revisão humana e verificações. Depois do merge, acompanhar **Actions → AquaClima WebGIS** na `main`. O job `deploy` só começa após ciência e frontend aprovados e expõe a URL efetiva no environment `github-pages`.

A execução manual pela interface de Actions exige o workflow registrado na branch padrão, conforme a [regra do GitHub para `workflow_dispatch`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch). Para publicar manualmente, selecionar `main`. Uma execução manual da branch experimental pode rodar verificações, mas seus gates bloqueiam o artefato Pages e o deploy. Se houver revisão obrigatória no environment, a aprovação continua pertencendo ao responsável definido pelo repositório.

O endereço esperado, sujeito ao sucesso do deployment, é [AquaClima no GitHub Pages](https://altaeir-13.github.io/FTL-Final-Project/). **A existência desse endereço não comprova publicação desta versão.** A evidência de conclusão deve reunir o run aprovado da `main`, a URL retornada pelo deployment e os testes dos 12 cenários nessa URL. O estado efetivamente observado fica no [relatório de finalização da Fase 5](finalizacao-webgis.md). As restrições de credenciais registradas na Fase 4 são históricas e foram superadas pelo login válido confirmado na Fase 5.

As permissões `pages: write` e `id-token: write` ficam limitadas ao job de deployment. O artefato é ligado ao environment `github-pages`; fonte e regras de branch seguem a [documentação oficial de workflows Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) e a [configuração de fonte Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

Os refs utilizados pelo workflow foram conferidos nas fontes oficiais: [checkout v6](https://github.com/actions/checkout/tree/v6), [setup-node v6](https://github.com/actions/setup-node/tree/v6) e [setup-python v6](https://github.com/actions/setup-python/tree/v6). O setup-uv está fixado no commit completo `68559e99cc807c1eb7e9238fd43a15bba460eec2`, identificado pela [release oficial v10.3.3](https://github.com/astral-sh/setup-uv/releases/tag/v10.3.3).

## Diferenças entre preview e site público

| Aspecto | Preview local | GitHub Pages |
| --- | --- | --- |
| Endereço | `http://127.0.0.1:4173/FTL-Final-Project/` | `https://altaeir-13.github.io/FTL-Final-Project/` |
| Contexto seguro para SHA-256 | O navegador trata loopback como origem confiável | HTTPS fornece o contexto seguro |
| Fonte dos arquivos | `web/dist/` servido por `serve.mjs` | Artefato estático enviado pelo workflow aprovado da `main` |
| Cache | O preview envia `Cache-Control: no-cache` | Cabeçalhos e cache são controlados pelo GitHub Pages |
| Recursos de runtime | Somente arquivos locais sob a base do projeto | Somente arquivos HTTPS sob a mesma base pública |
| CSP acrescentada pelo aplicativo | Nenhuma | Nenhuma |

Não há service worker para armazenar uma versão offline. JavaScript e CSS recebem nomes com hash no build; o manifesto e seus arquivos científicos também possuem identidade verificável. Se a versão pública parecer antiga após um deployment, atualizar sem cache (`Ctrl+F5`), conferir o run/commit publicado e comparar `data/manifest.json` com o snapshot da versão. Um erro de integridade deve ser investigado como inconsistência entre arquivos servidos; não se deve contornar a validação para abrir um pacote divergente.

O HTML não declara `Content-Security-Policy` e o aplicativo não configura headers de CSP no GitHub Pages. A integridade SHA-256, a validação do build e os testes que restringem recursos ao diretório publicado são mecanismos separados. Erros de CSP introduzidos por extensão, proxy ou política do navegador devem ser identificados no ambiente correspondente. Alterar políticas ou permitir CDNs não é uma correção necessária para essa demonstração.

Em caso de falha pública, consultar primeiro o job `deploy`, a aba Network e o console. Confirmar HTTPS, o caminho `/FTL-Final-Project/`, status 200 de `assets/*` e `data/manifest.json` e os hashes do pacote. Repetir `PLAYWRIGHT_BASE_URL` verifica o site remoto de fato; um preview funcionando em localhost não elimina um erro de publicação.

## Limitações e roteiro de demonstração

O estudo tem cinco pivôs próximos, lacunas mensais, seleção desigual entre estações, cultura e manejo desconhecidos e nenhum rótulo independente de falha real de irrigação. Meses sucessivos e pivôs não são amostras independentes. A seleção de cenas claras pode introduzir viés. A interface não transforma mudanças espectrais em evidência de falha, desperdício ou operação em tempo real. O período permanece janeiro de 2022 a dezembro de 2024; 2025 fica excluído.

O [roteiro de demonstração](roteiro-demonstracao.md) organiza esses recursos em três minutos, com totais verificáveis, exemplos de meses comuns e uma explicação final das limitações.

Antes da entrega do Capstone em **24 de novembro de 2026**, concluir a configuração e validar a URL pública, repetir o roteiro na máquina/projetor da apresentação, conservar as capturas verificadas e registrar a versão final do frontend. Esses passos não exigem novas aquisições ou alteração da versão científica.

Documentação científica: [contratos](contratos-webgis.md), [recuperação de 2022](recuperacao-2022.md), [modelagem recuperada](modelagem-recuperada.md), [radiometria](radiometria.md), [histórico](historico.md) e [metodologia](metodologia.md).
