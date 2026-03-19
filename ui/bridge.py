import json
import shutil
from pathlib import Path

import ollama
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QFileDialog

DOCS_DIR = Path.home() / ".johncode" / "documents"
DOCS_INDEX = DOCS_DIR / "index.json"
TODOS_FILE = Path.home() / ".johncode" / "todos.json"
ROOT_DIR = Path(__file__).resolve().parent.parent
MODELFILE = ROOT_DIR / "developer.modelfile"
CUSTOM_MODEL_NAME = MODELFILE.stem


class Bridge(QObject):
    token_received = Signal(str)
    chat_done = Signal()
    chat_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.model_name = self._ensure_model_name()

    def _base_model_name(self):
        if not MODELFILE.exists():
            return "llama3.1:8b"

        for raw_line in MODELFILE.read_text().splitlines():
            line = raw_line.strip()
            if line.upper().startswith("FROM "):
                return line.split(None, 1)[1].strip()

        return "llama3.1:8b"

    def _list_models(self):
        local_names = set()
        try:
            response = ollama.list()
            models = response.get("models", []) if isinstance(response, dict) else []
            for model in models:
                name = model.get("model") or model.get("name")
                if name:
                    local_names.add(name)
        except Exception:
            pass
        return local_names

    def _ensure_model_name(self):
        local_names = self._list_models()
        if CUSTOM_MODEL_NAME in local_names:
            return CUSTOM_MODEL_NAME

        tagged_name = f"{CUSTOM_MODEL_NAME}:latest"
        if tagged_name in local_names:
            return tagged_name

        return CUSTOM_MODEL_NAME

    def _load_docs_index(self):
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        if DOCS_INDEX.exists():
            try:
                return json.loads(DOCS_INDEX.read_text())
            except Exception:
                return []
        return []

    def _save_docs_index(self, entries):
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        DOCS_INDEX.write_text(json.dumps(entries, indent=2))

    def _extract_text(self, path):
        suffix = path.suffix.lower()

        if suffix in {".txt", ".md", ".py", ".json", ".csv"}:
            return path.read_text(errors="ignore")

        if suffix == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore

                reader = PdfReader(str(path))
                return "\n\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception:
                return ""

        return ""

    def _document_record(self, path, extracted_text):
        preview = ""
        if extracted_text.strip():
            preview = " ".join(extracted_text.split())[:180]

        return {
            "name": path.name,
            "path": str(path),
            "size": f"{max(1, path.stat().st_size // 1024)} KB",
            "kind": path.suffix.lower().lstrip(".") or "file",
            "preview": preview,
            "has_text": bool(extracted_text.strip()),
            "cover": "",
        }

    def _upsert_document(self, record):
        docs = self._load_docs_index()
        docs = [doc for doc in docs if doc["name"] != record["name"]]
        docs.append(record)
        docs.sort(key=lambda doc: doc["name"].lower())
        self._save_docs_index(docs)

    def _update_document(self, document_name, updates):
        docs = self._load_docs_index()
        changed = None
        for doc in docs:
            if doc["name"] == document_name:
                doc.update(updates)
                changed = doc
                break
        if changed:
            self._save_docs_index(docs)
        return changed

    def _stream_prompt(self, prompt):
        try:
            for chunk in ollama.generate(model=self.model_name, prompt=prompt, stream=True):
                self.token_received.emit(chunk["response"])
        except Exception as exc:
            self.chat_error.emit(str(exc))
        finally:
            self.chat_done.emit()

    @Slot(result=str)
    def ensure_model(self):
        try:
            if hasattr(ollama, "create"):
                try:
                    ollama.create(model=CUSTOM_MODEL_NAME, modelfile=MODELFILE.read_text())
                except TypeError:
                    ollama.create(
                        model=CUSTOM_MODEL_NAME,
                        from_=self._base_model_name(),
                        system='You are a senior developer peer. Be concise like a Stack Overflow answer. Focus on logic and snippets (max 10 lines). Never provide full implementations unless asked.',
                    )
            self.model_name = self._ensure_model_name()
            return json.dumps({"ok": True, "model": self.model_name})
        except Exception as exc:
            self.model_name = self._ensure_model_name()
            return json.dumps({"ok": False, "model": self.model_name, "error": str(exc)})

    @Slot(result=str)
    def get_bootstrap(self):
        return json.dumps(
            {
                "app_name": "JohnCode",
                "model": self.model_name,
                "ready": True,
                "documents_dir": str(DOCS_DIR),
                "modelfile": str(MODELFILE),
            }
        )

    @Slot(str)
    def chat(self, prompt):
        self._stream_prompt(prompt)

    @Slot(result=str)
    def pick_document(self):
        selected, _ = QFileDialog.getOpenFileName(
            None,
            "Import Document",
            str(Path.home()),
            "Documents (*.pdf *.txt *.md *.py *.json *.csv);;All Files (*)",
        )
        if not selected:
            return json.dumps({"ok": False, "cancelled": True})

        source = Path(selected)
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        destination = DOCS_DIR / source.name

        counter = 1
        while destination.exists() and destination.resolve() != source.resolve():
            destination = DOCS_DIR / f"{source.stem}-{counter}{source.suffix}"
            counter += 1

        if destination.resolve() != source.resolve():
            shutil.copy2(source, destination)

        extracted_text = self._extract_text(destination)
        text_path = DOCS_DIR / f"{destination.name}.txtcache"
        text_path.write_text(extracted_text)

        record = self._document_record(destination, extracted_text)
        self._upsert_document(record)
        return json.dumps({"ok": True, "document": record})

    @Slot(result=str)
    def get_documents(self):
        return json.dumps(self._load_docs_index())

    @Slot(str, result=str)
    def pick_cover_image(self, document_name):
        selected, _ = QFileDialog.getOpenFileName(
            None,
            "Choose Cover Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.gif);;All Files (*)",
        )
        if not selected:
            return json.dumps({"ok": False, "cancelled": True})

        source = Path(selected)
        covers_dir = DOCS_DIR / "covers"
        covers_dir.mkdir(parents=True, exist_ok=True)
        destination = covers_dir / f"{Path(document_name).stem}{source.suffix.lower()}"
        shutil.copy2(source, destination)

        record = self._update_document(document_name, {"cover": str(destination)})
        if not record:
            return json.dumps({"ok": False, "error": "Document not found."})

        return json.dumps({"ok": True, "document": record})

    @Slot(str, str)
    def ask_document(self, document_name, question):
        docs = self._load_docs_index()
        record = next((doc for doc in docs if doc["name"] == document_name), None)
        if not record:
            self.chat_error.emit("Document not found.")
            self.chat_done.emit()
            return

        cache_path = DOCS_DIR / f"{document_name}.txtcache"
        context = cache_path.read_text(errors="ignore") if cache_path.exists() else ""
        if not context.strip():
            self.chat_error.emit("No extractable text found. Install pypdf for PDF support.")
            self.chat_done.emit()
            return

        clipped_context = context[:18000]
        prompt = (
            "You are a senior developer peer. Be concise. Explain things clearly. "
            "Use the document context below to answer. If the answer is in the document, "
            "cite the chapter or section when possible. If it is not in the provided text, say so.\n\n"
            f"Document: {document_name}\n\n"
            f"Context:\n{clipped_context}\n\n"
            f"Question: {question}\n"
        )
        self._stream_prompt(prompt)

    @Slot(result=str)
    def get_todos(self):
        if TODOS_FILE.exists():
            return TODOS_FILE.read_text()
        return "[]"
