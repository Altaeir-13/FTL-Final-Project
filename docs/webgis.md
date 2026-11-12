# WebGIS científico — Fase 4

O frontend estático em `web/` explora os cinco pivôs de demonstração do AquaClima. Consome exclusivamente o dataset `2022_2024_recovery_v1` congelado no commit `1440f3e5b28736d12ded226d6baa6b5ca9005262`. Aquisição, ajuste de modelos e produção de resultados científicos continuam fora do frontend e do processo de publicação.

## Arquitetura e execução

HTML, CSS e módulos JavaScript são compilados pelo Vite. O Leaflet é instalado pelo lock npm e empacotado no build. O mapa desenha as geometrias ANA e uma grade geográfica própria; zoom, enquadramento, escala e navegação funcionam sem tiles. Não há backend obrigatório, CDN, raster bruto ou chamada a serviço comercial em runtime. Links de documentação levam ao repositório; não fornecem dados ao aplicativo.

O estado de seleção sincroniza pivô, índice e período entre séries, cobertura, mudanças e avaliação. Os gráficos representam meses ausentes sem convertê-los em zero ou ligar segmentos através das lacunas. Índices são adimensionais; a precipitação é acumulada mensal em mm. Valores individuais de cenas, contagens, qualidade e proveniência permanecem no pacote. O mapa representa a localização dos polígonos, sem deduzir estado operacional dos equipamentos.

O build usa base relativa (`./`), e a navegação interna não depende de rotas de servidor. Todos os caminhos de assets e dados funcionam sob `/FTL-Final-Project/` no GitHub Pages e sob outros diretórios de hospedagem estática. Os arquivos produzidos em `web/dist/` podem ser servidos por qualquer servidor HTTP estático; abrir `index.html` diretamente por `file://` não atende às regras de carregamento de dados do navegador.

Pré-requisitos locais: Node.js 22.12 ou posterior, npm e, para a suíte científica, Python 3.12 com uv. Em PowerShell, a partir da raiz:

```powershell
Set-Location web
npm ci
npm run data:validate
npm test
npm run build
npm run preview
```

Abra `http://127.0.0.1:4173/FTL-Final-Project/`. O servidor de preview usa o build estático final. Para desenvolvimento com atualização automática, execute `npm run dev`; o Vite informa a URL local. Para encerrar qualquer servidor em primeiro plano, use `Ctrl+C`.

Os testes de navegação usam Chromium local, sem depender de um navegador já aberto:

```powershell
Set-Location web
npx playwright install chromium
npm run test:browser
```

Os testes do navegador iniciam o servidor configurado pelo Playwright e exercitam o build. Execute `npm run build` antes, caso tenha alterado o frontend. No Linux da integração contínua, o workflow instala Chromium com `--with-deps`.

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

`npm test` verifica o contrato e suas falhas, CSV/GeoJSON, tipos, ausência, filtragem por pivô e período, correspondência de séries e valores, elegibilidade e comparação nos mesmos meses. `npm run test:browser` cobre navegação real, seleção sincronizada, assets sob o caminho de projeto, tamanhos de tela e erros de console. O build repete a validação integral do pacote como condição obrigatória para produzir o site.

Execute também a suíte científica a partir da raiz:

```powershell
uv sync --locked
uv run --no-sync python -m pytest -q
```

O workflow executa essa suíte de forma independente do frontend. A reprodução científica offline completa continua documentada em [recuperacao-2022.md](recuperacao-2022.md) e requer os dados locais anteriores; não é executada durante o deployment. Os totais efetivamente obtidos nesta implementação e as capturas reais devem ser consultados no relatório de entrega, sem presumir que o CI remoto já tenha sido executado.

## Publicação gratuita no GitHub Pages

O workflow [.github/workflows/webgis.yml](../.github/workflows/webgis.yml) instala dependências com os locks, valida o pacote público, executa testes de dados, compila, testa no navegador e executa a suíte científica. Publica apenas se ambas as tarefas forem aprovadas. O deployment pode ocorrer por push em `codex/aquaclima-webgis` ou por execução manual do workflow; pull requests somente validam. A branch `main` não é alterada por esse processo.

