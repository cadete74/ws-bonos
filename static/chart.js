<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="Permissions-Policy" content="interest-cohort=()">
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Bonos AR - AL30 / GD30 / Ratio</title>

  <!-- Chart.js v4 + adapter fechas + zoom -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.umd.min.js"></script>

  <style>
    :root{
      --bg:#0e1116; --panel:#141a25; --muted:#9aa4b2; --text:#e6edf3; --border:#202636;
      --chip:#0b0f18; --chip-bd:#273043; --grid:#1b2232; --grid-strong:#24314a;
      --al30:#4aa3ff; --gd30:#ffd166; --ratio:#58d68d; --violet:#b184e6;
      --good:#2ecc71; --bad:#e74c3c;
    }
    *{box-sizing:border-box}
    html,body{height:100%}
    body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,"Helvetica Neue",Arial,"Noto Sans";}
    header{display:flex;align-items:center;gap:.75rem;padding:.75rem 1rem;border-bottom:1px solid var(--border);
      background:linear-gradient(180deg,#0f141f,#0c1018);position:sticky;top:0;z-index:5}
    header h1{font-size:16px;margin:0 .5rem 0 0;letter-spacing:.3px;color:#c5cfde;font-weight:600}
    .toolbar{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center}
    .btn{border:1px solid var(--chip-bd);background:var(--chip);color:var(--text);padding:.35rem .6rem;border-radius:.5rem;cursor:pointer;
      user-select:none;transition:transform .02s ease,background .15s ease,border .15s ease;font-weight:600;font-size:12px}
    .btn:hover{border-color:#3a4661}.btn:active{transform:scale(.98)}.btn.active{background:#1d2435;border-color:#4a5c86}
    .status{margin-left:auto;display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;color:var(--muted);font-size:12px}
    .pill{padding:.2rem .5rem;border:1px solid var(--chip-bd);border-radius:999px;background:var(--chip);color:#cbd5e1}
    .ws-ok{color:var(--good);border-color:rgba(46,204,113,.4)} .ws-bad{color:var(--bad);border-color:rgba(231,76,60,.4)}
    main{display:grid;grid-template-columns:minmax(0,1fr) 520px;gap:10px;padding:10px;height:calc(100% - 58px)}
    #chartWrap{background:var(--panel);border:1px solid var(--border);border-radius:10px;display:flex;flex-direction:column;min-height:0;position:relative}
    #chart{width:100%;height:100%;min-height:480px}
    aside{display:flex;flex-direction:column;gap:10px;min-height:0}
    .card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:.75rem}
    .h3,.card h3{margin:.25rem 0 .5rem;font-size:13px;color:#c9d3e7;letter-spacing:.2px}
    .row{display:flex;justify-content:space-between;gap:.5rem;margin:.25rem 0}
    .lbl{color:#9fb0cc}.val{color:#e8eef9;font-weight:700}.sep{height:1px;background:#243048;margin:.5rem 0}
    .tiny{font-size:11px;color:#9aa6bd}.foot{margin-top:auto;font-size:11px;color:#8b97ab;display:flex;justify-content:space-between;gap:.5rem;align-items:center}
    .kbd{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#0a0f18;border:1px solid #222b3f;border-radius:6px;padding:.15rem .35rem;color:#d1dcf4}
    .books-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    .order-box{background:#101625;border:1px solid var(--border);border-radius:10px;padding:.6rem}
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:.5rem}
    table.order{width:100%;border-collapse:collapse;font-size:12px}
    table.order th, table.order td{padding:.2rem .25rem;border-bottom:1px dashed #243048;text-align:right}
    table.order th{color:#9fb0cc;font-weight:600} table.order td.qty{color:#c2cad8}
    #overlay{position:absolute;inset:0;background:rgba(14,17,22,.88);display:none;align-items:center;justify-content:center;text-align:center;padding:20px;border-radius:10px}
    #overlay .box{max-width:720px;color:#cbd5e1}
    #overlay .box h3{margin:0 0 .5rem 0}
    @media (max-width:1200px){main{grid-template-columns:1fr}.books-grid{grid-template-columns:1fr}}
  </style>
</head>
<body>
  <header>
    <h1>AL30 • GD30 • Ratio</h1>
    <div class="toolbar" id="resButtons">
      <button class="btn" data-res="1m">1m</button>
      <button class="btn" data-res="5m">5m</button>
      <button class="btn" data-res="15m">15m</button>
      <button class="btn" data-res="30m">30m</button>
      <button class="btn" data-res="1h">1h</button>
      <button class="btn" data-res="2h">2h</button>
      <button class="btn" data-res="1d">1d</button>
      <button class="btn" data-res="1M">1M</button>
      <button class="btn" id="resetZoom">Reset zoom</button>
      <button class="btn" id="btnAnchorLeft" title="Ver desde el inicio">⟵ Inicio</button>
      <button class="btn" id="btnFollow">Seguir en vivo: OFF</button>
      <button class="btn" id="btnSession">Filtro sesión: ON</button>
    </div>
    <div class="status">
      <span class="pill" id="wsState">WS: —</span>
      <span class="pill" id="ptsState">Puntos: —</span>
      <span class="pill" id="lastTs">Último: —</span>
    </div>
  </header>

  <main>
    <section id="chartWrap">
      <canvas id="chart"></canvas>
      <div id="overlay"><div class="box">
        <h3>Sin datos visibles</h3>
        <div id="overlayMsg" class="tiny">Verificando conexión…</div>
      </div></div>
      <div class="foot tiny">
        <div>
          Zoom: rueda + <span class="kbd">Ctrl</span> • Arrastre: <span class="kbd">Shift</span> • Pan: <span class="kbd">Alt</span> • Doble clic: Reset
        </div>
        <div id="footInfo"></div>
      </div>
    </section>

    <aside>
      <div class="card">
        <h3>Resumen <span class="tiny source" id="lastSource">—</span></h3>
        <div class="row"><span class="lbl">AL30 Último</span><span class="val" id="lastAL30">—</span></div>
        <div class="row"><span class="lbl">GD30 Último</span><span class="val" id="lastGD30">—</span></div>
        <div class="row"><span class="lbl">Ratio Último</span><span class="val" id="lastRatio">—</span></div>
        <div class="sep"></div>
        <div class="row"><span class="lbl">Promedio Ratio</span><span class="val" id="avgRatio">—</span></div>
      </div>

      <div class="books-grid">
        <div class="order-box">
          <div class="order-title"><h3 class="h3">Libro AL30</h3></div>
          <div class="grid2">
            <div>
              <div class="tiny">Bids (Top-5)</div>
              <table class="order" id="bookAL30Bids"><thead><tr><th>Precio</th><th class="qty">Cant.</th></tr></thead><tbody></tbody></table>
            </div>
            <div>
              <div class="tiny">Asks (Top-5)</div>
              <table class="order" id="bookAL30Asks"><thead><tr><th>Precio</th><th class="qty">Cant.</th></tr></thead><tbody></tbody></table>
            </div>
          </div>
          <div class="sep"></div>
          <div class="row"><span class="lbl">Mejor Bid/Ask</span><span class="val" id="bestAL30">—</span></div>
          <div class="row"><span class="lbl">Spread</span><span class="val" id="spreadAL30">—</span></div>
        </div>

        <div class="order-box">
          <div class="order-title"><h3 class="h3">Libro GD30</h3></div>
          <div class="grid2">
            <div>
              <div class="tiny">Bids (Top-5)</div>
              <table class="order" id="bookGD30Bids"><thead><tr><th>Precio</th><th class="qty">Cant.</th></tr></thead><tbody></tbody></table>
            </div>
            <div>
              <div class="tiny">Asks (Top-5)</div>
              <table class="order" id="bookGD30Asks"><thead><tr><th>Precio</th><th class="qty">Cant.</th></tr></thead><tbody></tbody></table>
            </div>
          </div>
          <div class="sep"></div>
          <div class="row"><span class="lbl">Mejor Bid/Ask</span><span class="val" id="bestGD30">—</span></div>
          <div class="row"><span class="lbl">Spread</span><span class="val" id="spreadGD30">—</span></div>
        </div>
      </div>
    </aside>
  </main>

  <script>
  // ===== Configuración de mercado (ART) =====
  const MARKET_TZ = 'America/Argentina/Buenos_Aires';
  const SESSION_OPEN_H = 11;
  const SESSION_CLOSE_H = 17;
  const SESSION_DAYS = new Set([1,2,3,4,5]); // lun..vie
  let sessionFilter = true; // toggle ON/OFF

  // ===== Helpers =====
  const $ = s => document.querySelector(s);
  const pad = n => String(n).padStart(2,'0');
  const fmtN = (v,d=2)=> Number.isFinite(v) ? v.toLocaleString('es-AR',{minimumFractionDigits:d,maximumFractionDigits:d}) : '—';
  const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const COLORS = { al30:cssVar('--al30')||'#4aa3ff', gd30:cssVar('--gd30')||'#ffd166', ratio:cssVar('--ratio')||'#58d68d',
                   violet:cssVar('--violet')||'#b184e6', grid:cssVar('--grid')||'#1b2232', gridStrong:cssVar('--grid-strong')||'#24314a' };
  const dtfTime = new Intl.DateTimeFormat('es-AR',{ timeZone:MARKET_TZ, hour:'2-digit', minute:'2-digit', hour12:false });
  const dtfDate = new Intl.DateTimeFormat('es-AR',{ timeZone:MARKET_TZ, day:'2-digit', month:'2-digit' });
  const dtfFull = new Intl.DateTimeFormat('es-AR',{ timeZone:MARKET_TZ, day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false });
  const fmtTimeART = ms => dtfTime.format(ms);
  const fmtDateART = ms => dtfDate.format(ms);
  const fmtFullART = ms => dtfFull.format(ms);
  function setFooter(msg){ const el=$('#footInfo'); if(el) el.textContent=msg; }
  function showOverlay(msg){ const o=$('#overlay'); $('#overlayMsg').textContent=msg; o.style.display='flex'; }
  function hideOverlay(){ $('#overlay').style.display='none'; }

  // Partes ART
  function partsART(date=new Date()){
    const p = new Intl.DateTimeFormat('es-AR',{timeZone:MARKET_TZ,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',weekday:'short',hour12:false})
      .formatToParts(date).reduce((a,x)=>{a[x.type]=x.value;return a;}, {});
    const w={lun:1,mar:2,mié:3,jue:4,vie:5,sáb:6,dom:0};
    return {year:+p.year,month:+p.month,day:+p.day,hour:+p.hour,minute:+p.minute,weekday:w[p.weekday]??0};
  }
  function isoART(y,m,d,hh=0,mm=0,ss=0){ return `${y}-${pad(m)}-${pad(d)}T${pad(hh)}:${pad(mm)}:${pad(ss)}-03:00`; }
  function msAtART(y,m,d,hh=0,mm=0,ss=0){ return Date.parse(isoART(y,m,d,hh,mm,ss)); }
  function sessionStartMsFor(tsms){ const {year,month,day}=partsART(new Date(tsms)); return msAtART(year,month,day,SESSION_OPEN_H,0,0); }
  function isMarketDayART(tsms){ const {weekday}=partsART(new Date(tsms)); return SESSION_DAYS.has(weekday); }
  function isInsideSessionART(tsms){
    if(!isMarketDayART(tsms)) return false;
    const {hour,minute}=partsART(new Date(tsms));
    const m=hour*60+minute; return m>=SESSION_OPEN_H*60 && m<SESSION_CLOSE_H*60;
  }

  // Parseo robusto de ts (epoch, ISO con/sin zona, "YYYY-MM-DD HH:mm[:ss]")
  function parseTs(ts){
    if(ts==null) return NaN;
    if(typeof ts==='number') return ts<1e12 ? Math.round(ts*1000) : Math.round(ts);
    if(typeof ts==='string'){
      let s=ts.trim();
      // números
      if(/^\d{13}$/.test(s)) return +s;
      if(/^\d{10}$/.test(s)) return +s*1000;
      if(/^\d+(\.\d+)?$/.test(s)){ const n=Number(s); return n<1e12 ? Math.round(n*1000) : Math.round(n); }
      // normalizar "YYYY-MM-DD HH:mm(:ss)?" -> "T"
      if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$/.test(s)) s = s.replace(' ','T');
      // si no trae zona, asumir ART
      const hasTZ = /[zZ]|[+\-]\d\d:\d\d$/.test(s);
      if(!hasTZ){
        if(!s.includes('T')) s += 'T00:00:00';
        s += '-03:00';
      }
      const t=Date.parse(s);
      return Number.isFinite(t) ? t : NaN;
    }
    return NaN;
  }

  // ===== Datos y estado =====
  const dataAL30=[], dataGD30=[], dataRatio=[];
  let ratioSum=0, lastTsMs=0, firstTsMs=0;
  let ws=null;

  const RES = {
    '1m':{unit:'minute',windowDays:1,tickLimit:18,height:440},
    '5m':{unit:'minute',windowDays:5,tickLimit:18,height:470},
    '15m':{unit:'minute',windowDays:15,tickLimit:16,height:490},
    '30m':{unit:'minute',windowDays:30,tickLimit:16,height:510},
    '1h':{unit:'hour',windowDays:60,tickLimit:14,height:540},
    '2h':{unit:'hour',windowDays:120,tickLimit:12,height:560},
    '1d':{unit:'day',windowDays:180,tickLimit:10,height:580},
    '1M':{unit:'month',windowDays:365,tickLimit:10,height:600},
  };
  let currentRes='5m', anchor='left', followLive=false;

  // ===== Chart plugins =====
  const crosshairPlugin={ id:'crosshair', afterDatasetsDraw(c){ const {ctx,tooltip,chartArea:{top,bottom}}=c; if(!tooltip||!tooltip.getActiveElements().length) return;
      const x=tooltip.caretX; ctx.save(); ctx.strokeStyle='#2b3a55'; ctx.lineWidth=1; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(x,top); ctx.lineTo(x,bottom); ctx.stroke(); ctx.restore(); } };
  const lastPriceLines={ id:'lastPriceLines', afterDatasetsDraw(c){ const {ctx,scales:{yPrice,yRatio},chartArea:{left,right}}=c; ctx.save();
      const draw=(yVal,color,label,axis='price')=>{ if(!Number.isFinite(yVal)) return; const y=(axis==='price'?yPrice:yRatio).getPixelForValue(yVal);
        ctx.strokeStyle=color; ctx.lineWidth=1; ctx.setLineDash([6,4]); ctx.beginPath(); ctx.moveTo(left,y); ctx.lineTo(right,y); ctx.stroke();
        const text=label; ctx.setLineDash([]); ctx.font='12px ui-monospace, monospace'; const padX=6,h=18,w=ctx.measureText(text).width+padX*2; const x=right-w-4; const yTop=y-h/2;
        ctx.fillStyle='#0a0f18'; ctx.strokeStyle='#2d3a55'; if(ctx.roundRect){ ctx.beginPath(); ctx.roundRect(x,yTop,w,h,6); ctx.fill(); ctx.stroke(); } else { ctx.fillRect(x,yTop,w,h); ctx.strokeRect(x,yTop,w,h); }
        ctx.fillStyle=color; ctx.fillText(text,x+padX,yTop+h-6); };
      const lp=dataAL30.at(-1)?.y, lg=dataGD30.at(-1)?.y, lr=dataRatio.at(-1)?.y;
      draw(lp,COLORS.al30,`AL30 ${fmtN(lp,2)}`,'price'); draw(lg,COLORS.gd30,`GD30 ${fmtN(lg,2)}`,'price'); draw(lr,COLORS.violet,`R ${fmtN(lr,6)}`,'ratio'); ctx.restore(); } };

  // ===== Chart =====
  const ratioAvgDataset={label:'Ratio Avg',data:[],yAxisID:'yRatio',parsing:false,borderColor:COLORS.violet,borderDash:[6,6],borderWidth:1.4,pointRadius:0,tension:0};
  const chart = new Chart(document.getElementById('chart').getContext('2d'),{
    type:'line',
    data:{datasets:[
      {label:'AL30',data:dataAL30,parsing:false,yAxisID:'yPrice',borderColor:COLORS.al30,borderWidth:1.8,pointRadius:0,tension:0,spanGaps:false},
      {label:'GD30',data:dataGD30,parsing:false,yAxisID:'yPrice',borderColor:COLORS.gd30,borderWidth:1.8,pointRadius:0,tension:0,spanGaps:false},
      {label:'Ratio',data:dataRatio,parsing:false,yAxisID:'yRatio',borderColor:COLORS.ratio,borderWidth:1.6,pointRadius:0,tension:0,spanGaps:false},
      ratioAvgDataset
    ]},
    options:{
      responsive:true, maintainAspectRatio:false, normalized:true, animation:false,
      interaction:{intersect:false,mode:'index'},
      plugins:{
        legend:{labels:{color:'#b7c1d1'}},
        tooltip:{enabled:true,backgroundColor:'#0b0f18',borderColor:'#273043',borderWidth:1,titleColor:'#cdd6e6',bodyColor:'#dfe7f6',
          callbacks:{ title(items){return items.length? fmtFullART(items[0].parsed.x):'';}, label(ctx){const d=ctx.dataset.label,v=ctx.parsed.y,dec=(d==='Ratio'||d==='Ratio Avg')?6:2; return `${d}: ${fmtN(v,dec)}`;} } },
        decimation:{enabled:true,algorithm:'min-max'},
        zoom:{ pan:{enabled:true,mode:'x',modifierKey:'alt'},
               zoom:{wheel:{enabled:true,modifierKey:'ctrl'},drag:{enabled:true,modifierKey:'shift',backgroundColor:'rgba(110,168,254,.08)'},mode:'x'},
               limits:{x:{min:'original',max:'original'}} }
      },
      scales:{
        x:{ type:'time', time:{tooltipFormat:'dd/MM HH:mm'}, ticks:{maxRotation:0,autoSkip:true, callback:(val,idx,ticks)=>{
              // Formato de labels: en minutos → HH:mm, en mayores → mayor: dd/MM, minor: HH:mm
              const unit = RES[currentRes].unit;
              if(unit==='minute') return fmtTimeART(val);
              const t=ticks[idx]; return t&&t.major ? fmtDateART(val) : fmtTimeART(val);
            }}, grid:{color:COLORS.grid}},
        yPrice:{position:'left',ticks:{color:'#a9bad8',callback:v=>fmtN(v,2)},grid:{color:COLORS.grid}},
        yRatio:{position:'right',ticks:{color:'#bfa9db',callback:v=>fmtN(v,6)},grid:{display:false}}
      }
    },
    plugins:[crosshairPlugin,lastPriceLines]
  });
  chart.canvas.addEventListener('dblclick',()=>{ chart.resetZoom(); applyWindow(); });

  // ===== UI controls =====
  function setActiveResButton(key){ document.querySelectorAll('#resButtons .btn[data-res]').forEach(b=>b.classList.toggle('active', b.dataset.res===key)); }
  function adjustChartHeight(){ const h=RES[currentRes].height||480; document.getElementById('chart').style.minHeight=`${h}px`; }
  function applyWindow(){
    if(!firstTsMs){ chart.update('none'); return; }
    const {windowDays,unit,tickLimit}=RES[currentRes];
    const ms=windowDays*86400000;
    const base=lastTsMs||firstTsMs;
    const startSession = sessionStartMsFor(firstTsMs);
    if(anchor==='left'){ chart.options.scales.x.min = startSession; chart.options.scales.x.max = Math.min(startSession+ms, base); }
    else { chart.options.scales.x.max=base; chart.options.scales.x.min=Math.max(base-ms, sessionStartMsFor(base)); }
    chart.options.scales.x.time.unit=unit; chart.options.scales.x.ticks.maxTicksLimit=tickLimit;
    chart.update('none');
    setFooter(`Ventana ${currentRes} • ${fmtFullART(chart.options.scales.x.min)} → ${fmtFullART(chart.options.scales.x.max)} • Filtro sesión: ${sessionFilter?'ON':'OFF'}`);
  }
  $('#resButtons').addEventListener('click',(e)=>{
    const btn=e.target.closest('button'); if(!btn) return;
    const res=btn.getAttribute('data-res'); if(!res) return;
    currentRes=res; setActiveResButton(currentRes); adjustChartHeight(); chart.resetZoom(); anchor=followLive?'right':'left'; applyWindow();
  },true);
  $('#resetZoom').addEventListener('click',()=>{ chart.resetZoom(); applyWindow(); });
  $('#btnAnchorLeft').addEventListener('click',()=>{ followLive=false; anchor='left'; $('#btnFollow').textContent='Seguir en vivo: OFF'; applyWindow(); });
  $('#btnFollow').addEventListener('click',()=>{ followLive=!followLive; anchor=followLive?'right':'left'; $('#btnFollow').textContent=`Seguir en vivo: ${followLive?'ON':'OFF'}`; applyWindow(); });
  $('#btnSession').addEventListener('click',()=>{ sessionFilter=!sessionFilter; $('#btnSession').textContent=`Filtro sesión: ${sessionFilter?'ON':'OFF'}`; rebuildFromCache(); });

  // ===== Carga con degradación =====
  let RAW_CACHE=[]; // ticks normalizados (ts ms ART), sin filtrar
  async function fetchWithTimeout(url, ms=45000){
    const ctrl=new AbortController(); const t=setTimeout(()=>ctrl.abort(),ms);
    try{ return await fetch(url,{signal:ctrl.signal}); } finally{ clearTimeout(t); }
  }
  async function loadHistorical(){
    const limits=[1000000,300000,100000];
    let rows=null, used=null, lastErr=null;
    for(const L of limits){
      try{
        const r=await fetchWithTimeout(`/ticks/recent?limit=${L}`,45000);
        if(!r.ok) throw new Error(`HTTP ${r.status}`);
        rows=await r.json();
        if(!Array.isArray(rows)) throw new Error('Formato inesperado');
        used=L; break;
      }catch(e){ lastErr=e; }
    }
    if(!rows){ showOverlay('No se pudo obtener histórico (1e6/300k/100k).'); console.error('[ticks] fallo histórico', lastErr); return false; }
    console.log('[ticks] recibidos:', rows.length, 'limit usado:', used);

    RAW_CACHE = rows.map(r=>{
      const ts=parseTs(r.ts);
      const al=Number(r.al30), gd=Number(r.gd30);
      let ra = Number(r.ratio);
      if(!(ra>0) && al>0 && gd>0) ra = al/gd;
      return { ts, al30:al, gd30:gd, ratio:ra,
        source:r.source, bi_al30:r.bi_al30, of_al30:r.of_al30, bi_gd30:r.bi_gd30, of_gd30:r.of_gd30, book_al30:r.book_al30, book_gd30:r.book_gd30 };
    }).filter(o=>Number.isFinite(o.ts)).sort((a,b)=>a.ts-b.ts);

    if(RAW_CACHE.length===0){
      showOverlay('El endpoint devolvió 0 filas válidas. Revisá que /ticks/recent entregue datos.');
      console.warn('[ticks] RAW_CACHE vacío tras normalizar');
      return false;
    }
    hideOverlay();
    const ok = rebuildFromCache(true); // true: primer build (aplica fallback si filtro vacía)
    $('#ptsState').textContent = `Puntos: ${dataAL30.length.toLocaleString('es-AR')}`;
    $('#lastTs').textContent = lastTsMs ? `Último: ${fmtFullART(lastTsMs)}` : 'Último: —';
    const last = RAW_CACHE.at(-1); if(last?.source) $('#lastSource').textContent = String(last.source);
    console.log('[ticks] visibles:', dataAL30.length, 'filtro sesión:', sessionFilter);
    if(!ok) showOverlay('No hay puntos para mostrar (ni con ni sin filtro). Verificá el formato de ts/valores.');
    return ok;
  }

  // Construye series desde cache, respeta filtro; si queda vacío y es primera carga, relaja filtro
  function rebuildFromCache(firstBuild=false){
    dataAL30.length=dataGD30.length=dataRatio.length=0; ratioSum=0; lastTsMs=0; firstTsMs=0; ratioAvgDataset.data=[];
    let filtered = RAW_CACHE;
    if(sessionFilter) filtered = filtered.filter(o=>isInsideSessionART(o.ts));

    if(firstBuild && filtered.length===0 && sessionFilter){
      console.warn('[ticks] filtro de sesión dejó 0 → fallback a SIN filtro');
      sessionFilter=false; $('#btnSession').textContent='Filtro sesión: OFF';
      filtered = RAW_CACHE;
      setFooter('Mostrando datos SIN filtro de sesión (fallback automático).');
    }

    // Coalescencia ±1s
    let lastBin=0;
    for(const r of filtered){
      const al = (r.al30>0)?r.al30:NaN, gd=(r.gd30>0)?r.gd30:NaN, ra=(r.ratio>0)?r.ratio:(al>0&&gd>0?al/gd:NaN);
      if(!lastBin || Math.abs(r.ts-lastBin)>1000){
        dataAL30.push({x:r.ts,y:al}); dataGD30.push({x:r.ts,y:gd}); dataRatio.push({x:r.ts,y:ra}); lastBin=r.ts;
      }else{
        const i=dataAL30.length-1; if(i>=0){ dataAL30[i]={x:r.ts,y:al}; dataGD30[i]={x:r.ts,y:gd}; dataRatio[i]={x:r.ts,y:ra}; lastBin=r.ts; }
      }
      lastTsMs = r.ts;
    }
    firstTsMs=Math.min(dataAL30[0]?.x??Infinity,dataGD30[0]?.x??Infinity,dataRatio[0]?.x??Infinity);
    if(!Number.isFinite(firstTsMs)||firstTsMs===Infinity){ chart.update('none'); return false; }

    // Promedio ratio
    ratioSum = dataRatio.reduce((s,p)=>s+(Number.isFinite(p.y)?p.y:0),0);
    const n=dataRatio.length||1, avg=ratioSum/n;
    ratioAvgDataset.data=[{x:firstTsMs,y:avg},{x:lastTsMs,y:avg}];
    $('#avgRatio').textContent = fmtN(avg,6);
    $('#lastAL30').textContent = fmtN(dataAL30.at(-1)?.y,2);
    $('#lastGD30').textContent = fmtN(dataGD30.at(-1)?.y,2);
    $('#lastRatio').textContent = fmtN(dataRatio.at(-1)?.y,6);

    setActiveResButton(currentRes); adjustChartHeight(); anchor=followLive?'right':'left'; applyWindow();
    return dataAL30.length>0;
  }

  // Libros
  function validPos(v){ return Number.isFinite(v)&&v>0; }
  function parseBook(bk){ if(!bk) return null; if(typeof bk==='string'){ try{bk=JSON.parse(bk);}catch(_){return null;} }
    if(!bk||!Array.isArray(bk.bids)||!Array.isArray(bk.asks)) return null;
    return {bids:bk.bids.slice(0,5).map(p=>[+p[0],+p[1]]).filter(p=>validPos(p[0])&&p[1]>0),
            asks:bk.asks.slice(0,5).map(p=>[+p[0],+p[1]]).filter(p=>validPos(p[0])&&p[1]>0)};
  }
  function renderBook(tbodyEl, rows){
    const tb=tbodyEl.querySelector('tbody'); tb.innerHTML='';
    if(!rows.length){ const tr=document.createElement('tr'); const td=document.createElement('td'); td.colSpan=2; td.className='tiny'; td.textContent='—'; tr.appendChild(td); tb.appendChild(tr); return; }
    for(const [price,qty] of rows){ const tr=document.createElement('tr'); const tdP=document.createElement('td'); tdP.textContent=fmtN(price,2);
      const tdQ=document.createElement('td'); tdQ.textContent=qty.toLocaleString('es-AR'); tdQ.className='qty'; tr.append(tdP,tdQ); tb.appendChild(tr); }
  }
  function updateOrderBooks(tick){
    const bookA=parseBook(tick.book_al30), bookG=parseBook(tick.book_gd30);
    const bestBidA=validPos(tick.bi_al30)?+tick.bi_al30:(bookA?.bids[0]?.[0]??NaN);
    const bestAskA=validPos(tick.of_al30)?+tick.of_al30:(bookA?.asks[0]?.[0]??NaN);
    renderBook(document.getElementById('bookAL30Bids'), bookA?bookA.bids:[]); renderBook(document.getElementById('bookAL30Asks'), bookA?bookA.asks:[]);
    $('#bestAL30').textContent=(Number.isFinite(bestBidA)||Number.isFinite(bestAskA))?`${fmtN(bestBidA,2)} / ${fmtN(bestAskA,2)}`:'—';
    $('#spreadAL30').textContent=(Number.isFinite(bestBidA)&&Number.isFinite(bestAskA))?fmtN(bestAskA-bestBidA,2):'—';

    const bestBidG=validPos(tick.bi_gd30)?+tick.bi_gd30:(bookG?.bids[0]?.[0]??NaN);
    const bestAskG=validPos(tick.of_gd30)?+tick.of_gd30:(bookG?.asks[0]?.[0]??NaN);
    renderBook(document.getElementById('bookGD30Bids'), bookG?bookG.bids:[]); renderBook(document.getElementById('bookGD30Asks'), bookG?bookG.asks:[]);
    $('#bestGD30').textContent=(Number.isFinite(bestBidG)||Number.isFinite(bestAskG))?`${fmtN(bestBidG,2)} / ${fmtN(bestAskG,2)}`:'—';
    $('#spreadGD30').textContent=(Number.isFinite(bestBidG)&&Number.isFinite(bestAskG))?fmtN(bestAskG-bestBidG,2):'—';
  }

  // WS (simple; no cierro fuera de sesión para no ocultar problemas)
  function connectWS(){
    try{ if(ws) ws.close(1000); }catch(_){}
    const proto = location.protocol==='https:'?'wss':'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    $('#wsState').textContent='WS: conectando…'; $('#wsState').className='pill';
    ws.onopen=()=>{ $('#wsState').textContent='WS: OK'; $('#wsState').className='pill ws-ok'; };
    ws.onclose=()=>{ $('#wsState').textContent='WS: desconectado'; $('#wsState').className='pill ws-bad'; };
    ws.onerror=()=>{};
    ws.onmessage=ev=>{
      try{
        const t=JSON.parse(ev.data); const ts=parseTs(t.ts);
        if(!Number.isFinite(ts)) return;
        if(sessionFilter && !isInsideSessionART(ts)) return;
        handleTick({ ts, al30:+t.al30, gd30:+t.gd30, ratio:+t.ratio, source:t.source,
          bi_al30:t.bi_al30, of_al30:t.of_al30, bi_gd30:t.bi_gd30, of_gd30:t.of_gd30, book_al30:t.book_al30, book_gd30:t.book_gd30 });
      }catch(_){}
    }
  }
  function handleTick(r){
    const al=(r.al30>0)?r.al30:NaN, gd=(r.gd30>0)?r.gd30:NaN;
    const ra=(r.ratio>0)?r.ratio:(al>0&&gd>0?al/gd:NaN);
    const x=r.ts;
    if(!lastTsMs){ dataAL30.push({x,y:al}); dataGD30.push({x,y:gd}); dataRatio.push({x,y:ra}); firstTsMs=firstTsMs||x; lastTsMs=x; }
    else if(Math.abs(x-lastTsMs)<=1000){ const i=dataAL30.length-1; if(i>=0){ dataAL30[i]={x,y:al}; dataGD30[i]={x,y:gd}; dataRatio[i]={x,y:ra}; lastTsMs=x; } }
    else if(x>lastTsMs){ dataAL30.push({x,y:al}); dataGD30.push({x,y:gd}); dataRatio.push({x,y:ra}); lastTsMs=x; }
    $('#ptsState').textContent=`Puntos: ${dataAL30.length.toLocaleString('es-AR')}`;
    $('#lastTs').textContent=`Último: ${fmtFullART(lastTsMs)}`;
    $('#lastAL30').textContent=fmtN(dataAL30.at(-1)?.y,2);
    $('#lastGD30').textContent=fmtN(dataGD30.at(-1)?.y,2);
    $('#lastRatio').textContent=fmtN(dataRatio.at(-1)?.y,6);
    if(r.source) $('#lastSource').textContent=String(r.source);
    updateOrderBooks(r);
    if(followLive){ anchor='right'; applyWindow(); } else { chart.update('none'); }
  }

  // ===== Arranque =====
  (async function start(){
    setActiveResButton(currentRes); adjustChartHeight(); showOverlay('Cargando histórico…');
    try{
      const ok = await loadHistorical();
      if(ok) hideOverlay();
    }catch(e){
      console.error(e); showOverlay('Error cargando datos. Revisá la consola del navegador para más detalle.');
    }
    connectWS();
  })();
  </script>
</body>
</html>
