# Demonstração AquaClima — três minutos

O roteiro apresenta a versão científica `2022_2024_recovery_v1`, congelada em `1440f3e`. É uma demonstração de pesquisa com cinco pivôs de Paracatu, MG. Não representa operação comercial em tempo real nem demonstra diagnóstico de falhas de irrigação.

## Preparação

Usar o build verificado conforme [webgis.md](webgis.md). A URL pública esperada é [AquaClima no GitHub Pages](https://altaeir-13.github.io/FTL-Final-Project/); confirmar no [relatório da Fase 5](finalizacao-webgis.md) se esta versão já teve deployment e testes públicos aprovados. Se a publicação estiver pendente, apresentar o servidor local em `http://127.0.0.1:4173/FTL-Final-Project/` e identificar essa condição.

Antes da apresentação, abrir a aplicação em tela de notebook/projetor, selecionar **ANA 8087**, índice **NDVI** e **Todo o período**. Manter o zoom do navegador em um tamanho legível. O mapa e os gráficos não precisam de tiles, CDN ou backend; uma nova sessão ainda precisa receber os arquivos estáticos do servidor.

Sete referências para conferir antes de falar:

| Referência | Valor congelado |
| --- | --- |
| Pivôs ANA | 5 |
| Observações espectrais aceitas | 256 |
| Cenas Sentinel-2 L2A | 57 |
| Espaços pivô/mês observados | 141 de 180 |
| Cobertura espectral total | 78,3% |
| Meses de precipitação CHIRPS | 36, em uma célula regional compartilhada |
| Elegibilidade dos modelos sazonais | Mediana em 5 pivôs; Ridge em 2 |

## Sequência de três minutos

| Tempo | Ação na interface | Mensagem sugerida |
| --- | --- | --- |
| 0:00–0:25 | Mostrar os indicadores e **Explorar pivôs**. Enquadrar os cinco polígonos. | “Monitoramos cinco pivôs de demonstração em Paracatu, com polígonos reais da ANA e 256 observações Sentinel-2 aceitas entre 2022 e 2024. A cobertura observada é 78,3%; não estamos operando um sistema em tempo real.” |
| 0:25–0:55 | Selecionar **ANA 8087**, abrir **Séries temporais**, alternar **NDVI** e **NDMI**, passar o cursor ou usar Tab em um ponto. | “NDVI e NDMI são índices adimensionais de resposta da vegetação. Cada ponto mensal é a mediana das medianas das cenas aceitas. O tooltip e a tabela mostram valores, datas e qualidade; os intervalos sem observação ficam visíveis.” |
| 0:55–1:20 | Escolher **2022**, abrir **Cobertura e qualidade** e selecionar **ANA 8087 · 2022-01**. Mostrar o cartão de precipitação ao lado das séries. | “Janeiro de 2022 está ausente, não é um índice igual a zero. A seleção exige pelo menos 70% de pixels válidos; qualidade limitada pede revisão. CHIRPS é um acumulado mensal regional compartilhado pelos cinco pivôs, conhecido após o fim do mês.” |
| 1:20–1:45 | Voltar a **Todo o período**, abrir **Mudanças espectrais**, expandir **Ver evidência** de uma linha. | “Esta é uma mudança espectral observada entre dois meses. Os valores inicial e final, diferença, distância temporal, meses sem observação e proveniência permitem interpretar a evidência. A mudança não comprova falha de irrigação.” |
| 1:45–2:25 | Selecionar **NDVI**, abrir **Modelos e avaliação** e manter **ANA 8087 / Três métodos**. Mostrar os meses comuns; depois selecionar **ANA 17373**. | “A avaliação é reconstrução espectral exploratória: treino em 2022–2023 e validação em 2024. Comparo modelos somente nos mesmos meses. A Ridge de 8087 usa sete meses neste contraste; em 17373 faltam dados para esse modelo e as métricas permanecem ausentes.” |
| 2:25–3:00 | Em **ANA 17373**, escolher **Mediana × mesmo mês de 2023**; depois abrir **Metodologia**. | “Ainda podemos consultar os métodos elegíveis neste pivô. Não identificamos cultura ou manejo, não temos rótulos independentes de falhas reais, e os pivôs próximos compartilham contexto regional. A ferramenta torna dados e limitações verificáveis; não produz um diagnóstico agronômico.” |

No contraste de três métodos para **ANA 8087 / NDVI**, os sete meses comuns são **março, abril, maio, julho, agosto, setembro e outubro de 2024**. O MAE Ridge congelado é **0,296783**, apresentado com quatro casas na tabela como **0,2968**. São resultados já exportados, sem ajuste ou recálculo pela interface. MAE e RMSE medem concordância espectral; não medem economia de água nem acurácia de detecção de falhas. Não comparar esse número diretamente às métricas individuais calculadas sobre dez meses.

## Se houver uma pergunta

- **“Por que faltam meses?”** Nuvens, sombras, pixels inválidos e disponibilidade dos catálogos limitam as observações; a seleção de dias claros pode introduzir viés sazonal.
- **“Por que não interpolar?”** A demonstração preserva os resultados congelados e distingue medição ausente de reconstrução exploratória. Não apresenta valores imputados como observados.
- **“O mapa é imagem de satélite?”** Não. É cartografia vetorial dos polígonos ANA com uma grade própria. Os índices vêm das cenas Sentinel-2 processadas pelo pipeline científico.
- **“São cinco estações de chuva?”** Não. Os cinco pivôs compartilham uma célula CHIRPS de aproximadamente 0,05°.
- **“Qual modelo venceu?”** O resultado depende de pivô, índice, métrica e conjunto de meses comuns. A amostra não sustenta um vencedor universal ou generalização para outras áreas.
- **“Uma mudança significa falha?”** Não. Cultura, fenologia, colheita, manejo e qualidade das imagens também podem alterar os índices. Faltam rótulos independentes para atribuir causas.

O relatório científico detalha [recuperação](recuperacao-2022.md), [radiometria](radiometria.md) e [modelagem](modelagem-recuperada.md). Para a entrega em **24/11/2026**, repetir o roteiro no equipamento da apresentação, verificar o link público e manter uma cópia do build local verificado como apoio.
