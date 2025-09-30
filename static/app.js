const { video_feed, set_masks, set_params, save_video } = window.APP_ENDPOINTS;

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const blurSlider = document.getElementById('blur');
const blurVal = document.getElementById('blurVal');
const btnSave = document.getElementById('btnSave');
const saveStatus = document.getElementById('saveStatus');
const downloadLink = document.getElementById('downloadLink');

const img = new Image();
img.src = `${video_feed}?_=${Date.now()}`;

let masks = [];         
let isDrawing = false;
let startX=0, startY=0;
let dragIndex = -1;
let dragOffset = {x:0,y:0};

function fitCanvas(){
  canvas.width = img.naturalWidth || 640;
  canvas.height = img.naturalHeight || 360;
}
function draw(){
  try{
    if (img.complete && img.naturalWidth){
      if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) fitCanvas();
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      ctx.lineWidth = 2; ctx.strokeStyle = 'lime';
      masks.forEach(r => ctx.strokeRect(r.x*canvas.width, r.y*canvas.height, r.w*canvas.width, r.h*canvas.height));
    }
  }catch(e){}
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);

function toNorm(clientX, clientY){
  const r = canvas.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(1, (clientX - r.left) / r.width)),
    y: Math.max(0, Math.min(1, (clientY - r.top) / r.height))
  };
}
function normFromEvent(e){
  if (e.touches && e.touches[0]) return toNorm(e.touches[0].clientX, e.touches[0].clientY);
  return toNorm(e.clientX, e.clientY);
}

// рисование/перетаскивание
canvas.addEventListener('mousedown', (e)=>{
  const p = normFromEvent(e);
  dragIndex = masks.findIndex(r => p.x>=r.x && p.x<=r.x+r.w && p.y>=r.y && p.y<=r.y+r.h);
  if (dragIndex>=0){ dragOffset.x=p.x-masks[dragIndex].x; dragOffset.y=p.y-masks[dragIndex].y; isDrawing=false; return; }
  isDrawing=true; startX=p.x; startY=p.y; masks.push({x:p.x,y:p.y,w:0,h:0});
});
canvas.addEventListener('mousemove', (e)=>{
  if (!isDrawing && dragIndex<0) return;
  const p = normFromEvent(e);
  if (isDrawing){
    const r = masks[masks.length-1];
    r.w = Math.max(0.001, Math.min(1 - r.x, p.x - startX));
    r.h = Math.max(0.001, Math.min(1 - r.y, p.y - startY));
    sendMasks();
  } else {
    let nx = p.x - dragOffset.x, ny = p.y - dragOffset.y;
    nx = Math.max(0, Math.min(1 - masks[dragIndex].w, nx));
    ny = Math.max(0, Math.min(1 - masks[dragIndex].h, ny));
    masks[dragIndex].x = nx; masks[dragIndex].y = ny;
    sendMasks();
  }
});
window.addEventListener('mouseup', ()=>{ isDrawing=false; dragIndex=-1; });

canvas.addEventListener('touchstart', (e)=>{
  const p = normFromEvent(e);
  dragIndex = masks.findIndex(r => p.x>=r.x && p.x<=r.x+r.w && p.y>=r.y && p.y<=r.y+r.h);
  if (dragIndex>=0){ dragOffset.x=p.x-masks[dragIndex].x; dragOffset.y=p.y-masks[dragIndex].y; isDrawing=false; }
  else { isDrawing=true; startX=p.x; startY=p.y; masks.push({x:p.x,y:p.y,w:0,h:0}); }
  e.preventDefault();
},{passive:false});
canvas.addEventListener('touchmove', (e)=>{
  if (!isDrawing && dragIndex<0) return;
  const p = normFromEvent(e);
  if (isDrawing){
    const r = masks[masks.length-1];
    r.w = Math.max(0.001, Math.min(1 - r.x, p.x - startX));
    r.h = Math.max(0.001, Math.min(1 - r.y, p.y - startY));
    sendMasks();
  } else {
    let nx = p.x - dragOffset.x, ny = p.y - dragOffset.y;
    nx = Math.max(0, Math.min(1 - masks[dragIndex].w, nx));
    ny = Math.max(0, Math.min(1 - masks[dragIndex].h, ny));
    masks[dragIndex].x = nx; masks[dragIndex].y = ny;
    sendMasks();
  }
  e.preventDefault();
},{passive:false});
window.addEventListener('touchend', ()=>{ isDrawing=false; dragIndex=-1; });

// отправка на бэкенд
function sendMasks(){
  fetch(set_masks, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({masks}) }).catch(()=>{});
}
function sendParams(){
  fetch(set_params, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ blur_strength: parseFloat(blurSlider.value) }) }).catch(()=>{});
}

// слайдер блюра
blurSlider.addEventListener('input', ()=>{
  blurVal.textContent = blurSlider.value;
  sendParams();
});

// начальная синхронизация
window.addEventListener('load', ()=>{
  blurVal.textContent = blurSlider.value;
  sendParams();
});

// сохранить
btnSave.addEventListener('click', async ()=>{
  saveStatus.textContent = 'Загрузка...';
  downloadLink.innerHTML = '';
  try {
    const res = await fetch(save_video, { method:'POST' });
    const data = await res.json();
    if (data.ok){
      saveStatus.textContent = 'Done.';
      downloadLink.innerHTML = `<a href="${data.download_url}">Скачать готовое видео</a>`;
    } else {
      saveStatus.textContent = 'Failed.';
    }
  } catch { saveStatus.textContent = 'Error.'; }
});
