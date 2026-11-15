# Roteiro final do AquaClima

Autor: Randerson Sousa de Sá Nunes. Entrega FTL: 24/11/2026. O roteiro usa a versão congelada `2022_2024_recovery_v1`. As falas regionais devem acompanhar o estado real do [relatório MA/PI](selecao-regional-ma-pi.md), sem converter candidatos em áreas monitoradas.

## Apresentação de cinco minutos

| Tempo | Slide | Fala sugerida |
|---|---|---|
| 0:00–0:30 | 1. AquaClima | “Sou Randerson Sousa de Sá Nunes, de Caxias, no Maranhão. O AquaClima investiga como organizar imagens públicas e precipitação para acompanhar o comportamento espectral de áreas agrícolas irrigadas. A entrega é um protótipo científico reproduzível com demonstração WebGIS.” |
| 0:30–1:05 | 2. Problema | “Imagens de datas diferentes só ajudam se conhecemos sua qualidade e calibração. Nuvens, meses sem observação e mudanças no processamento podem comprometer uma comparação. Nosso problema é construir uma série rastreável, distinguindo observação, lacuna e interpretação.” |
| 1:05–1:35 | 3. Relevância e ODS | “A relação com o ODS 6 está no apoio à pesquisa sobre gestão da água. O ODS 13 aparece na capacidade de compreender o contexto climático. Não medimos economia de água. Desenvolvemos uma infraestrutura aberta para organizar evidências, também relacionada aos ODS 2 e 9.” |
| 1:35–2:20 | 4. Dados e método | “Usamos polígonos ANA de 2022, Sentinel-2 L2A e chuva mensal CHIRPS v3. Aplicamos escala e offset, alinhamos as bandas e mantemos apenas pixels aprovados pela SCL. Uma observação exige pelo menos 70% de pixels válidos. Calculamos a mediana espacial de NDVI e NDMI e a mediana das cenas de cada mês. Lacunas permanecem explícitas.” |
| 2:20–2:55 | 5. Paracatu | “Paracatu ofereceu pivôs próximos para desenvolver e verificar o pipeline. O estudo concluído tem cinco equipamentos, 256 observações em 57 cenas e 141 dos 180 espaços pivô/mês. São 78,3% de cobertura entre 2022 e 2024. As falhas de cobertura aparecem na própria interface.” |
| 2:55–3:45 | 6. Resultados | “Treinamos com 2022–2023 e avaliamos 2024. A mediana sazonal atende aos critérios nos cinco pivôs. A Ridge atende em dois, pois os outros não representam todos os meses do calendário no treino. A tabela usa os mesmos sete meses para os três métodos. MAE é o erro absoluto médio e RMSE dá maior peso a erros grandes. A Ridge não vence em toda métrica. Esses erros são de índices espectrais, sem avaliação de defeitos de irrigação.” |
| 3:45–4:25 | 7. Expansão | “Minha ligação com Caxias motivou a investigação do Maranhão e do Piauí. A base ANA não trouxe registros associados a Caxias nessa edição. Selecionamos Guadalupe por critérios explícitos e processamos 29 observações aceitas em cinco pivôs e seis datas, com chuva integrada e reprodução offline. São seis meses amostrados, sem série mensal contínua. A prova demonstra execução do pipeline na amostra, sem validar modelos agronômicos regionais.” |
| 4:25–5:00 | 8. Conclusões | “A contribuição é uma cadeia aberta, auditável e reproduzível, com comunicação das limitações. Para uso operacional, precisamos de dados de campo, culturas e manejo, avaliação geográfica independente e custos medidos. Vou mostrar agora como o WebGIS liga o polígono, a observação, a qualidade e sua proveniência.” |

Ensaiar em voz alta com cronômetro. A tabela distribui cinco minutos; a velocidade real depende do apresentador. Cortar exemplos antes de reduzir a clareza dos limites científicos.

## Demonstração de aproximadamente três minutos

Antes da apresentação, abrir o site público e o preview local já compilado. Conferir o caso/versão e o [checklist](checklist-entrega-ftl.md). A versão local serve de contingência de conexão e deve ser identificada como tal.

