# Auditoria radiométrica da recuperação de 2022

Auditoria executada em 11/11/2026, sobre os cinco polígonos ANA originais. Os recortes, produtos XML, catálogos e relatórios estão em `data/recovery/`, fora do Git. O diagnóstico precedeu a recuperação. A autorização científica local admite **somente produtos Planetary Computer com PB 05.10**, convertidos por seus próprios metadados SAFE. Ela não autoriza toda a coleção antiga da Earth Search.

## Conversão e verificação por produto

O adaptador `ingestion/planetary.py` mantém os valores digitais nativos dos COGs. Para B04, B08 e B11, calcula `reflectância = (DN + BOA_ADD_OFFSET) / BOA_QUANTIFICATION_VALUE`. O XML `MTD_MSIL2A.xml` fornece os campos; data da imagem ou aparência dos índices não determinam o offset. O parser verifica identidade SAFE, nível L2A, baseline no XML/STAC/nome, valor de quantificação positivo, banda, NoData 0 e saturação 65535. PB ≥ 04 exige a lista completa de 13 offsets, inclusive as posições 3/B04, 7/B08 e 11/B11. Os seis produtos amostrados declaram quantificação 10.000; PB04 e PB05.10 declaram −1.000 DN, correspondendo a escala 0,0001 e offset −0,1.

