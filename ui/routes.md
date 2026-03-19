# Connecting Python to HTML with QWebChannel

## The idea

QWebChannel gives your HTML direct access to Python methods — no server, no ports,
no HTTP. JS handles only UI rendering. All logic, data, file handling, and AI calls
live in `bridge.py`.

```
JS side:      render UI, handle input events, call bridge
bridge.py:    ollama, RAG, file I/O, persistence, vault indexing
```

---

## Project structure

```
ui/
├── main.py          ← window setup, bridge registration
├── bridge.py        ← ALL logic — ollama, files, todos, vault
└── static/
    ├── index.html   ← UI only, no business logic
    ├── loading.html
    └── style.css
```

---

## Step 1 — Install dependencies

```bash
pip install PySide6 ollama
```

---

## Step 2 — bridge.py

Every `@Slot` method is callable from JS. Signals fire events back to JS.
This is where all the work happens — JS never does logic, only rendering.

```python
from PySide6.QtCore import QObject, Slot, Signal
from pathlib import Path
import ollama
import json

DOCS_DIR = Path.home() / ".johncode" / "documents"
TODOS_FILE = Path.home() / ".johncode" / "todos.json"

class Bridge(QObject):

    # ── Signals (Python → JS) ──
    token_received = Signal(str)   # fires per streaming token
    chat_done = Signal()           # fires when stream ends

    # ── Chat ──
    @Slot(str, str)
    def chat(self, model, prompt):
        for chunk in ollama.generate(model=model, prompt=prompt, stream=True):
            self.token_received.emit(chunk["response"])
        self.chat_done.emit()

    # ── Documents ──
    @Slot(str, result=str)
    def upload_document(self, filename):
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        # file reading / embedding happens here
        size_str = "—"
        try:
            f = DOCS_DIR / filename
            size_str = f"{f.stat().st_size // 1024} KB" if f.exists() else "uploaded"
        except Exception:
            pass
        return json.dumps({"name": filename, "size": size_str})

    @Slot(result=str)
    def get_documents(self):
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        files = [
            {"name": f.name, "size": f"{f.stat().st_size // 1024} KB"}
            for f in sorted(DOCS_DIR.iterdir())
            if f.is_file()
        ]
        return json.dumps(files)

    # ── Vault ──
    @Slot(result=str)
    def get_vault_status(self):
        notes = list(Path.home().glob("Documents/**/*.md"))
        return f"{len(notes)} notes found"

    @Slot(result=str)
    def index_vault(self):
        notes = list(Path.home().glob("Documents/**/*.md"))
        # embed notes into vector store here
        return f"Indexed {len(notes)} notes"

    @Slot(result=str)
    def get_vault_notes(self):
        notes = list(Path.home().glob("Documents/**/*.md"))
        data = [
            {
                "name": n.stem,
                "modified": n.stat().st_mtime
            }
            for n in sorted(notes, key=lambda x: x.stat().st_mtime, reverse=True)[:50]
        ]
        return json.dumps(data)

    # ── Todos ──
    def _load_todos(self):
        if TODOS_FILE.exists():
            return json.loads(TODOS_FILE.read_text())
        return []

    def _save_todos(self, todos):
        TODOS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TODOS_FILE.write_text(json.dumps(todos, indent=2))

    @Slot(result=str)
    def get_todos(self):
        return json.dumps(self._load_todos())

    @Slot(str, str, str)
    def add_todo(self, id, text, parent_id):
        todos = self._load_todos()
        todos.append({"id": id, "text": text, "done": False, "parent": parent_id})
        self._save_todos(todos)

    @Slot(str)
    def toggle_todo(self, id):
        todos = self._load_todos()
        for t in todos:
            if t["id"] == id:
                t["done"] = not t["done"]
        self._save_todos(todos)

    @Slot(str)
    def delete_todo(self, id):
        todos = self._load_todos()
        todos = [t for t in todos if t["id"] != id and t.get("parent") != id]
        self._save_todos(todos)
```

