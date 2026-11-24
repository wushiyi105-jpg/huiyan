"""Web 入口:零依赖 http.server,单页 + JSON API(含图片上传)。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import agent, db as dbmod, llm

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>慧眼 · 拍照识物生活助手</title>
<style>
  :root {
    --bg:#f4f7fb; --card:#ffffff; --ink:#1f2937; --muted:#6b7280;
    --blue:#2563eb; --blue-soft:#dbeafe; --amber:#f59e0b; --amber-soft:#fef3c7;
    --green:#16a34a; --green-soft:#dcfce7; --red:#dc2626; --red-soft:#fee2e2;
    --line:#e5e7eb; --radius:16px;
  }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
         background:var(--bg); color:var(--ink); }
  .wrap { max-width:1080px; margin:0 auto; padding:28px 20px 80px; }
  header { display:flex; align-items:baseline; gap:12px; margin-bottom:4px; }
  header h1 { font-size:24px; margin:0; letter-spacing:.5px; }
  .badge { font-size:12px; padding:3px 10px; border-radius:999px; background:var(--blue-soft); color:var(--blue); }
  .sub { color:var(--muted); margin:4px 0 22px; font-size:14px; }
  .grid { display:grid; grid-template-columns:1.1fr .9fr; gap:18px; align-items:start; }
  @media (max-width:860px){ .grid { grid-template-columns:1fr; } }
  .card { background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
          padding:18px; box-shadow:0 1px 2px rgba(16,24,40,.04); }
  .drop { border:2px dashed var(--line); border-radius:14px; padding:26px; text-align:center;
          color:var(--muted); cursor:pointer; transition:.15s; }
  .drop.over { border-color:var(--blue); background:var(--blue-soft); }
  .drop img { max-width:100%; max-height:220px; border-radius:10px; margin-bottom:8px; }
  input[type=file] { display:none; }
  textarea { width:100%; padding:12px 14px; border:1px solid var(--line); border-radius:12px;
             font-size:15px; font-family:inherit; resize:vertical; min-height:44px; }
  textarea:focus { outline:none; border-color:var(--blue); box-shadow:0 0 0 3px var(--blue-soft); }
  button { background:var(--blue); color:#fff; border:none; padding:11px 22px; border-radius:12px;
           font-size:15px; cursor:pointer; }
  button:hover { filter:brightness(1.06); }
  button:disabled { opacity:.6; cursor:not-allowed; }
  .hint { color:var(--muted); font-size:12px; margin:8px 0; }
  .spin { display:inline-block; width:15px; height:15px; border:2px solid #fff;
          border-top-color:transparent; border-radius:50%; animation:sp .7s linear infinite; vertical-align:-2px; }
  @keyframes sp { to { transform:rotate(360deg); } }
  .answer { display:none; }
  .answer.show { display:block; margin-top:16px; }
  .answer-box { background:var(--blue-soft); border-radius:12px; padding:13px 15px; line-height:1.7; white-space:pre-wrap; font-size:15px; }
  .steps { margin-top:12px; }
  .step { border:1px solid var(--line); border-radius:12px; padding:9px 12px; margin-bottom:8px; font-size:13px; }
  .step .tool { font-weight:600; color:var(--blue); font-family:ui-monospace,monospace; }
  .step .args { color:var(--muted); margin:3px 0; word-break:break-all; }
  .step .res { color:var(--muted); border-top:1px dashed var(--line); padding-top:5px; margin-top:5px; }
  h3 { font-size:14px; margin:0 0 10px; color:var(--muted); font-weight:600; }
  .rec { font-size:13px; padding:8px 0; border-bottom:1px solid #f1f5f9; }
  .rec:last-child { border-bottom:none; }
  .rec .d { color:var(--muted); }
  .empty { color:var(--muted); font-size:13px; }
</style>
</head>
<body>
<div class="wrap">
  <header><h1>慧眼 · 拍照识物生活助手</h1><span class="badge" id="badge">…</span></header>
  <p class="sub">拍一张图——体检报告、药品说明、衣服标签、配料表、植物……它识别内容并给出解读与建议。</p>

  <div class="grid">
    <div>
      <div class="card">
        <div class="drop" id="drop">
          <div id="drop-txt">📷 点击或拖入图片</div>
          <img id="preview" style="display:none">
        </div>
        <input type="file" id="file" accept="image/*">
        <textarea id="q" placeholder="补充问题(可选),例:这个体检报告有什么要注意的?"></textarea>
        <div class="hint">支持 jpg/png/webp;建议单张 < 5MB。</div>
        <button id="send">识别</button>
        <div class="answer" id="ans">
          <div class="answer-box" id="ans-box"></div>
          <div class="steps" id="steps"></div>
        </div>
      </div>
    </div>
    <div>
      <div class="card">
        <h3>📈 健康指标</h3>
        <div id="metrics"><div class="empty">暂无记录。</div></div>
        <h3 style="margin-top:16px">🗒 识物记录</h3>
        <div id="notes"><div class="empty">暂无记录。</div></div>
      </div>
    </div>
  </div>
</div>

<script>
const $ = s => document.querySelector(s);
const esc = s => String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let imgData = null, imgMime = null;

const drop = $('#drop'), file = $('#file');
drop.onclick = ()=>file.click();
file.onchange = ()=>loadFile(file.files[0]);
['dragover','dragenter'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('over');}));
['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('over');}));
drop.addEventListener('drop',e=>{ if(e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]); });

function loadFile(f){
  if(!f || !f.type.startsWith('image/')){ alert('请选择图片文件'); return; }
  imgMime = f.type;
  const r = new FileReader();
  r.onload = ()=>{
    imgData = r.result.split(',')[1];
    const pv = $('#preview'); pv.src = r.result; pv.style.display='block';
    $('#drop-txt').style.display='none';
  };
  r.readAsDataURL(f);
}

async function post(path, body){
  const r = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  return r.json();
}
function renderSteps(steps){
  const el = $('#steps'); el.innerHTML='';
  if(!steps||!steps.length) return;
  steps.forEach((s,i)=>{
    const args = Object.entries(s.arguments||{}).map(([k,v])=>k+'='+esc(JSON.stringify(v))).join(', ');
    const r = s.result||{};
    let resHtml = r.error ? '<span style="color:var(--red)">❌ '+esc(r.error)+'</span>'
                : r.saved ? '✓ '+esc(r.saved) : esc(JSON.stringify(r));
    el.innerHTML += '<div class="step"><div class="tool">'+(i+1)+'. '+esc(s.tool)+'</div>'+
      '<div class="args">'+esc(args)+'</div><div class="res">'+resHtml+'</div></div>';
  });
}

$('#send').onclick = async ()=>{
  if(!imgData){ alert('请先选择图片'); return; }
  const btn = $('#send'); btn.disabled=true; btn.innerHTML='<span class="spin"></span>';
  $('#ans').classList.remove('show');
  try{
    const r = await post('/api/analyze',{image_base64:imgData, mime:imgMime, question:$('#q').value});
    $('#ans-box').textContent = r.answer||'';
    renderSteps(r.steps);
    $('#ans').classList.add('show');
    loadRecords();
  }catch(e){ $('#ans-box').textContent='请求失败:'+e; $('#ans').classList.add('show'); }
  btn.disabled=false; btn.innerHTML='识别';
};

async function loadRecords(){
  try{
    const d = await (await fetch('/api/records')).json();
    const mEl=$('#metrics');
    if(!d.metrics.length){ mEl.innerHTML='<div class="empty">暂无记录。</div>'; }
    else{ mEl.innerHTML=''; d.metrics.forEach(m=>{
      mEl.innerHTML += '<div class="rec">'+esc(m.name)+' <b>'+m.value+'</b> '+(m.unit?esc(m.unit):'')+'<div class="d">'+esc(m.date)+'</div></div>';
    }); }
    const nEl=$('#notes');
    if(!d.notes.length){ nEl.innerHTML='<div class="empty">暂无记录。</div>'; }
    else{ nEl.innerHTML=''; d.notes.forEach(n=>{
      nEl.innerHTML += '<div class="rec"><b>'+esc(n.title)+'</b> <span style="color:var(--muted)">['+(n.category?esc(n.category):'未分类')+']</span><div class="d">'+esc(n.date)+'</div></div>';
    }); }
  }catch(e){}
}

fetch('/api/status').then(r=>r.json()).then(s=>{
  const b=$('#badge');
  if(s.mock){ b.textContent='离线演示'; b.style.background='#fee2e2'; b.style.color='#b91c1c'; }
  else{ b.textContent=s.model||'已连接'; b.style.background='#dcfce7'; b.style.color='#15803d'; }
}).catch(()=>{});
loadRecords();
</script>
</body>
</html>
"""


