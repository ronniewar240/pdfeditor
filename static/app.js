const input=document.getElementById('mainPdf');
const canvas=document.getElementById('pdfCanvas');
const ctx=canvas.getContext('2d');
const editLayer=document.getElementById('editLayer');
const empty=document.getElementById('viewerEmpty');
const fileName=document.getElementById('fileName');
const fileMeta=document.getElementById('fileMeta');
const thumbList=document.getElementById('thumbList');
let pdfDoc=null,currentPage=1,scale=1.25,currentFile=null,mode=null,annotations=[],selected=null;
pdfjsLib.GlobalWorkerOptions.workerSrc='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

function setProxyFiles(){document.querySelectorAll('.pdf-proxy').forEach(el=>{const dt=new DataTransfer();if(currentFile)dt.items.add(currentFile);el.files=dt.files;});}
function ratio(){return scale/1.25;}
function syncLayer(){editLayer.style.width=canvas.width+'px';editLayer.style.height=canvas.height+'px';renderAnnotations();}
async function renderPage(n){
  if(!pdfDoc)return; currentPage=n;
  const page=await pdfDoc.getPage(n); const vp=page.getViewport({scale});
  canvas.width=vp.width; canvas.height=vp.height;
  await page.render({canvasContext:ctx,viewport:vp}).promise;
  empty.style.display='none'; syncLayer();
  document.querySelectorAll('.thumb').forEach((t,i)=>t.classList.toggle('active',i+1===n));
  document.querySelectorAll('input[name="page"]').forEach(i=>i.value=n);
}
async function renderThumbs(){
  thumbList.innerHTML='';
  for(let i=1;i<=pdfDoc.numPages;i++){
    const wrap=document.createElement('div'); wrap.className='thumb'; wrap.innerHTML=`<canvas></canvas><span>Page ${i}</span>`; wrap.onclick=()=>renderPage(i); thumbList.appendChild(wrap);
    const page=await pdfDoc.getPage(i); const c=wrap.querySelector('canvas'),cx=c.getContext('2d'); const vp=page.getViewport({scale:.22}); c.width=vp.width;c.height=vp.height; await page.render({canvasContext:cx,viewport:vp}).promise;
  }
}
input.addEventListener('change',async()=>{
  currentFile=input.files[0]; if(!currentFile)return; annotations=[]; selected=null; setProxyFiles();
  fileName.textContent=currentFile.name; fileMeta.textContent=`${(currentFile.size/1024/1024).toFixed(2)} MB`;
  const url=URL.createObjectURL(currentFile); pdfDoc=await pdfjsLib.getDocument(url).promise;
  fileMeta.textContent+=` • ${pdfDoc.numPages} pages`; await renderThumbs(); await renderPage(1);
});
document.querySelectorAll('.tab').forEach(tab=>tab.onclick=()=>{document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));tab.classList.add('active');document.querySelectorAll('.tool-panel').forEach(p=>p.classList.toggle('active',p.dataset.panel===tab.dataset.tool));mode=null; editLayer.style.cursor='default';});
document.getElementById('zoomIn').onclick=()=>{scale=Math.min(scale+.15,2.5);document.getElementById('zoomText').textContent=Math.round(ratio()*100)+'%';renderPage(currentPage)};
document.getElementById('zoomOut').onclick=()=>{scale=Math.max(scale-.15,.55);document.getElementById('zoomText').textContent=Math.round(ratio()*100)+'%';renderPage(currentPage)};
document.querySelectorAll('form').forEach(form=>form.addEventListener('submit',e=>{if(form.querySelector('.pdf-proxy')&&!currentFile){e.preventDefault();alert('Upload a PDF first.');}}));