O produto PB03.00 de 24/01 não contém lista de offsets e usa a convenção anterior, escala 0,0001 e offset zero. Sua reflectância nativa foi diagnosticada, mas o produto foi excluído da consolidação. A mudança PB04 incluiu harmonização radiométrica do Sentinel-2B em relação ao Sentinel-2A. Não houve comparação local coincidente PB03 versus reprocessamento, e multiplicar arbitrariamente a reflectância L2A por 1,011 não reproduziria toda a cadeia de correção atmosférica. [SentiWiki: produtos](https://sentiwiki.copernicus.eu/web/s2-products), [processamento e baselines](https://sentiwiki.copernicus.eu/web/s2-processing).

Os COGs Planetary Computer originais não anunciam a calibração BOA em `raster:bands` nesses itens. O adaptador registra que seus parâmetros foram derivados do XML, preservando URL sem assinatura, SHA-256, identificação nativa e produto SAFE. As assinaturas temporárias públicas de leitura ficam em memória; o cliente HTTP remove parâmetros sensíveis de logs e proveniência. A documentação dos mantenedores também registra a necessidade de considerar a mudança radiométrica. [Microsoft: discussão de harmonização BOA](https://github.com/microsoft/PlanetaryComputer/issues/134).

Todos os recortes amostrados usam EPSG:32723, B04/B08 a 10 m e B11/SCL a 20 m, grades verificadas no próprio raster. Os índices mantêm a metodologia anterior: SCL 4/5, máscara antes da média espacial, B04/B08 agregadas para a grade nativa de B11, razões após a conversão e mediana por pivô. A aceitação requer ≥ 70% de pixels conjuntos válidos. Nenhum valor negativo é deslocado ou truncado para tornar o índice plausível; ele fica inválido segundo a política terrestre existente.

## Comparação independente do mesmo produto

O produto `S2A_MSIL2A_20220320T132241_N0510_R038_T23KKA_20240601T152534.SAFE` está nos dois provedores. Os recortes Planetary Computer foram comparados aos arquivos C1 adquiridos anteriormente, sem nova consulta ou download C1.

| Banda | Pixels comparados | Grade/CRS iguais | Pixels DN diferentes |
|---|---:|---|---:|
| B04 | 34.300 | Sim | 0 |
| B08 | 34.300 | Sim | 0 |
| B11 | 9.090 | Sim | 0 |
| SCL | 9.090 | Sim | 0 |

São **86.780 comparações de DN com diferença zero**. O XML do produto informa a mesma transformação usada pelo C1. Para o pivô 8087, o processamento independente dos arquivos PC produz NDVI 0,5211692452 e NDMI 0,0379900001, iguais aos valores do processamento C1. Isso verifica a compatibilidade da conversão do provedor para esse produto, não uma validação absoluta com observações de campo.

## Por que PB04 não foi incorporado

Antes de calcular as diferenças PB04/PB05.10, foi registrado `compatibility-protocol.json`: mesma grade, todos os cinco pivôs aceitos nas duas versões, percentil 95 da diferença absoluta de reflectância ≤ 0,02 nos pixels comuns claros e diferença absoluta das medianas de NDVI/NDMI por pivô ≤ 0,02. Esse limiar é uma decisão de engenharia deste piloto, sem equivalência a uma norma universal ou precisão agronômica.

Foram comparadas as versões PB04/PB05.10 das aquisições de 20/03 e 28/07/2022. Em março, os percentis 95 das diferenças absolutas de reflectância foram 0,0048/B04, 0,0078/B08 e 0,005695/B11. Em julho, foram 0,0086, 0,0134 e 0,0087. As grades coincidiram, mas o pivô 8087 de março apresentou ΔNDVI = **+0,0352454** e ΔNDMI = **+0,0330517** na versão reprocessada. As diferenças dos outros quatro pivôs de março ficaram abaixo de 0,0014; as dos cinco pivôs de julho ficaram abaixo de 0,0010.

O critério previamente definido falhou. PB04 ficou fora desta consolidação; o limiar não foi alterado para obter aprovação. Os dados não permitem atribuir essa diferença a uma única etapa de processamento, tampouco declarar que todo produto PB04 seja intrinsecamente inválido. A alternativa PB05.10 passou pela comparação de produto idêntico e evita essa mistura de versões.

## Amostra úmida e seca

Foram recortados seis produtos: 24/01/PB03, 29/01/PB04, 20/03/PB04 e PB05.10, e 28/07/PB04 e PB05.10. Em 24/01 os cinco pivôs passam na qualidade, porém são excluídos pelo protocolo radiométrico. Em 29/01 nenhum pivô tem pixels válidos suficientes. Em 28/07/PB05.10 os cinco têm 100% de pixels conjuntos válidos.

As distribuições completas de reflectância, mínimos/máximos de DN, quantis 0/1/50/99/100%, contagens de negativos, resolução e transformação estão em `radiometry/pixel-audit.json`. Não houve reflectância negativa nos seis recortes amostrados. Em 28/07/PB05.10, as medianas de reflectância dos retângulos de recorte foram 0,1710/B04, 0,2802/B08 e 0,3807/B11. Elas incluem o retângulo completo e não substituem as estatísticas mascaradas de cada pivô.

## Evidência real do risco na coleção antiga

Também foram lidos recortes da Earth Search `sentinel-2-l2a` para 29/01 e 28/07. As comparações têm a mesma aquisição e PB04, mas gerações SAFE diferentes; essa limitação está no relatório e impede alegar igualdade exata dos produtos. Os dois itens legados declaram escala 0,0001 e offset −0,1, apesar de indicadores diferentes de offset previamente aplicado.

| Aquisição | `boa_offset_applied` | Mediana DN legado − PC: B04/B08/B11 | Diferença de reflectância ao seguir `raster:bands`: B04/B08/B11 |
|---|---|---|---|
| 29/01 | false | −4 / −4 / 0 | −0,0004 / −0,0004 / 0 |
| 28/07 | true | −1.008 / −1.020 / −1.024 | −0,1008 / −0,1020 / −0,1024 |

A SCL coincide nos 9.090 pixels em ambas as aquisições. O deslocamento espectral observado em julho é compatível com o risco de aplicar novamente um offset já incorporado, somado a diferenças de geração. Não foi inferida uma regra universal de reparação a partir de dois itens. Esses recortes são exclusivamente diagnósticos. Relatório: `radiometry/legacy-pixel-comparison.json`. [Element84: relato de inconsistência de offset](https://github.com/Element84/earth-search/issues/71).

## Recursos, integridade e reprodução

O inventário da amostra PC registra 13.689.421 bytes e 135 requisições HTTP, incluindo uma primeira execução interrompida durante a serialização do relatório e retomada pelo cache. A auditoria legada acrescenta 9.830.400 bytes e 83 requisições. Total dos dois inventários de pixels: **23.519.821 bytes**, abaixo do teto de 50 MB reservado para esse diagnóstico. Consultas de catálogo e XML anteriores têm inventários próprios e devem entrar no total geral da fase.

Os dois scripts foram reexecutados offline, cada um com **zero requisições e zero bytes**, recomputando as comparações. O pacote de evidências da autorização inclui hashes do protocolo, relatórios, XML e recortes brutos. `compatibility.json` não varia com tempo de execução ou contadores HTTP. Sua reprodução foi verificada com SHA-256 `5c90b29fbc920fbc41ff33d27857acd7c3fc64932e4a766870fe2bae506ea124`.

```powershell
uv run --no-sync python scripts/audit_radiometry.py --offline
uv run --no-sync python scripts/audit_legacy_radiometry.py --offline
```

Os scripts exigem os arquivos locais efetivamente adquiridos, incluindo os catálogos nativos. Se faltar um arquivo íntegro, o modo offline falha explicitamente. Sem `--offline`, eles permitem apenas as amostras listadas, com limites próprios de 50 MB para PC e 20 MB para o legado; não adquirem cenas inteiras nem ampliam o histórico. A aquisição histórica tem planejamento e limites separados.