1. **0:00–0:30, contexto territorial.** Mostrar Paracatu como caso concluído e a região MA/PI com seu estado real. Explicar que Caxias é a origem territorial da pesquisa. Selecionar um pivô no mapa e conferir o FID.
2. **0:30–1:10, séries.** Alternar NDVI/NDMI e apontar um valor observado com data e qualidade. Mostrar a chuva mensal e explicar a diferença de resolução e de janela temporal. Não atribuir uma variação a irrigação sem dados independentes.
3. **1:10–1:40, lacunas.** Abrir cobertura/qualidade. Mostrar um mês ausente e o motivo registrado. Explicar que ausência não equivale a índice zero e que a nuvem do catálogo não substitui a máscara no próprio pivô.
4. **1:40–2:20, comparação temporal/modelos.** Mostrar os valores anterior e posterior e a diferença, incluindo meses sem observação entre eles. Abrir modelos e usar a comparação em meses comuns. Explicar por que três pivôs não recebem Ridge elegível.
5. **2:20–3:00, proveniência.** Abrir a origem da observação ou do pacote. Mostrar período 2022–2024, versão, hashes e links metodológicos. Encerrar com a contribuição e o próximo passo de validação de campo. Se a prova regional estiver integrada, mostrar brevemente seus dados descritivos e o rótulo exploratório, sem transportar métricas de Paracatu.

Se um recurso visual não existir na versão demonstrada, mostrar a evidência equivalente nas tabelas e no relatório. Não prometer interação inexistente. O roteiro técnico detalhado do caso concluído permanece em [roteiro-demonstracao.md](roteiro-demonstracao.md).

## Versão rápida de aproximadamente um minuto

“O AquaClima é meu Capstone do Future Tech Leaders. Ele integra polígonos oficiais da ANA, reflectância Sentinel-2 e chuva CHIRPS para acompanhar índices espectrais de áreas irrigadas. Em cinco pivôs de Paracatu, processamos 256 observações aceitas e cobrimos 141 de 180 espaços mensais entre 2022 e 2024. O WebGIS permite verificar séries, lacunas, qualidade e proveniência. Avaliamos baselines sazonais com treino em 2022–2023 e validação em 2024, sem incluir 2025. Minha origem em Caxias motivou uma investigação territorial no Maranhão e Piauí, com a seleção guiada por dados reais. A contribuição é uma metodologia aberta e reproduzível. Detectar falhas de irrigação ou quantificar economia de água ainda exige dados de campo e validação específica.”

## Perguntas prováveis da banca

**Por que Paracatu?** Foi uma escolha de viabilidade para o desenvolvimento: relevância agrícola e uma amostra compacta de pivôs oficiais na unidade de São Marcos. Isso facilita janelas pequenas e cenas compartilhadas. Não constitui amostra representativa de todos os irrigantes.

**Por que expandir para Maranhão/Piauí?** O autor é de Caxias e deseja investigar um território próximo da sua realidade. A nova região é escolhida por geometrias oficiais, disponibilidade de imagens, qualidade esperada, proximidade e custo. Motivação pessoal não substitui a verificação.

**O que os índices medem?** NDVI contrasta vermelho e infravermelho próximo e descreve características espectrais da vegetação. NDMI contrasta infravermelho próximo e SWIR, com sensibilidade à água do dossel. Ambos também respondem a cultura, estágio, solo e mistura de pixels. Não medem diretamente consumo ou vazão.

**Como foram escolhidas as cenas?** Busca STAC com interseção espacial, período e filtros explícitos, favorecendo cobertura e menor nuvem de cena. A aceitação acontece depois do recorte, calibração e SCL, com pelo menos 70% de pixels conjuntamente válidos no pivô. Fonte e rejeições ficam registradas.

**Por que há meses sem dados?** Pode faltar cena elegível ou a observação pode ser rejeitada por nuvens, sombra, qualidade ou aquisição incompleta. O pipeline preserva a diferença entre essas situações e não preenche índices silenciosamente.

