from pathlib import Path
import re

p = Path("webapp/src/main.jsx")
s = p.read_text(encoding="utf-8")

# 1) Добавляем helper telegram user.
if "function tgUser()" not in s:
    s = s.replace(
        "function tg() { return window.Telegram?.WebApp || null; }",
        '''function tg() { return window.Telegram?.WebApp || null; }
function tgUser() { return tg()?.initDataUnsafe?.user || null; }'''
    )

# 2) Avatar должен поддерживать photo_url.
# Меняем простую функцию Avatar, если она есть.
s = re.sub(
    r"function Avatar\(\{ name=\"A\" \}\) \{[\s\S]*?\n\}",
    '''function Avatar({ name="A", photoUrl=null }) {
  if (photoUrl) {
    return <img className="avatar" src={photoUrl} alt={name || "avatar"} />;
  }
  return <div className="avatar">{String(name || "A").slice(0,1).toUpperCase()}</div>;
}''',
    s,
    count=1,
)

# 3) В App добавляем telegram avatar в user.
s = s.replace(
    "const user = me.data || fallbackUser;",
    '''const tgProfile = tgUser();
  const user = {
    ...(me.data || fallbackUser),
    username: (me.data || fallbackUser).username || tgProfile?.username,
    full_name: (me.data || fallbackUser).full_name || [tgProfile?.first_name, tgProfile?.last_name].filter(Boolean).join(" "),
    photo_url: tgProfile?.photo_url || (me.data || fallbackUser).photo_url,
  };'''
)

# 4) Все <Avatar name=...> должны получить photoUrl, где есть user.
s = s.replace(
    '<Avatar name={user.full_name || user.username}',
    '<Avatar photoUrl={user.photo_url} name={user.full_name || user.username}'
)
s = s.replace(
    '<Avatar size="lg" name={user.full_name || user.username}',
    '<Avatar photoUrl={user.photo_url} size="lg" name={user.full_name || user.username}'
)

# 5) Добавляем state full viewer в App.
if "const [viewer, setViewer]" not in s:
    s = s.replace(
        'const [generation,setGeneration] = useState(null);',
        'const [generation,setGeneration] = useState(null);\\n  const [viewer, setViewer] = useState(null);'
    )

# 6) Перед return App добавим viewer в screens props.
s = s.replace(
    'feed:<Feed history={history.data} feed={feed.data} prompts={prompts.data} setScreen={setScreen}/>',
    'feed:<Feed history={history.data} feed={feed.data} prompts={prompts.data} setScreen={setScreen} setViewer={setViewer}/>'
)
s = s.replace(
    'home:<Home user={user} feed={feed.data} prompts={prompts.data} setScreen={setScreen}/>',
    'home:<Home user={user} feed={feed.data} prompts={prompts.data} setScreen={setScreen} setViewer={setViewer}/>'
)

# 7) Home/Feed сигнатуры.
s = s.replace(
    "function Home({ user, feed, prompts, setScreen })",
    "function Home({ user, feed, prompts, setScreen, setViewer })"
)
s = s.replace(
    "function Feed({ history, feed, prompts, setScreen })",
    "function Feed({ history, feed, prompts, setScreen, setViewer })"
)

# 8) Клик по feedCard открывает viewer, если есть result_url.
s = s.replace(
    'className="feedCard" onClick={() => setScreen("feed")}',
    'className="feedCard" onClick={() => f.result_url ? setViewer(f) : setScreen("feed")}'
)

# Для Feed screen, если там кнопки без onClick.
s = re.sub(
    r'<button key=\{f\.id \|\| i\} className="feedCard">',
    '<button key={f.id || i} className="feedCard" onClick={() => f.result_url && setViewer(f)}>',
    s
)

# 9) Добавляем publish API helper.
if "async function publishGeneration" not in s:
    s = s.replace(
        "async function api(path, options = {}) {",
        '''async function publishGeneration(id) {
  return api(`/generations/${id}/publish`, { method: "POST" });
}

async function api(path, options = {}) {'''
    )

# 10) Добавляем FullViewer component перед App.
if "function FullViewer(" not in s:
    s = s.replace(
        "function App() {",
        '''function FullViewer({ item, onClose }) {
  if (!item) return null;
  return <div className="viewer" onClick={onClose}>
    <div className="viewerPanel" onClick={(e) => e.stopPropagation()}>
      <button className="viewerClose" onClick={onClose}>×</button>
      {item.result_url ? <img src={item.result_url} alt="" /> : <Art type="a" />}
      <div className="viewerMeta">
        <b>{item.model || "Generation"}</b>
        <p>{item.prompt || "Промпт скрыт"}</p>
        <div className="viewerActions">
          <button onClick={() => item.id && publishGeneration(item.id)}>📚 В библиотеку</button>
          <button onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  </div>
}

function App() {'''
    )

# 11) Рендер viewer в App return.
s = s.replace(
    '<Nav screen={screen} setScreen={setScreen} credits={user.credits}/></main>',
    '<Nav screen={screen} setScreen={setScreen} credits={user.credits}/><FullViewer item={viewer} onClose={() => setViewer(null)} /></main>'
)

p.write_text(s, encoding="utf-8")
print("OK: miniapp avatar/viewer/publish patched")