def _make_handler(db, cfg, force_mock):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, ctype: str, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200):
            self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8", status)

        def _read_json(self):
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", errors="replace")
            return json.loads(text) if text else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/status":
                mock_mode = force_mock or not cfg.get("api_key")
                self._json({"mock": mock_mode, "model": None if mock_mode else cfg.get("model")})
            elif path == "/api/records":
                self._json({"metrics": db.all_metrics(20), "notes": db.list_notes(20)})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._read_json()
                if path == "/api/analyze":
                    r = agent.run_data(body.get("image_base64", ""), body.get("mime", ""),
                                       body.get("question", ""), db=db, config=cfg, force_mock=force_mock)
                    self._json(r)
                else:
                    self._json({"error": "not found"}, 404)
            except llm.LLMError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 500)

        def log_message(self, *args):
            pass

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000, db_path: str | None = None, force_mock: bool = False):
    db = dbmod.Database(db_path)
    cfg = llm.default_config()
    handler = _make_handler(db, cfg, force_mock)
    httpd = ThreadingHTTPServer((host, port), handler)
    mode = "离线演示模式(未配置 key)" if (force_mock or not cfg.get("api_key")) else f"模型:{cfg.get('model')}"
    print(f"👁 慧眼已启动:http://{host}:{port}  [{mode}]")
    print("   按 Ctrl+C 停止")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
