
// эндпоинты
const { snapshot, setMasks, setParams, togglePause, saveVideo } = window.APP_ENDPOINTS;

// элементы
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const blurSlider   = document.getElementById('blurStrength');
const blurVal      = document.getElementById('blurStrengthVal');
const autoFaceCb   = document.getElementById('autoFace');
const btnPause     = document.getElementById('btnPause');
const btnResume    = document.getElementById('btnResume');
const btnClear     = document.getElementById('btnClear');
const btnSave      = document.getElementById('btnSave');
const saveStatus   = document.getElementById('saveStatus');
const downloadLink = document.getElementById('downloadLink');

// состояние
let masks = []; 
let drawing = false;  
let dragging = -1; 
let startX = 0, startY = 0; 
let tempRect = null;  
let frameImg = null;  
let fps = 10; 
let timer = null;   
let sendMasksTimer = null; 

// утилиты 
const clamp = (v,a,b)=>Math.max(a,Math.min(b,v));

function pxToNorm(x,y,w,h){
  const W = canvas.width || 1, H = canvas.height || 1;
  return {
    x: clamp(x/W, 0, 1),
    y: clamp(y/H, 0, 1),
    w: clamp(w/W, 0.001, 1),
    h: clamp(h/H, 0.001, 1),
  };
}
function normToPx(r){
  return {
    x: r.x * canvas.width,
    y: r.y * canvas.height,
    w: r.w * canvas.width,
    h: r.h * canvas.height,
  };
}
function clientToPx(e){
  const p = e.touches ? e.touches[0] : e;
  const r = canvas.getBoundingClientRect();
  return {
    x: clamp((p.clientX - r.left) * (canvas.width  / r.width),  0, canvas.width),
    y: clamp((p.clientY - r.top)  * (canvas.height / r.height), 0, canvas.height)
  };
}
function post(url, body){
  return fetch(url, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(body || {})
  });
}

// предпросмотр
function fetchFrame(){
  const img = new Image();
  img.onload = ()=>{
    frameImg = img;
    if (!canvas.width) {
      canvas.width  = img.naturalWidth  || 640;
      canvas.height = img.naturalHeight || 360;
    }
  };
  img.src = `${snapshot}?_=${Date.now()}`;
}
function startPreview(){
  if (timer) return;
  fetchFrame();
  timer = setInterval(fetchFrame, Math.max(60, Math.floor(1000 / fps)));
}
function stopPreview(){
  clearInterval(timer);
  timer = null;
}

// отрисовка
function render(){
  // фон-кадр
  if (frameImg) ctx.drawImage(frameImg, 0, 0, canvas.width, canvas.height);

  // маски
  ctx.lineWidth = 2;
  ctx.strokeStyle = 'lime';
  ctx.setLineDash([]);
  masks.forEach(m=>{
    const {x,y,w,h} = normToPx(m);
    ctx.strokeRect(x,y,w,h);
  });

  // временная рамка при рисовании
  if (tempRect){
    ctx.setLineDash([6,4]);
    ctx.strokeStyle = 'yellow';
    ctx.strokeRect(tempRect.x, tempRect.y, tempRect.w, tempRect.h);
    ctx.setLineDash([]);
  }

  requestAnimationFrame(render);
}

// отправка масок 
function sendMasks(){
  clearTimeout(sendMasksTimer);
  sendMasksTimer = setTimeout(()=>post(setMasks, { masks }), 120);
}

// события мыши
canvas.addEventListener('pointerdown', e=>{
  canvas.setPointerCapture(e.pointerId);
  const {x,y} = clientToPx(e);

  // пытаемся схватить существующую маску для перетаскивания
  dragging = masks.findIndex(r=>{
    const p = normToPx(r);
    return x >= p.x && x <= p.x+p.w && y >= p.y && y <= p.y+p.h;
  });
  if (dragging >= 0){
    drawing = false;
    tempRect = { dx: x - normToPx(masks[dragging]).x, dy: y - normToPx(masks[dragging]).y }; // смещение для плавного перетаскивания
    return;
  }

  // иначе начинаем рисовать новую
  drawing = true;
  startX = x; startY = y;
  tempRect = { x, y, w:0, h:0 };
});

canvas.addEventListener('pointermove', e=>{
  const {x,y} = clientToPx(e);

  // рисуем новую маску
  if (drawing && tempRect){
    const x0 = Math.min(startX, x);
    const y0 = Math.min(startY, y);
    tempRect.x = x0;
    tempRect.y = y0;
    tempRect.w = Math.max(2, Math.abs(x - startX));
    tempRect.h = Math.max(2, Math.abs(y - startY));
    return;
  }

  // двигаем существующую маску
  if (dragging >= 0){
    const r = masks[dragging];
    const px = normToPx(r);
    const newX = clamp(x - (tempRect.dx || 0), 0, canvas.width  - px.w);
    const newY = clamp(y - (tempRect.dy || 0), 0, canvas.height - px.h);
    const moved = pxToNorm(newX, newY, px.w, px.h);
    masks[dragging] = moved;
    sendMasks();
  }
});

canvas.addEventListener('pointerup', ()=>{
  // завершаем рисование
  if (drawing && tempRect){
    const {x,y,w,h} = tempRect;
    if (w >= 2 && h >= 2){
      masks.push(pxToNorm(x,y,w,h));
      sendMasks();
    }
  }
  drawing = false;
  dragging = -1;
  tempRect = null;
});

// управление
blurSlider.addEventListener('input', ()=>{
  blurVal.textContent = blurSlider.value;
  post(setParams, { blurStrength: parseFloat(blurSlider.value), autoFace: autoFaceCb.checked });
});
autoFaceCb.addEventListener('change', ()=>{
  post(setParams, { blurStrength: parseFloat(blurSlider.value), autoFace: autoFaceCb.checked });
});

btnPause .addEventListener('click', ()=>post(togglePause, { paused:true  }));
btnResume.addEventListener('click', ()=>post(togglePause, { paused:false }));
btnClear .addEventListener('click', ()=>{ masks = []; sendMasks(); });

btnSave.addEventListener('click', async ()=>{
  saveStatus.textContent = 'Идёт обработка...';
  downloadLink.innerHTML = '';
  try{
    const r = await fetch(saveVideo, { method:'POST' });
    const d = await r.json();
    if (d.ok && d.downloadUrl){
      saveStatus.textContent = 'Готово.';
      downloadLink.innerHTML = `<a class="btn" href="${d.downloadUrl}">Скачать результат</a>`;
    } else {
      saveStatus.textContent = 'Не удалось сохранить.';
    }
  } catch {
    saveStatus.textContent = 'Ошибка сети.';
  }
});

window.addEventListener('load', ()=>{
  blurVal.textContent = blurSlider.value;
  post(setParams, { blurStrength: parseFloat(blurSlider.value), autoFace: autoFaceCb.checked });
  startPreview();
  requestAnimationFrame(render);
  window.preview = {
    start: startPreview,
    stop:  ()=>stopPreview(),
    setFps: (v)=>{ fps = clamp(v|0, 1, 30); if (timer){ stopPreview(); startPreview(); } }
  };
});



