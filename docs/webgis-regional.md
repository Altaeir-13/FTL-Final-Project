# WebGIS multirregional — implementação e verificação da fase 6

Referência: **15/11/2026**. A versão desta branch foi testada localmente. A publicação continua restrita à `main`, após merge decidido pelo usuário; nenhum deployment da branch regional foi realizado.

## Estudos e níveis de evidência

A abertura apresenta o problema de acompanhar mudanças na vegetação irrigada, o vínculo territorial com Caxias e as contribuições de pesquisa aos ODS 6 e 13, com contexto dos ODS 2 e 9. O texto não atribui economia de água, consumo medido, diagnóstico de falhas ou operação comercial ao protótipo.

O seletor de estudos diferencia:

- **Paracatu, MG: estudo concluído.** Mantém cinco pivôs, 256 observações, 57 cenas, 141/180 espaços pivô/mês e modelos congelados. Os filtros, o mapa e as métricas do observatório existente continuam exclusivos de Paracatu.
- **Guadalupe, PI: prova exploratória de portabilidade.** A auditoria ANA selecionou cinco dos 12 pivôs municipais; dez atendem ao corte geométrico e de área. O painel independente apresenta 29 observações aceitas em seis datas, 30 tentativas, 29/115 espaços na grade contínua de 23 meses (**25,2%**) e seis meses alvo. A proporção de 29/30 espaços alvo é 96,7%; não corresponde à cobertura contínua do período. Nenhum modelo regional foi ajustado.

Caxias aparece como motivação e referência pública de distância. Não é apresentada como área monitorada. A tabela comparativa contém os 14 municípios efetivamente auditados, incluindo quatro alternativas suplementares que não atingiram três pivôs. O relatório de seleção documenta que a decisão original foi tomada sobre os dez candidatos principais, antes da aquisição de rasters.

O mapa de Guadalupe reutiliza o componente vetorial com parâmetros próprios de identificação. Não depende de basemap, tiles, CDN ou chamadas ao serviço ANA em tempo de execução. Seleções regionais não modificam os filtros científicos de Paracatu. Uma falha no pacote regional apresenta aviso local e mantém Paracatu utilizável.

## Catálogo independente e integridade

`web/data/manifest.json` e todos os arquivos em `web/data/packages/` permanecem byte a byte preservados. O contrato WebGIS 1.0.0 e o pacote público de Paracatu `7a072a6e29688039b5b775663262ecf6338b35c41386264e75ee789f93068a4d` não foram alterados.

O catálogo superior está em `web/regions/catalog.json`, com versão própria 1.0.0, referência ao manifesto original e descriptor regional separado. O pacote `packages/<sha256>/regional.json` contém a decisão, o método, o inventário comparativo, a amostra GeoJSON WGS84, observações, tentativas incluindo rejeições, grade mensal, proveniência radiométrica e evidência de reprodução offline. Não contém rasters, caminhos privados ou credenciais. Os PNGs têm descritores individuais de tamanho e SHA-256.

O build verifica hashes, lista exata de arquivos públicos, chaves municipais, separação entre regiões, contagens, medianas mensais, lacunas, qualidade mínima de 70%, proveniência offline e compatibilidade das grades das imagens. O navegador repete a verificação de SHA-256 do pacote e das duas imagens antes de exibir o painel. O pacote científico congelado continua validado pelo contrato original. `web/regions/** -text` protege os bytes revisados entre checkouts.

O exportador explícito `web/scripts/export-regional.mjs` lê somente os caminhos e campos declarados do estudo e produz o snapshot público. **O build não executa aquisição nem exige o cache científico local**: usa o snapshot versionado. O exportador normaliza os booleanos `True`/`False` do CSV científico para booleanos JSON e conserva ausências como `null`. Os identificadores são `PI:<FID>`, acompanhados da chave `guadalupe-pi`.

## Comparação visual real

Foram incluídos dois derivados reais Sentinel-2 L2A C1 do mesmo grupo:

| Data | Aquisição | Qualidade dos cinco pivôs |
|---|---|---|
| 18/07/2023 | `S2B_T23MPN_20230718T132238_L2A` | 100% de pixels conjuntos válidos em cada pivô |
| 22/07/2024 | `S2B_T23MPN_20240722T132235_L2A` | 100% de pixels conjuntos válidos em cada pivô |

