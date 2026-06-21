#!/usr/bin/env python3
"""
Telegram Bot Tester — интерактивный симулятор пользователя.

Запуск:
    python bot_tester.py <BOT_TOKEN> [--user-id YOUR_TELEGRAM_ID] [--port 8765]

Открой в браузере: http://localhost:8765

Без зависимостей — только Python stdlib.
"""

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import Empty, Queue

TG = "https://api.telegram.org/bot"
TOKEN = ""
USER_ID = 0
updates_queue: Queue = Queue()
offset = 0
bot_info: dict = {}


def tg(method: str, **params) -> dict:
    url = f"{TG}{TOKEN}/{method}"
    data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else str(v))
            for k, v in params.items() if v is not None}
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except Exception as e:
        return {"ok": False, "description": str(e)}


def poll_loop():
    global offset
    while True:
        resp = tg("getUpdates", offset=offset, timeout=30,
                  allowed_updates=["message", "callback_query"])
        if resp.get("ok"):
            for upd in resp.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("callback_query", {}).get("message")

                if msg and msg.get("from", {}).get("id") != USER_ID:
                    event = {
                        "type": "message",
                        "text": msg.get("text", ""),
                        "photo": bool(msg.get("photo")),
                        "caption": msg.get("caption", ""),
                        "reply_markup": msg.get("reply_markup"),
                        "ts": msg.get("date", int(time.time())),
                        "message_id": msg.get("message_id"),
                        "edited": False,
                    }
                    updates_queue.put(event)

                edited = upd.get("edited_message")
                if edited and edited.get("from", {}).get("id") != USER_ID:
                    updates_queue.put({
                        "type": "message",
                        "text": edited.get("text", ""),
                        "caption": edited.get("caption", ""),
                        "reply_markup": edited.get("reply_markup"),
                        "ts": edited.get("date", int(time.time())),
                        "message_id": edited.get("message_id"),
                        "edited": True,
                    })
        else:
            time.sleep(2)


HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bot Tester</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#1c1c1e;
  display:flex;align-items:center;justify-content:center;
  min-height:100vh;
}
#app{
  width:390px;height:720px;
  background:#17212b;
  border-radius:16px;
  overflow:hidden;
  display:flex;flex-direction:column;
  box-shadow:0 24px 80px rgba(0,0,0,.6);
  border:1px solid rgba(255,255,255,.06);
}
#header{
  background:#232e3c;
  padding:12px 16px;
  display:flex;align-items:center;gap:12px;
  border-bottom:1px solid rgba(255,255,255,.05);
  flex-shrink:0;
}
#avatar{
  width:40px;height:40px;border-radius:50%;
  background:#5288c1;
  display:flex;align-items:center;justify-content:center;
  font-size:18px;color:#fff;font-weight:600;flex-shrink:0;
}
#bot-name{color:#fff;font-size:15px;font-weight:600}
#bot-status{color:#7d8e9e;font-size:12px;margin-top:1px}
#status-dot{
  width:8px;height:8px;border-radius:50%;
  background:#4caf50;margin-left:auto;flex-shrink:0;
  transition:background .3s;
}
#status-dot.off{background:#666}
#messages{
  flex:1;overflow-y:auto;
  padding:12px 10px;
  display:flex;flex-direction:column;gap:6px;
  scroll-behavior:smooth;
}
#messages::-webkit-scrollbar{width:4px}
#messages::-webkit-scrollbar-track{background:transparent}
#messages::-webkit-scrollbar-thumb{background:#2e3e50;border-radius:2px}
.msg-wrap{display:flex;flex-direction:column;max-width:82%}
.msg-wrap.user{align-self:flex-end;align-items:flex-end}
.msg-wrap.bot{align-self:flex-start;align-items:flex-start}
.bubble{
  padding:8px 12px;
  border-radius:12px;
  font-size:14px;line-height:1.45;
  word-break:break-word;
  position:relative;
}
.bot .bubble{background:#232e3c;color:#e8eaf0;border-bottom-left-radius:3px}
.user .bubble{background:#2b5278;color:#fff;border-bottom-right-radius:3px}
.edited-tag{font-size:10px;color:#7d8e9e;margin-top:2px;padding:0 4px}
.ts{font-size:10px;color:#7d8e9e;margin-top:3px;padding:0 4px}
.inline-kb{
  display:flex;flex-direction:column;gap:4px;
  margin-top:6px;width:100%;
}
.kb-row{display:flex;gap:4px}
.kb-btn{
  flex:1;
  background:#1a2535;
  border:1px solid #2d4158;
  border-radius:8px;
  padding:8px 6px;
  color:#5ba3d9;
  font-size:12px;font-weight:500;
  cursor:pointer;
  text-align:center;
  transition:background .15s,transform .1s;
}
.kb-btn:hover{background:#223043}
.kb-btn:active{background:#1a2535;transform:scale(.97)}
.kb-btn.pressed{background:#1d3451;color:#7ebfe8}
#input-area{
  background:#232e3c;
  padding:10px 12px;
  display:flex;align-items:flex-end;gap:8px;
  border-top:1px solid rgba(255,255,255,.05);
  flex-shrink:0;
}
#msg-input{
  flex:1;
  background:#17212b;
  border:1px solid #2d3f54;
  border-radius:20px;
  padding:9px 14px;
  color:#e8eaf0;
  font-size:14px;
  resize:none;
  min-height:38px;max-height:120px;
  outline:none;
  font-family:inherit;
  line-height:1.4;
}
#msg-input::placeholder{color:#4a5a6a}
#msg-input:focus{border-color:#3d5a78}
#send-btn{
  width:38px;height:38px;
  background:#2b5278;
  border:none;border-radius:50%;
  color:#fff;font-size:16px;
  cursor:pointer;
  flex-shrink:0;
  display:flex;align-items:center;justify-content:center;
  transition:background .15s,transform .1s;
}
#send-btn:hover{background:#3a6591}
#send-btn:active{transform:scale(.93)}
#send-btn:disabled{background:#2a3b4c;color:#4a5a6a;cursor:default}
.system-msg{
  align-self:center;
  background:#1e2d3d;
  color:#7d8e9e;
  font-size:11px;
  padding:4px 10px;
  border-radius:10px;
  margin:4px 0;
}
.typing{
  align-self:flex-start;
  display:flex;align-items:center;gap:4px;
  padding:8px 14px;
  background:#232e3c;
  border-radius:12px;border-bottom-left-radius:3px;
}
.typing span{
  width:6px;height:6px;border-radius:50%;
  background:#7d8e9e;
  animation:bounce .9s infinite;
}
.typing span:nth-child(2){animation-delay:.15s}
.typing span:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-5px)}}
</style>
</head>
<body>
<div id="app">
  <div id="header">
    <div id="avatar">?</div>
    <div>
      <div id="bot-name">Загрузка...</div>
      <div id="bot-status">Подключение...</div>
    </div>
    <div id="status-dot" class="off"></div>
  </div>
  <div id="messages">
    <div class="system-msg">Сессия началась</div>
  </div>
  <div id="input-area">
    <textarea id="msg-input" placeholder="Сообщение..." rows="1"></textarea>
    <button id="send-btn" disabled>&#10148;</button>
  </div>
</div>
<script>
const chat = document.getElementById('messages');
const input = document.getElementById('msg-input');
const sendBtn = document.getElementById('send-btn');
const statusDot = document.getElementById('status-dot');
let polling = false;

function fmt(ts){
  return new Date(ts*1000).toLocaleTimeString('ru',{hour:'2-digit',minute:'2-digit'});
}

function addSystem(text){
  const d = document.createElement('div');
  d.className='system-msg'; d.textContent=text;
  chat.appendChild(d); scroll();
}

function addMessage(side, text, ts, replyMarkup, edited, caption){
  const wrap = document.createElement('div');
  wrap.className = 'msg-wrap '+side;

  const bub = document.createElement('div');
  bub.className = 'bubble';

  const content = (text || '') + (caption ? (text?'\n':'')+caption : '');
  bub.textContent = content;

  if(edited){
    const et=document.createElement('div');
    et.className='edited-tag'; et.textContent='изменено';
    bub.appendChild(et);
  }
  wrap.appendChild(bub);

  if(replyMarkup && replyMarkup.inline_keyboard){
    const kb = document.createElement('div');
    kb.className='inline-kb';
    replyMarkup.inline_keyboard.forEach(row=>{
      const r=document.createElement('div'); r.className='kb-row';
      row.forEach(btn=>{
        const b=document.createElement('button');
        b.className='kb-btn';
        b.textContent=btn.text;
        b.onclick=()=>handleCallback(b, btn.callback_data, btn.url, btn.text);
        r.appendChild(b);
      });
      kb.appendChild(r);
    });
    wrap.appendChild(kb);
  }

  const t=document.createElement('div');
  t.className='ts'; t.textContent=fmt(ts||Date.now()/1000);
  wrap.appendChild(t);

  chat.appendChild(wrap);
  scroll();
}

function showTyping(){
  const d=document.createElement('div'); d.className='typing'; d.id='typing-ind';
  d.innerHTML='<span></span><span></span><span></span>';
  chat.appendChild(d); scroll();
}
function hideTyping(){ const t=document.getElementById('typing-ind'); if(t)t.remove(); }

function scroll(){ chat.scrollTop=chat.scrollHeight; }

async function handleCallback(btn, data, url, text){
  if(url){ window.open(url,'_blank'); return; }
  if(!data) return;
  btn.classList.add('pressed');
  addMessage('user', text, Date.now()/1000, null, false, '');
  showTyping();
  try{
    await fetch('/api/callback',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({data})
    });
  }catch(e){}
}