function pagePoint(e){const r=editLayer.getBoundingClientRect();return {x:e.clientX-r.left,y:e.clientY-r.top};}
function addAnnotation(a){annotations.push({...a,id:crypto.randomUUID(),page:currentPage}); selected=annotations[annotations.length-1].id; renderAnnotations(); updateSelectedControls();}
function getSelected(){return annotations.find(a=>a.id===selected);}
function clampAnnotation(a){
  const maxW=canvas.width/ratio(), maxH=canvas.height/ratio();
  a.w=Math.max(24,Math.min(a.w,maxW-a.x));
  a.h=Math.max(18,Math.min(a.h,maxH-a.y));
  a.x=Math.max(0,Math.min(a.x,maxW-a.w));
  a.y=Math.max(0,Math.min(a.y,maxH-a.h));
}
function updateSelectedControls(){
  const a=getSelected();
  ['deleteSelected','deleteSelectedSide','deleteSelectedSign'].forEach(id=>{const b=document.getElementById(id); if(b)b.disabled=!a;});
  const info=document.getElementById('selectedInfo');
  if(info) info.textContent=a?`Selected: ${Math.round(a.x)}, ${Math.round(a.y)} • ${Math.round(a.w)}×${Math.round(a.h)}`:'Select an item to move or resize it.';
}
function deleteSelectedItem(){if(!selected)return; annotations=annotations.filter(a=>a.id!==selected); selected=null; renderAnnotations(); updateSelectedControls();}
function applyElementStyle(el,a){const z=ratio(); el.style.left=(a.x*z)+'px'; el.style.top=(a.y*z)+'px'; el.style.width=(a.w*z)+'px'; el.style.height=(a.h*z)+'px'; if(a.type==='text')el.style.fontSize=(a.size*z)+'px';}

function renderAnnotations(){
  editLayer.innerHTML=''; const z=ratio();
  annotations.filter(a=>a.page===currentPage).forEach(a=>{
    const el=document.createElement('div'); el.className=`anno ${a.type==='text'?'text-anno':'sig-anno'} ${selected===a.id?'selected':''}`; el.dataset.id=a.id; applyElementStyle(el,a);
    if(a.type==='text'){
      el.textContent=a.text; el.style.color=a.color;
      el.ondblclick=()=>{const v=prompt('Edit text',a.text); if(v!==null){a.text=v;renderAnnotations();}};
    } else {const img=document.createElement('img'); img.src=a.data; el.appendChild(img);}
    if(selected===a.id){['nw','n','ne','e','se','s','sw','w'].forEach(pos=>{const h=document.createElement('span'); h.className=`handle ${pos}`; h.dataset.handle=pos; el.appendChild(h);});}
    wireTransform(el,a); editLayer.appendChild(el);
  });
  updateSelectedControls();
}
function wireTransform(el,a){
  el.onpointerdown=(e)=>{
    const handle=e.target.dataset.handle;
    selected=a.id; renderAnnotations();
    const fresh=[...editLayer.querySelectorAll('.anno')].find(x=>x.dataset.id===a.id) || el;
    startTransform(e,a,handle||'move',fresh);
    e.stopPropagation();
  };
}
function startTransform(e,a,action,el){
  const z=ratio(), start=pagePoint(e), ox=a.x, oy=a.y, ow=a.w, oh=a.h;
  el.setPointerCapture(e.pointerId);
  el.onpointermove=(ev)=>{
    const p=pagePoint(ev), dx=(p.x-start.x)/z, dy=(p.y-start.y)/z;
    if(action==='move'){a.x=ox+dx; a.y=oy+dy;}
    else{
      if(action.includes('e')) a.w=ow+dx;
      if(action.includes('s')) a.h=oh+dy;
      if(action.includes('w')){a.x=ox+dx; a.w=ow-dx;}
      if(action.includes('n')){a.y=oy+dy; a.h=oh-dy;}
      if(a.type==='text') a.size=Math.max(8,a.h*.65);
    }
    clampAnnotation(a); applyElementStyle(el,a); updateSelectedControls();
  };
  el.onpointerup=()=>{el.onpointermove=null; el.onpointerup=null; renderAnnotations();};
}
editLayer.addEventListener('pointerdown',e=>{if(e.target===editLayer){selected=null;renderAnnotations();updateSelectedControls();}});
editLayer.addEventListener('click',e=>{
  if(!pdfDoc){alert('Upload a PDF first.');return;} if(e.target!==editLayer)return;
  const p=pagePoint(e), z=ratio();
  if(mode==='text'){
    const text=document.getElementById('textValue').value.trim(); if(!text){alert('Type text first.');return;}
    const size=parseInt(document.getElementById('textSize').value||'18'); addAnnotation({type:'text',text,color:document.getElementById('textColor').value,size,x:p.x/z,y:p.y/z,w:220,h:size*1.7}); mode=null; editLayer.style.cursor='default';
  } else if(mode==='signature'){
    const data=sigCanvas.toDataURL('image/png'); addAnnotation({type:'signature',data,x:p.x/z,y:p.y/z,w:220,h:84}); mode=null; editLayer.style.cursor='default';
  }
});
document.getElementById('placeText').onclick=()=>{mode='text'; editLayer.style.cursor='crosshair';};
document.getElementById('placeSignature').onclick=()=>{mode='signature'; editLayer.style.cursor='crosshair';};
document.getElementById('clearEdits').onclick=()=>{annotations=[];selected=null;renderAnnotations();updateSelectedControls();};
document.getElementById('deleteSelected').onclick=deleteSelectedItem;
document.getElementById('deleteSelectedSide').onclick=deleteSelectedItem;
document.getElementById('deleteSelectedSign').onclick=deleteSelectedItem;
document.addEventListener('keydown',e=>{if((e.key==='Delete'||e.key==='Backspace')&&selected){deleteSelectedItem();}});