A configuração da conta ainda precisa ser concluída por uma pessoa com acesso administrativo ao repositório:

1. Em **Settings → Pages → Build and deployment → Source**, selecionar **GitHub Actions**.
2. Em **Settings → Environments → github-pages**, permitir deploy da branch `codex/aquaclima-webgis`, caso as regras atuais permitam apenas a branch padrão; conservar as revisões obrigatórias que já existirem.
3. Conferir que Actions e as ações utilizadas pelo workflow estão permitidos no repositório/organização.
4. Autenticar o Git local quando necessário e enviar a branch de trabalho. Nenhum comando abaixo modifica `main`:

```powershell
gh auth login --hostname github.com
git push -u origin codex/aquaclima-webgis
```

5. Acompanhar **Actions → AquaClima WebGIS**. O job `deploy` só começa depois das verificações e expõe a URL efetiva no environment `github-pages`.

A execução manual pela interface de Actions só aparece quando o workflow também está registrado na branch padrão, conforme a [regra do GitHub para `workflow_dispatch`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch); o primeiro push da branch preparada aciona a publicação sem depender desse botão. Se uma regra do environment impedir o deploy, autorizar a branch ou aprovar o job na configuração existente, sem modificar resultados científicos.

O endereço esperado, sujeito à conclusão e ao sucesso do deployment, é `https://altaeir-13.github.io/FTL-Final-Project/`. **Esse endereço não comprova publicação.** Na preparação local, `gh auth status` informou credencial inválida. O conector GitHub disponível confirmou acesso de leitura ao repositório, com `push=false` e `admin=false`, portanto não permite enviar a branch ou configurar Pages. É necessário autenticar uma conta com permissão de escrita para o push e acesso administrativo para a configuração. Não foi feita alteração remota de Pages nem declarada publicação concluída.

As permissões `pages: write` e `id-token: write` ficam limitadas ao job de deployment. O artefato é ligado ao environment `github-pages`; fonte e regras de branch seguem a [documentação oficial de workflows Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) e a [configuração de fonte Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

Os refs utilizados pelo workflow foram conferidos nas fontes oficiais: [checkout v6](https://github.com/actions/checkout/tree/v6), [setup-node v6](https://github.com/actions/setup-node/tree/v6) e [setup-python v6](https://github.com/actions/setup-python/tree/v6). O setup-uv está fixado no commit completo `68559e99cc807c1eb7e9238fd43a15bba460eec2`, identificado pela [release oficial v10.3.3](https://github.com/astral-sh/setup-uv/releases/tag/v10.3.3).

## Limitações e roteiro de demonstração

O estudo tem cinco pivôs próximos, lacunas mensais, seleção desigual entre estações, cultura e manejo desconhecidos e nenhum rótulo independente de falha real de irrigação. Meses sucessivos e pivôs não são amostras independentes. A seleção de cenas claras pode introduzir viés. A interface não transforma mudanças espectrais em evidência de falha, desperdício ou operação em tempo real. O período permanece janeiro de 2022 a dezembro de 2024; 2025 fica excluído.

Para apresentar o sistema em poucos minutos: mostrar os totais verificáveis; selecionar dois pivôs no mapa; alternar NDVI e NDMI; examinar uma lacuna e a cobertura de 2022; abrir a chuva regional; consultar uma mudança e seus meses intermediários; comparar métodos nos meses comuns; selecionar um pivô sem Ridge e explicar a insuficiência. Encerrar com a metodologia e os limites de interpretação.

Antes da entrega do Capstone em **24 de novembro de 2026**, concluir a configuração e validar a URL pública, repetir o roteiro na máquina/projetor da apresentação, conservar as capturas verificadas e registrar a versão final do frontend. Esses passos não exigem novas aquisições ou alteração da versão científica.

Documentação científica: [contratos](contratos-webgis.md), [recuperação de 2022](recuperacao-2022.md), [modelagem recuperada](modelagem-recuperada.md), [radiometria](radiometria.md), [histórico](historico.md) e [metodologia](metodologia.md).