**Por que somente dois pivôs têm Ridge elegível?** O protocolo exige pelo menos 18 meses aceitos e todos os 12 meses do calendário no treino 2022–2023. Os pivôs 17373, 17382 e 19997 não têm janeiro no treino. O limiar foi preservado após a recuperação e as métricas deles ficam vazias.

**O que significam MAE e RMSE?** MAE resume a magnitude média do erro. RMSE aumenta a influência de erros grandes. São adimensionais porque o alvo é um índice. Não são porcentagem de acerto. Para comparar métodos, usamos os mesmos meses e explicitamos o tamanho da avaliação.

**Qual modelo foi melhor?** Nos sete meses comuns, a Ridge tem menor MAE nos dois índices dos dois pivôs elegíveis. Para NDVI em 16708, a mediana tem RMSE ligeiramente menor. A amostra e a dependência entre observações não permitem declarar superioridade universal.

**O modelo detecta falhas de irrigação?** Não há essa validação. Há mudanças espectrais descritivas e reconstruções sazonais. Colheita, rotação, fenologia ou nuvens residuais também podem explicar mudanças. Seriam necessários rótulos e dados independentes de operação e campo.

**Qual a diferença entre demanda e consumo hídrico?** Demanda é a necessidade de água sob condições e critérios definidos. Consumo se relaciona à parcela efetivamente utilizada e não restituída ao sistema no recorte considerado. Retirada e água aplicada são outras grandezas. Este protótipo não estima nenhuma delas por NDVI/NDMI e chuva isoladamente.

**A tecnologia funciona em outras regiões?** A prova de Guadalupe processou 29 observações reais em cinco pivôs e seis datas, integrou CHIRPS e reproduziu cinco arquivos offline. Isso demonstra execução do procedimento nessa amostra. Os 96,7% referem-se aos 30 espaços planejados, enquanto a grade completa de 23 meses tem 25,2% de cobertura. Validação agronômica e generalização dos modelos exigem protocolo externo adicional.

**Como poderia virar startup?** A hipótese é organizar evidências territoriais para apoiar acompanhamento agrícola. O próximo passo é testar necessidades de usuários e estabelecer parcerias de campo. Só depois se pode validar alertas, valor econômico, operação e modelo de receita. O Capstone não comprova tração comercial.

**Qual o custo operacional?** Não foram usadas APIs pagas nem infraestrutura faturável. Há custos de tempo, computador, conexão e armazenamento. O piloto de Guadalupe registrou 53,14 MB de corpos HTTP e 144,15 MB armazenados, incluindo os rasters CHIRPS reutilizados localmente. São recursos de uma prova limitada, com escopo explícito. Não existe ainda custo por cliente validado.

**2025 entrou na avaliação?** Não. A avaliação congelada usa 2022–2024. Três datas de 2025 foram examinadas em um piloto anterior de engenharia, com exposição exploratória registrada. Elas não entram no treinamento, nas predições ou nas métricas apresentadas.

**A reprodução é possível sem conexão?** A consolidação científica foi reproduzida no ambiente original com os caches previamente adquiridos, requisições proibidas e igualdade byte a byte. Um clone sem caches consegue reproduzir o build do WebGIS pelo pacote público. São dois escopos distintos de reprodução.

**Como a chuva foi validada?** A integração verifica arquivo, célula, unidade, mês e proveniência. O produto CHIRPS possui avaliação publicada, mas o projeto não realizou comparação local independente com pluviômetros. Portanto, chuva permanece contexto regional estimado.

**O AquaClima comprovou impacto nos ODS?** O trabalho tem alinhamento metodológico e educativo com água e clima. Não mediu os indicadores oficiais nem comprovou economia de água, produtividade ou redução de emissões.

## Evidências de apoio

[Relatório científico](relatorio-final-ftl.md), [seleção territorial](selecao-regional-ma-pi.md), [métricas congeladas](modelagem-recuperada.md), [contratos](contratos-webgis.md) e [apresentação editável](apresentacao/aquaclima-ftl.pptx).