A composição é **falsa cor**, com R=B08/NIR, G=B04/vermelho e B=B11/SWIR1. As bandas de 10 m foram agregadas à grade B11 de 20 m, em EPSG:32723. As duas datas possuem a mesma transformação espacial, dimensões e limites; o estiramento fixo de reflectância 0–0,6 permite comparação visual consistente. Pixels fora da máscara SCL 4/5 ou com reflectância inválida aparecem em cinza. Os contornos e rótulos são dos polígonos ANA reais. PNGs são derivados visuais; cores não diagnosticam irrigação.

Os dados, hashes, parâmetros e georreferência estão em `docs/evidencias/guadalupe-pi/comparison/provenance.json`. A geração é reproduzível por `scripts/render_regional_comparison.py`, sobre os recortes já adquiridos e verificados, sem download adicional.

## Investigação temporal

A tabela de mudanças de Paracatu agora apresenta também a precipitação CHIRPS e a qualidade mínima das cenas nos dois meses exatos de cada evento, junto dos valores inicial/final, diferença, intervalo, lacunas e identificadores das cenas. Esses campos são recuperados por chave pivô/mês; ausência de precipitação permanece ausente, e zero real permanece zero. Nenhum evento ou limiar científico foi recalculado.

Em Guadalupe, os gráficos preservam todos os espaços da grade de janeiro/2023 a novembro/2024. A tabela de tentativas inclui a rejeição de `PI:5802`, em 24/03/2024, com 52,5% de pixels válidos e índices ausentes. É possível alternar entre os cinco pivôs e NDVI/NDMI. Não são traçadas linhas através dos meses sem observação.

## Execução e testes efetivamente realizados

No diretório `web`, com dependências do lock instaladas:

```powershell
node scripts/export-regional.mjs --pilot   # exige o estudo científico local
npm run regions:validate
npm test
npm run build
npm run verify:dist
$env:PLAYWRIGHT_CHANNEL='msedge'
npm run test:browser
node scripts/capture-regional.mjs
```

| Verificação | Resultado observado nesta implementação |
|---|---|
| Testes frontend, contratos, exportação, integridade e contexto temporal | **37 aprovados** |
| Navegação real Edge, incluindo os 12 cenários originais e quatro regionais | **16 aprovados**, 17,5 s |
| Política de CI e deployment | **5 aprovados**, main-only preservada |
| Build Vite e verificador estático | Aprovados; 25 arquivos e três assets de aplicação |
| Artefato final local SHA-256 | `753605cd4fc2caff31b7420fc8568bd816e9ef96455bf1d956cc093d14f14a71` |
| Site público da main, antes das alterações regionais | **12 cenários originais aprovados**, 16,7 s |

Os quatro cenários novos verificam isolamento de regiões e valores exatos dos gráficos, rejeição preservada, comparação real com datas e legendas, viewport de 390 px, inventário/proveniência e corrupção regional sem interrupção de Paracatu. O conjunto original continua cobrindo métricas, ausências, navegação por teclado, contraste textual, redução de movimento, bloqueio de recursos externos e erros de integridade científica.

A suíte de navegador local precisou de execução fora do sandbox para iniciar servidor e Edge; isso não altera o artefato publicado. Nenhuma dependência de servidor local entra no runtime de produção. O teste público foi executado diretamente em `https://altaeir-13.github.io/FTL-Final-Project/`, sem servidor local; ele valida a **main já publicada**, não antecipa a publicação desta branch.

## Capturas autênticas

As capturas em `docs/images/webgis-studies.png`, `webgis-regional.png`, `webgis-real-comparison.png` e `webgis-regional-mobile.png` foram produzidas pelo Edge sobre o build de produção local e inspecionadas visualmente. O script de captura é versionado; as telas não foram compostas artificialmente. A comparação registra os derivados de satélite reais. O screenshot móvel confirma leitura em 390 px; tabelas largas mantêm rolagem interna.

## Limitações e publicação

A prova regional cobre seis meses previamente selecionados, com amostragem desigual e sem identificação de culturas ou dados de campo. Ela comprova a execução reproduzível do pipeline nesses pivôs e datas; não demonstra sazonalidade completa, generalização de modelos, demanda ou consumo hídrico. A precipitação é contexto de célula regional, com ausências fora dos meses adquiridos.

A branch está pronta para revisão. Após merge autorizado na `main`, o workflow existente pode publicar o mesmo snapshot. Somente depois de um deployment efetivamente aprovado deve-se executar a suíte regional contra a URL pública e registrar a nova validação. A apresentação pode demonstrar o build local revisado enquanto o merge aguarda decisão.