document.getElementById('saveEdits').onclick=async()=>{
  if(!currentFile){alert('Upload a PDF first.');return;} if(!annotations.length){alert('No edits to save.');return;}
  const fd=new FormData(); fd.append('pdf',currentFile); fd.append('annotations',JSON.stringify(annotations));
  const res=await fetch('/api/apply-edits',{method:'POST',body:fd}); if(!res.ok){alert((await res.json()).error||'Save failed');return;}
  const blob=await res.blob(); const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download='edited_dynamic.pdf'; a.click(); URL.revokeObjectURL(url);
};

const sigCanvas=document.getElementById('signatureCanvas'); const sigCtx=sigCanvas.getContext('2d'); let drawing=false;
function resetSigCanvas(){sigCtx.clearRect(0,0,sigCanvas.width,sigCanvas.height);sigCtx.fillStyle='white';sigCtx.fillRect(0,0,sigCanvas.width,sigCanvas.height);sigCtx.lineWidth=3;sigCtx.lineCap='round';sigCtx.strokeStyle='black';}
function pointerPos(e){const r=sigCanvas.getBoundingClientRect();const t=e.touches?e.touches[0]:e;return {x:(t.clientX-r.left)*(sigCanvas.width/r.width),y:(t.clientY-r.top)*(sigCanvas.height/r.height)};}
function startDraw(e){drawing=true;const p=pointerPos(e);sigCtx.beginPath();sigCtx.moveTo(p.x,p.y);e.preventDefault();}
function draw(e){if(!drawing)return;const p=pointerPos(e);sigCtx.lineTo(p.x,p.y);sigCtx.stroke();e.preventDefault();}
function stopDraw(){drawing=false;}
['mousedown','touchstart'].forEach(ev=>sigCanvas.addEventListener(ev,startDraw,{passive:false}));
['mousemove','touchmove'].forEach(ev=>sigCanvas.addEventListener(ev,draw,{passive:false}));
['mouseup','mouseleave','touchend'].forEach(ev=>sigCanvas.addEventListener(ev,stopDraw));
document.getElementById('clearSignature').onclick=resetSigCanvas;
document.getElementById('useTypedSignature').onclick=()=>{const name=document.getElementById('typedSignature').value.trim(); if(!name){alert('Type your name first.');return;} resetSigCanvas(); sigCtx.fillStyle='black'; sigCtx.font='52px cursive'; sigCtx.fillText(name,32,96);};
resetSigCanvas();