async function send(){
  const text=input.value.trim();
  if(!text) return;
  input.value=''; input.style.height='';
  sendBtn.disabled=true;
  addMessage('user', text, Date.now()/1000, null, false, '');
  showTyping();
  try{
    await fetch('/api/send',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text})
    });
  }catch(e){ addSystem('Ошибка отправки'); }
  setTimeout(()=>{ sendBtn.disabled=false; input.focus(); },300);
}

sendBtn.onclick=send;
input.addEventListener('keydown', e=>{
  if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); send(); }
});
input.addEventListener('input',()=>{
  input.style.height='auto';
  input.style.height=Math.min(input.scrollHeight,120)+'px';
});

async function pollUpdates(){
  if(polling) return; polling=true;
  while(true){
    try{
      const r=await fetch('/api/updates');
      const data=await r.json();
      hideTyping();
      if(data.events && data.events.length){
        data.events.forEach(ev=>{
          addMessage('bot', ev.text, ev.ts, ev.reply_markup, ev.edited, ev.caption);
        });
      }
      statusDot.classList.remove('off');
      document.getElementById('bot-status').textContent='онлайн';
    }catch(e){
      statusDot.classList.add('off');
      document.getElementById('bot-status').textContent='нет связи';
      await new Promise(r=>setTimeout(r,2000));
    }
    await new Promise(r=>setTimeout(r,300));
  }
}

async function init(){
  try{
    const r=await fetch('/api/me');
    const d=await r.json();
    if(d.ok){
      const bot=d.result;
      document.getElementById('bot-name').textContent=bot.first_name;
      document.getElementById('bot-status').textContent='@'+bot.username;
      const a=document.getElementById('avatar');
      a.textContent=bot.first_name[0].toUpperCase();
      sendBtn.disabled=false;
      input.focus();
      addSystem('Бот: @'+bot.username+' • Введи /start');
    }else{
      addSystem('Ошибка: '+d.description);
    }
  }catch(e){ addSystem('Не удалось подключиться к серверу'); }
  pollUpdates();
}

init();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        if self.path == "/":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/me":
            self.send_json(tg("getMe"))

        elif self.path == "/api/updates":
            events = []
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    ev = updates_queue.get(timeout=0.3)
                    events.append(ev)
                    while not updates_queue.empty():
                        events.append(updates_queue.get_nowait())
                    break
                except Empty:
                    pass
            self.send_json({"events": events})

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        body = self.read_body()

        if self.path == "/api/send":
            text = body.get("text", "")
            resp = tg("sendMessage", chat_id=USER_ID, text=text, parse_mode="HTML")
            self.send_json(resp)

        elif self.path == "/api/callback":
            cb_data = body.get("data", "")
            resp = tg("sendMessage", chat_id=USER_ID, text=cb_data)
            self.send_json(resp)

        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    global TOKEN, USER_ID, offset

    parser = argparse.ArgumentParser(description="Telegram Bot Tester")
    parser.add_argument("token", nargs="?", help="Bot token")
    parser.add_argument("--user-id", type=int, default=0, help="Your Telegram user ID")
    parser.add_argument("--port", type=int, default=8765, help="Local port (default 8765)")
    args = parser.parse_args()

    if not args.token:
        print("Использование: python bot_tester.py <BOT_TOKEN> [--user-id YOUR_ID]")
        print("\nКак получить user-id: напиши @userinfobot в Telegram")
        sys.exit(1)

    TOKEN = args.token
    USER_ID = args.user_id

    print("\n┌─ Telegram Bot Tester ─────────────────┐")

    me = tg("getMe")
    if not me.get("ok"):
        print(f"│ ✗ Ошибка токена: {me.get('description')}")
        sys.exit(1)

    bot = me["result"]
    print(f"│ Бот:  {bot['first_name']} (@{bot['username']})")
    print(f"│ ID:   {bot['id']}")

    if USER_ID:
        print(f"│ Ты:   user_id={USER_ID}")
        drain = tg("getUpdates", offset=-1)
        if drain.get("ok") and drain.get("result"):
            offset = drain["result"][-1]["update_id"] + 1
    else:
        print("│ ⚠  --user-id не задан, все входящие сообщения будут видны")

    print(f"│ URL:  http://localhost:{args.port}")
    print("└───────────────────────────────────────┘\n")

    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()

    server = HTTPServer(("localhost", args.port), Handler)
    print(f"Открой браузер: http://localhost:{args.port}")
    print("Ctrl+C для остановки\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлен.")


if __name__ == "__main__":
    main()
