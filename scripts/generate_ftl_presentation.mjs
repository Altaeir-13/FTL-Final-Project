/** Editable FTL deck, generated from the immutable public evidence.
 * Environment paths come from Codex load_workspace_dependencies, never installation.
 * Requires AQUACLIMA_ARTIFACT_MODULES, AQUACLIMA_PRESENTATIONS_SKILL,
 * and AQUACLIMA_RUNTIME_PYTHON. Run from the repository root.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MODULES = process.env.AQUACLIMA_ARTIFACT_MODULES;
const SKILL = process.env.AQUACLIMA_PRESENTATIONS_SKILL;
const PYTHON = process.env.AQUACLIMA_RUNTIME_PYTHON;
if (!MODULES || !SKILL || !PYTHON) throw new Error('Set runtime paths documented in docs/apresentacao/README.md');
process.env.RUNTIME_NODE_MODULES ??= MODULES;
const { Presentation, PresentationFile } = await import(pathToFileURL(path.join(MODULES, '@oai/artifact-tool/dist/artifact_tool.mjs')).href);
const { applyPresentationChartFont, finalizePresentation } = await import(pathToFileURL(path.join(SKILL, 'container_tools/artifact_tool_utils.mjs')).href);
const OUT = path.join(ROOT, 'docs/apresentacao');
const BUILD = path.join(ROOT, 'build/ftl-presentation');
await fs.mkdir(BUILD, {recursive:true});
await fs.mkdir(OUT, {recursive:true});
const evidence = JSON.parse(await fs.readFile(path.join(OUT, 'evidencias-paracatu.json'), 'utf8'));
const regional = JSON.parse(await fs.readFile(path.join(OUT, 'evidencias-regionais.json'), 'utf8'));
const comparison = JSON.parse(await fs.readFile(path.join(ROOT, 'docs/evidencias/guadalupe-pi/comparison/provenance.json'), 'utf8'));
if(evidence.observations !== 256 || evidence.observed_pivot_months !== 141) throw new Error('Frozen evidence mismatch');
const deck = Presentation.create({slideSize:{width:1280,height:720}});
const C = {ink:'#173f32', secondary:'#435e50',paper:'#f7f8f2',teal:'#247b75',olive:'#8ca55b',light:'#dce7d5'};
function text(slide, value, x,y,w,h,size=28,bold=false,color=C.ink){
 const shape = slide.shapes.add({geometry:'textbox',name:value.slice(0,50),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 shape.text = value;
 shape.text.style = {typeface:'Arial',fontSize:size,bold,color,wrap:'square',autoFit:'none',insets:0,verticalAlignment:'top'};
 return shape;
}
function base(title){const s=deck.slides.add();s.background.fill=C.paper;text(s,title,64,42,1152,88,44,true);return s;}
function foot(s,value){text(s,value,64,648,1152,45,18,false,C.secondary);}
function note(s,value){s.speakerNotes.text=value;}
async function picture(s,relative,x,y,w,h,alt='Captura autêntica do WebGIS AquaClima, caso Paracatu'){const b=await fs.readFile(path.join(ROOT,relative));s.images.add({blob:b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),contentType:relative.endsWith('.jpg')?'image/jpeg':'image/png',alt,fit:'contain',position:{left:x,top:y,width:w,height:h}});}
function table(s,values,position,widths,fontSize=24){
 const t=s.tables.add({rows:values.length,columns:values[0].length,...position,values,columnWidths:widths});
 t.borders.assign({fill:'#c7d5c6',width:1,style:'solid'});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[r].length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?C.ink:'#ffffff';
  cell.text.style={typeface:'Arial',fontSize,bold:r===0,color:r===0?'#ffffff':C.ink,insets:10,verticalAlignment:'middle'};
 }
 return t;
}

// 1. Cover, no decorative or synthetic imagery.
{
 const s=deck.slides.add();s.background.fill=C.ink;
 text(s,'AquaClima',72,148,1130,110,80,true,'#ffffff');
 text(s,'Monitoramento espectral de áreas\nagrícolas irrigadas',76,282,1090,130,42,false,'#e6eedf');
 text(s,'Randerson Sousa de Sá Nunes\nFuture Tech Leaders Brasil',76,500,1090,76,28,false,'#e6eedf');
 note(s,'Protótipo científico aplicado. Autor de Caxias/MA. Caso concluído Paracatu 2022–2024, investigação regional independente. Código aberto: https://github.com/Altaeir-13/FTL-Final-Project. Não há economia de água ou diagnóstico de irrigação demonstrado.');
}
// 2. Actual coverage chart shows the observational problem.
{
 const s=base('O problema do acompanhamento temporal');
 text(s,'Imagens de datas diferentes exigem\ncalibração e controle de qualidade.',64,166,560,126,32,true);
 text(s,'Nuvens e lacunas limitam a leitura\ndas mudanças na vegetação.\n\nCada valor precisa de data, qualidade\ne origem verificáveis.',64,326,550,240,28);
 const chart=s.charts.add('bar',{position:{left:664,top:168,width:552,height:400},categories:['2022','2023','2024'],series:[{name:'Observados',values:[35,57,49],fill:C.teal},{name:'Ausentes',values:[25,3,11],fill:'#d7decf'}],hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:22,typeface:'Arial',fill:C.ink}},barOptions:{direction:'column',grouping:'stacked',gapWidth:110},xAxis:{textStyle:{fontSize:22,typeface:'Arial',fill:C.ink}},yAxis:{min:0,max:60,majorUnit:20,textStyle:{fontSize:20,typeface:'Arial',fill:C.ink}},dataLabels:{showValue:true,position:'center',textStyle:{fontSize:23,color:C.ink,typeface:'Arial'}}});
 applyPresentationChartFont(chart,{fontFamily:'Arial'});
 foot(s,'Cobertura real de Paracatu. Cada ano contém 60 espaços possíveis: 5 pivôs × 12 meses.');
 note(s,'Fonte: pacote público congelado '+evidence.public_package_sha256+', monthly.csv. Contagem realizada em scripts/prepare_ftl_evidence.py, sem imputação. Observados=35,57,49 e ausentes=25,3,11.');
}
// 3. SDG relations, with appropriately limited claims.
{
 const s=base('Água, clima e pesquisa aberta');
 text(s,'ODS 6',64,170,380,64,44,true,C.teal);
 text(s,'Informação territorial para\napoiar pesquisas sobre\ngestão da água.',64,258,510,165,32);
 text(s,'ODS 13',686,170,450,64,44,true,C.teal);
 text(s,'Capacidade de interpretar\nvegetação e variabilidade\nda precipitação.',686,258,510,165,32);
 text(s,'ODS 2 e 9: agricultura e infraestrutura aberta de informação.',64,494,1150,64,26);
 foot(s,'Alinhamento metodológico e educativo. O estudo não mede impacto nos indicadores oficiais.');
 note(s,'Fontes oficiais ONU: https://sdgs.un.org/goals/goal6 e https://sdgs.un.org/goals/goal13. Relações com ODS 6.4/6.5 e 13.3 são interpretações da contribuição metodológica, sem mensurar eficiência hídrica, emissões ou produtividade. Não há economia de água demonstrada.');
}
// 4. Method and formulas.
{
 const s=base('Dados e metodologia');
 text(s,'ANA/SNIRH',64,162,380,45,30,true);text(s,'Polígonos reais de pivôs de 2022',64,213,600,45,26);
 text(s,'Sentinel-2 L2A',64,290,480,45,30,true);text(s,'Reflectância calibrada, bandas alinhadas e SCL',64,341,650,72,26);
 text(s,'CHIRPS v3',64,440,420,45,30,true);text(s,'Chuva mensal regional em grade de 0,05°',64,491,630,70,26);
 text(s,'NDVI = (B08 − B04) / (B08 + B04)',725,185,490,90,28,true);
 text(s,'NDMI = (B08 − B11) / (B08 + B11)',725,315,490,90,28,true);
 text(s,'≥70% de pixels válidos\nMediana espacial por cena\nMediana das cenas no mês',725,455,490,135,28);
 foot(s,'Escala e offset por produto. Ausências explícitas. Proveniência e hashes por aquisição.');
 note(s,'Fontes: docs/metodologia.md, docs/radiometria.md, docs/recuperacao-2022.md. ANA: https://portal1.snirh.gov.br/server/rest/services/SFI/PIVOS_2022_SNIRH/MapServer/0. Sentinel Earth Search: https://earth-search.aws.element84.com/v1. CHIRPS v3: https://chc.ucsb.edu/data/chirps3. Tucker 1979 DOI10.1016/0034-4257(79)90013-0; Gao1996 DOI10.1016/S0034-4257(96)00067-3 é referência conceitual, originalmente 1.24µm, não o B11 1.61µm. USGS NDMI: https://www.usgs.gov/landsat-missions/normalized-difference-moisture-index.');
}
// 5. Authentic screenshot and immutable counts.
{
 const s=base('Paracatu, MG: estudo concluído');
 await picture(s,'docs/images/webgis-overview.jpg',64,174,735,410);
 text(s,'5 pivôs reais\n256 observações aceitas\n57 cenas Sentinel-2',850,180,365,160,30,true);
 text(s,'141 de 180 espaços\npivô/mês observados\n\n78,3% de cobertura',850,380,365,188,30);
 foot(s,'Histórico 2022–2024. Amostra compacta para desenvolver e verificar o pipeline.');
 note(s,'Captura autêntica existente docs/images/webgis-overview.jpg, sem modificar conteúdo. Números conferidos no manifesto e no pacote público. Caso concluído; amostra deliberada, sem representatividade estatística de todo município. Versão científica2022_2024_recovery_v1; commit1440f3e5b28736d12ded226d6baa6b5ca9005262.');
}
// 6. Editable real numeric table, same validation months.
{
 const s=base('Resultados científicos em meses comuns');
 text(s,'Pivô 16708, sete meses de 2024. Treino em 2022–2023.',64,145,1150,50,28);
 const labels={calendar_month_median:'Mediana sazonal',harmonic_ridge:'Ridge harmônica',previous_year_same_calendar_month:'Mesmo mês de 2023'};
 const metrics=evidence.common_metrics.filter(r=>r.pivot_id==='16708');
 const rows=[['Índice','Método','n','MAE','RMSE']];
 for(const target of ['ndvi_median','ndmi_median'])for(const method of Object.keys(labels)){
  const r=metrics.find(v=>v.target===target&&v.method===method);if(!r)throw new Error('Missing true metrics');
  rows.push([target.startsWith('ndvi')?'NDVI':'NDMI',labels[method],r.n_common_months,Number(r.mae).toFixed(3).replace('.',','),Number(r.rmse).toFixed(3).replace('.',',')]);
 }
 table(s,rows,{left:64,top:224,width:1152,height:316},[135,500,85,210,222],25);
 text(s,'Mediana elegível em 5 pivôs. Ridge elegível em 2.\nOs erros descrevem índices, sem validação de falhas de irrigação.',64,565,1150,74,25);
 note(s,'Fonte: common_month_metrics.csv do pacote público, contraste simultâneo dos3métodos. Meses2024-03,04,05,07,08,09,10. Valores exibidos arredondados3casas, dados completos no relatório. MAE=erro absoluto médio;RMSE=raiz do erro quadrático médio. Ridge menor MAE neste exemplo, mediana menor RMSE NDVI. Mediana5elegíveis; Ridge2, faltando janeiro de treino nos3restantes.2025excluído.');
}
// 7. Region facts and execution state stay explicitly separated.
{
 const s=base('Expansão regional: Guadalupe, PI');
 text(s,`${regional.pivot_count} pivôs, ${regional.accepted_scenes} cenas e ${regional.accepted_observations} observações aceitas de 30 tentativas`,64,143,1152,48,28);
 for(const [index,scene] of comparison.scenes.entries()){
  const relative=`docs/evidencias/guadalupe-pi/comparison/${scene.image}`;
  const bytes=await fs.readFile(path.join(ROOT,relative));
  if(createHash('sha256').update(bytes).digest('hex')!==scene.image_sha256)throw new Error('Comparison image hash mismatch');
  const x=index===0?64:664;
  await picture(s,relative,x,207,552,350,`Imagem real Sentinel-2 em falsa cor de Guadalupe em ${scene.date}, com os contornos ANA dos cinco pivôs`);
  text(s,scene.date.split('-').reverse().join('/'),x,574,552,42,28,true);
 }
 foot(s,'Falsa cor B08/B04/B11, mesma grade de 20 m. Prova exploratória, sem modelo regional validado.');
 note(s,'As duas imagens são derivados reais de Sentinel-2B L2A C1 já publicados. Contains modified Copernicus Sentinel data 2023–2024. Composição R=B08/NIR, G=B04/vermelho, B=B11/SWIR1. Mesma grade EPSG:32723, pixel 20 m, forma 178×217, estiramento fixo de reflectância 0–0,6. Contornos e FIDs ANA 2022 dos cinco pivôs. Todos os cinco pivôs possuem 100% de pixels conjuntos válidos nas duas cenas. As cores não diagnosticam irrigação. Fonte local: docs/evidencias/guadalupe-pi/comparison/provenance.json. '+comparison.scenes.map(scene=>`Data ${scene.date}. Cena ${scene.scene_id}. Fonte ${scene.source}. PB ${scene.processing_baseline}. PNG SHA-256 ${scene.image_sha256}. Manifesto SHA-256 ${scene.manifest_sha256}. Recortes SHA-256 ${JSON.stringify(scene.source_crops_sha256)}.`).join(' ')+' Auditoria territorial 15/11/2026: 14 municípios conferidos, 176 pivôs estaduais MA/PI recuperados. A decisão original comparou dez municípios, com 111 polígonos. Caxias/MA é origem e motivação do pesquisador, sem observações processadas. Guadalupe tem 12 polígonos ANA, dez elegíveis ≥25 ha, com FIDs 5795/5797/5798/5802/5804 na amostra. Distância geodésica de 215,49 km entre o grupo e a sede pública de Caxias. Os 19 meses preliminares STAC não são índices aceitos. Grade contínua: 29/115 espaços observados (25,2%), distinta dos 29/30 alvos (96,7%). '+regional.notes);
}
// 8. Conclusions and demo link.
{
 const s=base('Conclusões e demonstração');
 text(s,'Evidências organizadas para investigação',64,164,1150,70,40,true,C.teal);
 text(s,'Comparação por pivô com duas observações reais.\nFicha de Evidências A4 com seleção e proveniência.\nLinks com observações e hash do pacote publicado.\nDemonstração guiada e visão territorial do Brasil.',64,257,1150,175,29);
 text(s,'Validação de campo e avaliação externa regional continuam\nnecessárias antes de alertas operacionais de irrigação.',64,458,1150,78,26);
 const link=text(s,'altaeir-13.github.io/FTL-Final-Project/',64,540,1150,60,32,true);
 link.text.get('altaeir-13.github.io/FTL-Final-Project/').link={uri:'https://altaeir-13.github.io/FTL-Final-Project/',isExternal:true};
 foot(s,'Funcionalidades tecnológicas derivadas dos resultados científicos. Interpretar mudanças exige contexto.');
 note(s,'Fase 7, referência 16/11/2026. Investigação guiada: território, pivô, duas observações aceitas, deltas assinados B−A de NDVI/NDMI, CHIRPS mensal, qualidade e proveniência. Paracatu usa agregados mensais publicados, Guadalupe usa cenas efetivas. Sem imputação ou diagnóstico causal. Ficha de Evidências: snapshot independente da interface, A4, identificador determinístico SHA-256 sem data de impressão, geração local no navegador. O link preserva região, pivô, observações, índice e hash do pacote. Demonstração manual em cinco passos: problema, Paracatu, investigação, Guadalupe, limites. Escape encerra e restaura estado anterior. Visão territorial distingue Caxias origem, Paracatu estudo concluído e Guadalupe prova exploratória, sem validação nacional. Roteiro detalhado: docs/roteiro-final-ftl.md e docs/investigacao-guiada-ftl.md. URL: https://altaeir-13.github.io/FTL-Final-Project/. As funcionalidades desta revisão dependem de revisão e merge humano para publicação pela main. Não há economia de água, ganho econômico ou falha de irrigação comprovados.');
}

const candidate=path.join(BUILD,'candidate.pptx');
await(await PresentationFile.exportPptx(deck)).save(candidate);
for(let i=0;i<deck.slides.items.length;i++){
 const s=deck.slides.items[i];const png=await deck.export({slide:s,format:'png',scale:1});
 await fs.writeFile(path.join(BUILD,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
 const layout=await s.export({format:'layout'});await fs.writeFile(path.join(BUILD,`slide-${i+1}.layout.json`),await layout.text());
}
const final=path.join(OUT,process.env.AQUACLIMA_DECK_NAME||'aquaclima-ftl-fase7.pptx');
await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath:final,pythonExecutable:PYTHON,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','6'],explicitTotalSlideCount:8,requiredNativeTableOwnerSlides:[6],requiredNativeChartOwnerSlides:[2],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:['Arial']},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,path.basename(final)+'.validation.json')});
console.log(JSON.stringify({pptx:final,slides:deck.slides.items.length,previews:BUILD}));
if(process.env.AQUACLIMA_EXPORT_PDF==='1'){
 // The bundled native PDF exporter lacks a standard-font module on this runtime.
 // A raster backup from the inspected renders preserves the displayed evidence.
 const {spawnSync}=await import('node:child_process');
 const result=spawnSync(PYTHON,[path.join(ROOT,'scripts/export_ftl_pdf.py'),'--output',final.replace(/\.pptx$/i,'.pdf')],{cwd:ROOT,encoding:'utf8'});
 if(result.status!==0)throw new Error(result.stderr||'Raster PDF backup export failed');
 console.log(result.stdout.trim());
}