---

## Step 3 — main.py

```python
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineScript
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl, QTimer, QFile, QIODevice
from PySide6.QtGui import QColor
from pathlib import Path
from bridge import Bridge

app = QApplication(sys.argv)

window = QWebEngineView()
window.setWindowTitle("JohnCode")
window.resize(1000, 700)
window.page().setBackgroundColor(QColor("#0d1b3e"))

# ── Register bridge ──
bridge = Bridge()
channel = QWebChannel()
channel.registerObject("bridge", bridge)
window.page().setWebChannel(channel)

# ── Inject qwebchannel.js (shipped with Qt) ──
qwebchannel_js = QFile(":/qtwebchannel/qwebchannel.js")
qwebchannel_js.open(QIODevice.ReadOnly)
js_code = bytes(qwebchannel_js.readAll()).decode()
qwebchannel_js.close()

script = QWebEngineScript()
script.setName("qwebchannel")
script.setSourceCode(js_code)
script.setInjectionPoint(QWebEngineScript.DocumentCreation)
script.setWorldId(QWebEngineScript.MainWorld)
window.page().scripts().insert(script)

# ── Loading screen → app ──
static = Path(__file__).parent / "static"
loading_path = static / "loading.html"
app_path = static / "index.html"

loaded_once = False

def on_loaded(ok):
    global loaded_once
    if not loaded_once:
        loaded_once = True
        window.page().runJavaScript("""
            document.body.style.transition = 'opacity 0.4s ease';
            document.body.style.opacity = '0';
        """)
        QTimer.singleShot(400, lambda: window.load(QUrl.fromLocalFile(str(app_path))))

window.load(QUrl.fromLocalFile(str(loading_path)))
window.loadFinished.connect(on_loaded)
window.show()

sys.exit(app.exec())
```

---

## Step 4 — How JS talks to bridge.py

The rule is simple: **JS calls bridge, bridge returns data, JS renders it.**
JS never fetches, never computes, never stores.

```javascript
// Boot sequence — runs once bridge is ready
new QWebChannel(qt.webChannelTransport, function(channel) {
    window.bridge = channel.objects.bridge;

    // Listen for streaming tokens from Python
    bridge.token_received.connect(function(token) {
        const el = document.getElementById(window.currentBotId);
        if (el) el.textContent += token;
    });

    bridge.chat_done.connect(function() {
        window.currentBotId = null;
        document.getElementById('send-btn').disabled = false;
    });

    // Load persisted data on startup
    bridge.get_vault_status(result => {
        document.getElementById('vault-count').textContent = result;
    });
    loadDocuments();
    loadTodos();
});
```

---

## Responsibility split

| What | Where |
|---|---|
| Render messages, panels, lists | `index.html` JS |
| Panel switching, input events | `index.html` JS |
| Ollama chat + streaming | `bridge.py` |
| File reading + RAG embedding | `bridge.py` |
| Vault scanning + indexing | `bridge.py` |
| Todo persistence (JSON/SQLite) | `bridge.py` |
| Document storage | `bridge.py` |

---

## Slot reference

| Signature | Use case |
|---|---|
| `@Slot(result=str)` | No args, returns data |
| `@Slot(str)` | Takes one arg, no return |
| `@Slot(str, str)` | Takes two args, no return |
| `@Slot(str, result=str)` | Takes one arg, returns data |
| `@Slot(str, str, str)` | Takes three args, no return |

Signals fire from Python to JS:

```python
# Python fires
self.token_received.emit("some text")

# JS listens
bridge.token_received.connect(function(text) { ... })
```

---

## Data persistence

Todos and documents are stored in `~/.johncode/` — a hidden folder in the user's
home directory. This keeps app data out of the project folder and survives reinstalls.

```
~/.johncode/
├── todos.json
└── documents/
    ├── company_handbook.pdf
    └── meeting_notes.txt
```

Bridge reads and writes this on every call — no in-memory state needed in JS.