import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QColor
from pathlib import Path

app = QApplication(sys.argv)

window = QWebEngineView()
window.setWindowTitle("CampyBot")
window.resize(1000, 700)

window.page().setBackgroundColor(QColor("#0d1b3e"))

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