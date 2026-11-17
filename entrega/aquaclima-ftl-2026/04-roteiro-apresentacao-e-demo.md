# Roteiro final do AquaClima

Autor: Randerson Sousa de Sá Nunes. Revisão de release: 17/11/2026, sobre a Fase 7 de 16/11. Entrega FTL: 24/11/2026. O roteiro usa a versão congelada `2022_2024_recovery_v1` e a prova exploratória de Guadalupe, preservadas na Fase 7. As novas interações organizam evidências já produzidas; não demonstram novas descobertas agronômicas. O [PR #3](https://github.com/Altaeir-13/FTL-Final-Project/pull/3) foi integrado à `main` no commit `ad107d0c29c63ad9eb9f91a5970d96906676e3df`; a publicação foi aprovada e a suíte de 25 cenários passou na URL pública em 17/11. A [revisão da apresentação](REVISAO-APRESENTACAO.md) registra os arquivos e limites desta conferência.

## Apresentação de cinco minutos

| Tempo | Slide | Fala sugerida |
|---|---|---|
| 0:00–0:30 | 1. AquaClima | “Sou Randerson Sousa de Sá Nunes, de Caxias, no Maranhão. O AquaClima investiga como organizar imagens públicas e precipitação para acompanhar o comportamento espectral de áreas agrícolas irrigadas. A entrega é um protótipo científico reproduzível com demonstração WebGIS.” |
| 0:30–1:05 | 2. Problema | “Imagens de datas diferentes só ajudam se conhecemos sua qualidade e calibração. Nuvens, meses sem observação e mudanças no processamento podem comprometer uma comparação. Nosso problema é construir uma série rastreável, distinguindo observação, lacuna e interpretação.” |
| 1:05–1:35 | 3. Relevância e ODS | “A relação com o ODS 6 está no apoio à pesquisa sobre gestão da água. O ODS 13 aparece na capacidade de compreender o contexto climático. Não medimos economia de água. Desenvolvemos uma infraestrutura aberta para organizar evidências, também relacionada aos ODS 2 e 9.” |
| 1:35–2:20 | 4. Dados e método | “Usamos polígonos ANA de 2022, Sentinel-2 L2A e chuva mensal CHIRPS v3. Aplicamos escala e offset, alinhamos as bandas e mantemos apenas pixels aprovados pela SCL. Uma observação exige pelo menos 70% de pixels válidos. Calculamos a mediana espacial de NDVI e NDMI e a mediana das cenas de cada mês. Lacunas permanecem explícitas.” |
| 2:20–2:55 | 5. Paracatu | “Paracatu ofereceu pivôs próximos para desenvolver e verificar o pipeline. O estudo concluído tem cinco equipamentos, 256 observações em 57 cenas e 141 dos 180 espaços pivô/mês. São 78,3% de cobertura entre 2022 e 2024. As lacunas de cobertura aparecem na própria interface.” |
| 2:55–3:45 | 6. Resultados | “Treinamos com 2022–2023 e avaliamos 2024. A mediana sazonal atende aos critérios nos cinco pivôs. A Ridge atende em dois, pois os outros não representam todos os meses do calendário no treino. A tabela usa os mesmos sete meses para os três métodos. MAE é o erro absoluto médio e RMSE dá maior peso a erros grandes. A Ridge não vence em toda métrica. Esses erros são de índices espectrais, sem avaliação de defeitos de irrigação.” |
| 3:45–4:25 | 7. Expansão | “Minha ligação com Caxias motivou a investigação regional. Selecionamos Guadalupe por critérios oficiais e processamos 29 observações aceitas em cinco pivôs e seis datas. Estas imagens reais de julho de 2023 e julho de 2024 usam a mesma grade e falsa cor. A chuva foi integrada e a reprodução offline preservou os arquivos. Os seis meses amostrados não formam uma série contínua. A prova demonstra execução do pipeline nessa amostra, sem modelo regional validado.” |
| 4:25–5:00 | 8. Conclusões | “A contribuição é uma cadeia aberta, auditável e reproduzível, com comunicação das limitações. A investigação guiada compara observações reais e gera uma ficha de evidências com fontes e hashes. Para uso operacional, precisamos de dados de campo, culturas e manejo, avaliação geográfica independente e custos medidos. Vou mostrar como o WebGIS liga o polígono, a observação, a qualidade e sua proveniência.” |

Ensaiar em voz alta com cronômetro. A tabela distribui cinco minutos; a velocidade real depende do apresentador. Cortar exemplos antes de reduzir a clareza dos limites científicos.

## Demonstração de aproximadamente três minutos

Antes da apresentação, abrir o [site público](https://altaeir-13.github.io/FTL-Final-Project/) e conferir o [checklist](CHECKLIST-ENTREGA.md). A Fase 7 está publicada pelo [workflow aprovado da `main`](https://github.com/Altaeir-13/FTL-Final-Project/actions/runs/44067496065), após o merge do PR #3. A verificação pública de 17/11 aprovou **25 cenários reais no Edge**, sem iniciar servidor local, sem cenários ignorados e sem falhas ou instabilidade registradas; consulte o [registro](evidencias/playwright-publico.json). O preview local compilado continua disponível como contingência, identificado ao público. Acionar **Iniciar demonstração**; o avanço é manual, sem temporizador obrigatório.

| Tempo | Passo no WebGIS | Fala e ação |
|---|---|---|
| 0:00–0:25 | 1. O problema | “Precisamos acompanhar mudanças espectrais com qualidade conhecida. Caxias é minha origem territorial; não é apresentada como área já monitorada.” Mostrar os papéis geográficos na visão territorial. |
| 0:25–1:00 | 2. O estudo de Paracatu | “A validação começou em Paracatu: cinco pivôs, 256 observações, 57 cenas e 78,3% de cobertura em 2022–2024.” Mostrar mapa, cobertura e resultados congelados; os números são derivados do pacote real. |
| 1:00–1:50 | 3. Uma investigação | Mostrar o pivô e os dois agregados mensais disponíveis. “Esta é a diferença assinada B menos A. A chuva corresponde aos meses indicados; a qualidade e as cenas estão registradas. Lacunas não foram preenchidas.” Abrir **Gerar ficha de evidências**, mostrar seleção, identificador e hash; fechar a prévia para continuar. A impressão pode ficar para depois da fala. |
| 1:50–2:30 | 4. Expansão para Guadalupe | “A seleção oficial levou a Guadalupe, uma prova exploratória com cinco pivôs e 29 observações em seis datas.” Mostrar as imagens reais de 18/07/2023 e 22/07/2024, na mesma grade e falsa cor. “O recorte contém o grupo dos cinco pivôs. Não existe modelo regional validado.” |
| 2:30–3:00 | 5. Conclusões e limitações | “O AquaClima organiza evidências rastreáveis e períodos para revisão. A mudança pode refletir fenologia, colheita, manejo e ambiente. Não atribuímos causa ou economia de água. O próximo passo é validação de campo.” Encerrar a demonstração, restaurando a seleção anterior. |

Usar **Avançar**, **Voltar**, **Reiniciar** e **Encerrar**; Escape também encerra. O passo e o progresso ficam visíveis. O link da investigação preserva região, pivô, observações e pacote; pode ser copiado após a fala. Se uma observação não possuir derivado visual, mostrar a mensagem de indisponibilidade e seus valores, sem substituir por outra imagem. A [documentação da investigação](https://github.com/Altaeir-13/FTL-Final-Project/blob/ad107d0c29c63ad9eb9f91a5970d96906676e3df/docs/investigacao-guiada-ftl.md) registra as regras e os exemplos. O roteiro técnico anterior de Paracatu permanece em [roteiro-demonstracao.md](https://github.com/Altaeir-13/FTL-Final-Project/blob/ad107d0c29c63ad9eb9f91a5970d96906676e3df/docs/roteiro-demonstracao.md).

## Versão rápida de aproximadamente um minuto

“O AquaClima é meu Capstone do Future Tech Leaders. Integra polígonos ANA, Sentinel-2 e chuva CHIRPS para investigar mudanças espectrais. O estudo de Paracatu tem 256 observações e 78,3% de cobertura mensal em 2022–2024, com baselines avaliados em 2024. Guadalupe acrescenta 29 observações exploratórias, sem modelo regional validado. O WebGIS orienta a comparação de duas observações reais e gera uma ficha com valores, qualidade, proveniência e hashes. Caxias é minha origem e motivação territorial. A contribuição é uma metodologia aberta e uma tecnologia rastreável de investigação. Diagnóstico de irrigação e economia de água ainda exigem validação de campo.”

## Perguntas prováveis da banca

**Por que Paracatu?** Foi uma escolha de viabilidade para o desenvolvimento: relevância agrícola e uma amostra compacta de pivôs oficiais na unidade de São Marcos. Isso facilita janelas pequenas e cenas compartilhadas. Não constitui amostra representativa de todos os irrigantes.

**Por que expandir para Maranhão/Piauí?** O autor é de Caxias e deseja investigar um território próximo da sua realidade. Guadalupe foi escolhida por geometrias oficiais, disponibilidade de imagens, qualidade esperada, proximidade e custo. Motivação pessoal não substitui a verificação.

**O que os índices medem?** NDVI contrasta vermelho e infravermelho próximo e descreve características espectrais da vegetação. NDMI contrasta infravermelho próximo e SWIR, com sensibilidade à água do dossel. Ambos também respondem a cultura, estágio, solo e mistura de pixels. Não medem diretamente consumo ou vazão.

**Como foram escolhidas as cenas?** Busca STAC com interseção espacial, período e filtros explícitos, favorecendo cobertura e menor nuvem de cena. A aceitação acontece depois do recorte, calibração e SCL, com pelo menos 70% de pixels conjuntamente válidos no pivô. Fonte e rejeições ficam registradas.

**Por que há meses sem dados?** Pode faltar cena elegível ou a observação pode ser rejeitada por nuvens, sombra, qualidade ou aquisição incompleta. O pipeline preserva a diferença entre essas situações e não preenche índices silenciosamente.

**Por que somente dois pivôs têm Ridge elegível?** O protocolo exige pelo menos 18 meses aceitos e todos os 12 meses do calendário no treino 2022–2023. Os pivôs 17373, 17382 e 19997 não têm janeiro no treino. O limiar foi preservado após a recuperação e as métricas deles ficam vazias.

**O que significam MAE e RMSE?** MAE resume a magnitude média do erro. RMSE aumenta a influência de erros grandes. São adimensionais porque o alvo é um índice. Não são porcentagem de acerto. Para comparar métodos, usamos os mesmos meses e explicitamos o tamanho da avaliação.

**Qual modelo foi melhor?** Nos sete meses comuns, a Ridge tem menor MAE nos dois índices dos dois pivôs elegíveis. Para NDVI em 16708, a mediana tem RMSE ligeiramente menor. A amostra e a dependência entre observações não permitem declarar superioridade universal.

**O modelo detecta falhas de irrigação?** Não há essa validação. Há mudanças espectrais descritivas e reconstruções sazonais. Colheita, rotação, fenologia ou nuvens residuais também podem explicar mudanças. Seriam necessários rótulos e dados independentes de operação e campo.

**A ficha é um laudo agronômico?** É um registro descritivo da seleção feita no WebGIS. Preserva observações, chuva, qualidade, imagens correspondentes, proveniência, limites e pacote utilizado. Não atribui causa, recomenda manejo ou certifica falha de irrigação. Pode ser impressa ou salva como PDF localmente.

**A interpretação usa inteligência artificial generativa?** A síntese da investigação utiliza templates determinísticos sobre os dados publicados, sem modelo de linguagem externo ou API paga. O identificador científico permanece o mesmo quando a seleção e os parâmetros são iguais, mesmo que a impressão ocorra em outro dia.

**Qual a diferença entre demanda e consumo hídrico?** Demanda é a necessidade de água sob condições e critérios definidos. Consumo se relaciona à parcela efetivamente utilizada e não restituída ao sistema no recorte considerado. Retirada e água aplicada são outras grandezas. Este protótipo não estima nenhuma delas por NDVI/NDMI e chuva isoladamente.

**A tecnologia funciona em outras regiões?** A prova de Guadalupe processou 29 observações reais em cinco pivôs e seis datas, integrou CHIRPS e reproduziu cinco arquivos offline. Isso demonstra execução do procedimento nessa amostra. Os 96,7% referem-se aos 30 espaços planejados, enquanto a grade completa de 23 meses tem 25,2% de cobertura. Validação agronômica e generalização dos modelos exigem protocolo externo adicional.

**Como poderia virar startup?** A hipótese é organizar evidências territoriais para apoiar acompanhamento agrícola. O próximo passo é testar necessidades de usuários e estabelecer parcerias de campo. Só depois se pode validar alertas, valor econômico, operação e modelo de receita. O Capstone não comprova tração comercial.

**Qual o custo operacional?** Não foram usadas APIs pagas nem infraestrutura faturável. Há custos de tempo, computador, conexão e armazenamento. O piloto de Guadalupe registrou 53,14 MB de corpos HTTP e 144,15 MB armazenados, incluindo os rasters CHIRPS reutilizados localmente. São recursos de uma prova limitada, com escopo explícito. Não existe ainda custo por cliente validado.

**2025 entrou na avaliação?** Não. A avaliação congelada usa 2022–2024. Três datas de 2025 foram examinadas em um piloto anterior de engenharia, com exposição exploratória registrada. Elas não entram no treinamento, nas predições ou nas métricas apresentadas.

**A reprodução é possível sem conexão?** A consolidação científica foi reproduzida no ambiente original com os caches previamente adquiridos, requisições proibidas e igualdade byte a byte. Um clone sem caches consegue reproduzir o build do WebGIS pelo pacote público. São dois escopos distintos de reprodução.

**Como a chuva foi validada?** A integração verifica arquivo, célula, unidade, mês e proveniência. O produto CHIRPS possui avaliação publicada, mas o projeto não realizou comparação local independente com pluviômetros. Portanto, chuva permanece contexto regional estimado.

**O AquaClima comprovou impacto nos ODS?** O trabalho tem alinhamento metodológico e educativo com água e clima. Não mediu os indicadores oficiais nem comprovou economia de água, produtividade ou redução de emissões.

## Evidências de apoio

[Relatório científico](https://github.com/Altaeir-13/FTL-Final-Project/blob/ad107d0c29c63ad9eb9f91a5970d96906676e3df/docs/relatorio-final-ftl.md), [seleção territorial](https://github.com/Altaeir-13/FTL-Final-Project/blob/ad107d0c29c63ad9eb9f91a5970d96906676e3df/docs/selecao-regional-ma-pi.md), [métricas congeladas](https://github.com/Altaeir-13/FTL-Final-Project/blob/ad107d0c29c63ad9eb9f91a5970d96906676e3df/docs/modelagem-recuperada.md), [contratos](https://github.com/Altaeir-13/FTL-Final-Project/blob/ad107d0c29c63ad9eb9f91a5970d96906676e3df/docs/contratos-webgis.md) e [apresentação editável da Fase 7](02-apresentacao-editavel.pptx).
