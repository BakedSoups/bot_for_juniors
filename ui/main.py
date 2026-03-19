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