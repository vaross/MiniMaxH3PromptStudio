import base64
import json
import os
import shutil
import sys
import time
import uuid
from urllib.parse import urlencode
from datetime import datetime, timedelta
from pathlib import Path

import requests
from PIL import Image
from PySide6.QtCore import QObject, QSize, QThread, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QLineEdit,
    QSplitter,
)


OLLAMA_URL = "http://localhost:11434"
OLLAMA_URL_CLOUD = os.getenv("MODAL_OLLAMA_URL", "https://vilchesdiaz-alvaro--agente-minimax-h3-fastapi-app.modal.run")
COMFYUI_MODAL_URL = os.getenv("COMFYUI_MODAL_URL", "https://vilchesdiaz-alvaro--comfyui-minimax-ui.modal.run")
OLLAMA_TIMEOUT_NORMAL = 600  # 10 minutos
OLLAMA_TIMEOUT_HEAVY = 1800  # 30 minutos
HISTORY_MAX_ENTRIES = 200


def get_resource_path(filename):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / filename


def get_workflow_paths():
    workflows_dir = get_resource_path("workflows")
    return sorted(workflows_dir.glob("*.json"), key=lambda path: path.name.lower())


def get_workflow_node_ids(workflow):
    required_types = {
        "prompt": "PrimitiveStringMultiline",
        "media": "MiniMaxH3MediaLoader",
        "duration": "PrimitiveFloat",
        "loras": "Power Lora Loader (rgthree)",
        "output": "VHS_VideoCombine",
    }
    node_ids = {}
    for key, class_type in required_types.items():
        node_id = next((
            node_id
            for node_id, node in workflow.items()
            if node.get("class_type") == class_type
            and (key != "output" or node.get("inputs", {}).get("save_output"))
        ), None)
        if node_id is None:
            if key == "output":
                raise ValueError("El workflow no tiene una salida de vídeo persistente activada.")
            raise ValueError(f"Falta el nodo requerido: {class_type}.")
        node_ids[key] = node_id
    return node_ids


def get_minimax_history_path():
    base = os.getenv("APPDATA") or str(Path.home())
    folder = Path(base) / "MiniMaxPromptStudio"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "minimax_history.json"


def get_minimax_history_images_dir():
    base = os.getenv("APPDATA") or str(Path.home())
    folder = Path(base) / "MiniMaxPromptStudio" / "history_images"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_minimax_history():
    path = get_minimax_history_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_minimax_history(entries):
    path = get_minimax_history_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_comfyui_loras_path():
    base = os.getenv("APPDATA") or str(Path.home())
    folder = Path(base) / "MiniMaxPromptStudio"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "comfyui_loras.json"


def get_comfyui_videos_dir():
    downloads_dir = Path.home() / "Downloads"
    folder = downloads_dir / "MiniMaxPromptStudio"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_comfyui_loras():
    path = get_comfyui_loras_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            loras = json.load(f)
        return loras if isinstance(loras, list) and all(isinstance(name, str) for name in loras) else []
    except Exception:
        return []


def save_comfyui_loras(loras):
    try:
        with open(get_comfyui_loras_path(), "w", encoding="utf-8") as f:
            json.dump(loras, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def format_timestamp_european(ts_iso):
    try:
        dt = datetime.fromisoformat(ts_iso)
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return ts_iso


def history_day_label(day):
    today = datetime.now().date()
    if day == today:
        return "Hoy"
    if day == today - timedelta(days=1):
        return "Ayer"
    return day.strftime("%d/%m/%Y")

CSS = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #eef7ff, stop:0.4 #fdf2ff, stop:1 #f3f6ff);
    color: #111827;
}

QWidget {
    color: #111827;
    font-family: "Segoe UI";
}

QTabWidget::pane {
    border: 1px solid #E2E8F0;
    background: transparent;
    border-radius: 18px;
}

QTabBar::tab {
    background: #E5ECFF;
    color: #334155;
    border: 1px solid #D7E5FF;
    border-bottom: none;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    padding: 10px 18px;
    margin-right: 6px;
    font-weight: 700;
}

QTabBar::tab:selected {
    background: #FFFFFF;
    color: #0F172A;
}

QFrame#card {
    background: rgba(255,255,255,0.94);
    border: 1px solid #DDEBFF;
    border-radius: 18px;
}

QFrame#panel {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f8fbff, stop:1 #f3f0ff);
    border: 1px dashed #B9CFFF;
    border-radius: 16px;
}

QFrame#drop-zone {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #edf7ff, stop:1 #f4f0ff);
    border: 2px dashed #8AB4FF;
    border-radius: 18px;
}

QLabel#section-title {
    color: #0F172A;
    font-size: 14px;
    font-weight: 700;
}

QLabel#preview-empty {
    color: #64748B;
    font-size: 12px;
    font-weight: 600;
}

QPushButton {
    background: #EEF4FF;
    color: #0F172A;
    border: 1px solid #D9E5FF;
    border-radius: 10px;
    padding: 8px 16px;
    font-weight: 600;
}

QPushButton:hover {
    background: #E1EBFF;
}

QPushButton:pressed {
    background: #D4E2FF;
}

QPushButton#primary-button {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff8a65, stop:0.45 #ff6b6b, stop:1 #7c4dff);
    color: #FFFFFF;
    border: none;
}

QPushButton#primary-button:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff7c52, stop:0.45 #ff5d5d, stop:1 #6d42f2);
}

QPushButton#danger-button {
    background: #fff1f2;
    color: #be123c;
    border: 1px solid #fecdd3;
}

QPushButton#danger-button:hover {
    background: #ffe4e6;
}

QComboBox, QPlainTextEdit, QTextEdit {
    background: #FFFFFF;
    border: 1px solid #D9E3FF;
    border-radius: 12px;
    padding: 8px 10px;
    color: #111827;
    selection-background-color: #BFDBFE;
}

QComboBox::drop-down {
    border: none;
}

QComboBox {
    min-height: 36px;
}

QRadioButton {
    spacing: 8px;
    color: #1F2937;
}

QScrollArea {
    border: none;
    background: transparent;
}

QLabel#drop-title {
    color: #4F46E5;
    font-weight: 700;
    font-size: 13px;
}

QPushButton#accordion-header {
    background: #EEF4FF;
    border: 1px solid #D9E5FF;
    border-radius: 10px;
    text-align: left;
    padding: 8px 12px;
    font-weight: 700;
    color: #1E293B;
}

QPushButton#accordion-header:hover {
    background: #E1EBFF;
}

QFrame#history-entry {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
}

QFrame#history-entry:hover {
    background: #F8FAFF;
    border: 1px solid #C7D9FF;
}

QLabel#history-timestamp {
    color: #6366F1;
    font-size: 11px;
    font-weight: 700;
}

QLabel#history-preview {
    color: #1F2937;
    font-size: 12px;
}

QPushButton#favorite-button {
    background: transparent;
    border: none;
    color: #F59E0B;
    font-size: 15px;
    padding: 0px;
}

QPushButton#favorite-button:hover {
    background: #FFF7E6;
    border-radius: 8px;
}
"""


class ImageDropZone(QFrame):
    dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("drop-zone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path and os.path.isfile(file_path):
                paths.append(file_path)
        if paths:
            self.dropped.emit(paths)
            event.acceptProposedAction()


class GalleryImageTile(QWidget):
    """Single thumbnail tile used by the image gallery, with no filename shown."""

    removed = Signal(str)

    TILE_SIZE = (112, 96)

    def __init__(self, path, pixmap, parent=None):
        super().__init__(parent)
        self.path = path
        width, height = self.TILE_SIZE
        self.setFixedSize(width, height)

        self.thumb = QLabel(self)
        self.thumb.setGeometry(0, 0, width, height)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setPixmap(pixmap)
        self.thumb.setStyleSheet(
            "border: 1px solid #dfe8ff; border-radius: 10px; background: #f8fbff;"
        )

        self.remove_btn = QPushButton("X", self)
        self.remove_btn.setObjectName("danger-button")
        self.remove_btn.setFixedSize(20, 20)
        self.remove_btn.move(width - 22, 2)
        self.remove_btn.setStyleSheet(
            "QPushButton { padding: 0px; font-size: 10px; font-weight: 700; border-radius: 10px; }"
        )
        self.remove_btn.setCursor(Qt.PointingHandCursor)
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self.path))

    def sizeHint(self):
        return QSize(*self.TILE_SIZE)


class ReorderableImageList(QListWidget):
    """Gallery-style image preview grid that accepts dropped files and supports drag-to-reorder."""

    filesDropped = Signal(list)
    orderChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("drop-zone")
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setViewMode(QListWidget.IconMode)
        self.setMovement(QListWidget.Snap)
        self.setResizeMode(QListWidget.Adjust)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setGridSize(QSize(122, 106))
        self.setSpacing(6)
        self.setMinimumHeight(150)
        self.setMaximumHeight(320)
        self.setFrameShape(QFrame.NoFrame)
        self.model().rowsMoved.connect(lambda *_: self.orderChanged.emit())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path and os.path.isfile(file_path):
                    paths.append(file_path)
            if paths:
                self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class ReorderableFileList(QListWidget):
    filesDropped = Signal(list)
    orderChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMinimumHeight(120)
        self.model().rowsMoved.connect(lambda *_: self.orderChanged.emit())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
            if paths:
                self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class OllamaWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    chunk = Signal(str)
    status = Signal(str)
    stopped = Signal()

    def __init__(self, timeout=OLLAMA_TIMEOUT_NORMAL, url=OLLAMA_URL, is_cloud=False):
        super().__init__()
        self.stop_requested = False
        self.response = None
        self.timeout = timeout
        self.url = url
        self.is_cloud = is_cloud

    def request_stop(self):
        self.stop_requested = True
        if self.response:
            self.response.close()

    @Slot(str, str, object)
    def run(self, model_name, prompt, image_paths):
        try:
            image_paths = image_paths or []
            images = []
            if image_paths:
                self.status.emit(f"Codificando {len(image_paths)} imagen(es)...")
                print(f"[DEBUG] Encoding {len(image_paths)} images")
            for image_path in image_paths:
                with open(image_path, "rb") as f:
                    images.append(base64.b64encode(f.read()).decode("utf-8"))

            if self.is_cloud:
                self._run_cloud(model_name, prompt, images)
            else:
                self._run_local(model_name, prompt, images)
        except Exception as exc:
            print(f"[DEBUG] Exception: {exc}")
            if self.stop_requested:
                self.stopped.emit()
            else:
                self.failed.emit(str(exc))

    def _run_local(self, model_name, prompt, images):
        payload = {
            "model": model_name,
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": images,
            }],
            "stream": True,
            # -1 = sin límite de tokens de salida, evita que Ollama corte respuestas largas
            "options": {
                "num_predict": -1,
                "num_ctx": 32768,
            },
        }
        self.status.emit(f"Conectando con el modelo '{model_name}'...")
        print(f"[DEBUG] Connecting to {self.url}/api/chat, model: {model_name}, timeout: {self.timeout}s")
        self.response = requests.post(
            f"{self.url}/api/chat", json=payload, timeout=self.timeout, stream=True
        )
        self.response.raise_for_status()
        self.status.emit("Generando respuesta...")
        print("[DEBUG] Generating response...")
        full_text = ""
        chunk_count = 0
        for line in self.response.iter_lines(decode_unicode=True):
            if self.stop_requested:
                print("[DEBUG] Stop requested")
                self.stopped.emit()
                return
            if not line:
                continue
            try:
                body = json.loads(line)
            except json.JSONDecodeError:
                print(f"[DEBUG] Invalid JSON line: {line}")
                continue
            if body.get("error"):
                raise ValueError(body["error"])
            delta = body.get("message", {}).get("content", "")
            if delta:
                full_text += delta
                chunk_count += 1
                print(f"[DEBUG] Chunk {chunk_count}: {len(delta)} chars")
                self.chunk.emit(delta)
            if body.get("done"):
                break
        if not full_text:
            raise ValueError("La respuesta de Ollama no tiene el formato esperado.")
        print(f"[DEBUG] Completed. Total: {len(full_text)} chars")
        self.finished.emit(full_text.strip())

    def _run_cloud(self, model_name, prompt, images):
        payload = {
            "prompt": prompt,
            "images": images,
            "options": {
                "num_predict": -1,
                "num_ctx": 32768,
            },
        }
        self.status.emit(f"Conectando con el modelo '{model_name}' en la nube...")
        print(f"[DEBUG] Connecting to {self.url}/generar, model: {model_name}, timeout: {self.timeout}s")
        self.response = requests.post(
            f"{self.url}/generar", json=payload, timeout=self.timeout, stream=True
        )
        self.response.raise_for_status()
        self.status.emit("Generando respuesta...")
        print("[DEBUG] Generating response from cloud...")

        raw_parts = []
        for chunk in self.response.iter_content(chunk_size=4096, decode_unicode=True):
            if self.stop_requested:
                print("[DEBUG] Stop requested")
                self.stopped.emit()
                return
            if chunk:
                raw_parts.append(chunk)
        raw_text = "".join(raw_parts)

        try:
            result = json.loads(raw_text)
            if isinstance(result, dict):
                full_text = result.get("response", result.get("text", str(result)))
                done_reason = result.get("done_reason")
                eval_count = result.get("eval_count")
                if done_reason:
                    self.status.emit(
                        f"La nube finalizó por: {done_reason}"
                        + (f" ({eval_count} tokens generados)." if eval_count is not None else ".")
                    )
            else:
                full_text = str(result)
        except json.JSONDecodeError:
            full_text = raw_text

        if not full_text:
            raise ValueError("La respuesta de la nube no tiene el formato esperado.")

        print(f"[DEBUG] Completed. Total: {len(full_text)} chars")
        self.chunk.emit(full_text)
        self.finished.emit(full_text.strip())


class CollapsibleSection(QWidget):
    """Accordion-style section with a toggleable header used to group history by day."""

    def __init__(self, title, expanded=True, parent=None):
        super().__init__(parent)
        self._title = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toggle_btn = QPushButton()
        self.toggle_btn.setObjectName("accordion-header")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(expanded)
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self.toggle_btn)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(6, 6, 6, 10)
        self.content_layout.setSpacing(6)
        self.content.setVisible(expanded)
        layout.addWidget(self.content)

        self._update_header_text()

    def _update_header_text(self):
        arrow = "▾" if self.toggle_btn.isChecked() else "▸"
        self.toggle_btn.setText(f"{arrow}  {self._title}")

    def _on_toggle(self):
        expanded = self.toggle_btn.isChecked()
        self.content.setVisible(expanded)
        self._update_header_text()

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)


class HistoryEntryWidget(QFrame):
    """Single row inside the history accordion, with favorite and delete actions."""

    clicked = Signal(str)
    deleteRequested = Signal(str)
    favoriteToggled = Signal(str, bool)

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry_id = entry.get("id")
        self._favorite = bool(entry.get("favorite", False))
        self.setObjectName("history-entry")
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(8)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        timestamp_label = QLabel(format_timestamp_european(entry.get("timestamp", "")))
        timestamp_label.setObjectName("history-timestamp")
        text_col.addWidget(timestamp_label)

        preview = entry.get("input", "").strip().replace("\n", " ")
        if len(preview) > 60:
            preview = preview[:60] + "…"
        if not preview:
            preview = "(sin texto de entrada)"
        image_count = len(entry.get("images", []))
        if image_count:
            preview += f"  [{image_count} img]"
        preview_label = QLabel(preview)
        preview_label.setWordWrap(True)
        preview_label.setObjectName("history-preview")
        text_col.addWidget(preview_label)

        layout.addLayout(text_col, 1)

        self.fav_btn = QPushButton("★" if self._favorite else "☆")
        self.fav_btn.setObjectName("favorite-button")
        self.fav_btn.setFixedWidth(30)
        self.fav_btn.setCursor(Qt.PointingHandCursor)
        self.fav_btn.clicked.connect(self._on_favorite_clicked)
        layout.addWidget(self.fav_btn)

        del_btn = QPushButton("X")
        del_btn.setObjectName("danger-button")
        del_btn.setFixedSize(30, 30)
        del_btn.setStyleSheet(
            "QPushButton { padding: 0px; font-size: 12px; font-weight: 700; }"
        )
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.deleteRequested.emit(self.entry_id))
        layout.addWidget(del_btn)

    def _on_favorite_clicked(self):
        self._favorite = not self._favorite
        self.fav_btn.setText("★" if self._favorite else "☆")
        self.favoriteToggled.emit(self.entry_id, self._favorite)

    def mousePressEvent(self, event):
        self.clicked.emit(self.entry_id)
        super().mousePressEvent(event)


class ComfyUICatalogWorker(QObject):
    finished = Signal(str, list)
    failed = Signal(str)

    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url.rstrip("/")

    @Slot()
    def run(self):
        try:
            stats = requests.get(f"{self.base_url}/system_stats", timeout=120)
            stats.raise_for_status()
            response = requests.get(f"{self.base_url}/models/loras", timeout=120)
            response.raise_for_status()
            loras = response.json()
            if not isinstance(loras, list) or not all(isinstance(name, str) for name in loras):
                raise ValueError("ComfyUI devolvió un catálogo de LoRAs no válido.")
            self.finished.emit(self.base_url, sorted(loras, key=str.lower))
        except Exception as exc:
            self.failed.emit(str(exc))


class ComfyUIRenderWorker(QObject):
    status = Signal(str)
    elapsed = Signal(int)
    queued = Signal(str)
    completed = Signal(str, str)
    failed = Signal(str)

    def __init__(self, base_url, workflow_path, prompt, duration, image_paths, audio_paths, loras):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.workflow_path = workflow_path
        self.prompt = prompt
        self.duration = duration
        self.image_paths = image_paths
        self.audio_paths = audio_paths
        self.loras = loras

    def _upload_file(self, path, upload_id):
        self.status.emit(f"Subiendo {Path(path).name}...")
        with open(path, "rb") as file_handle:
            response = requests.post(
                f"{self.base_url}/upload/image",
                files={"image": (f"{upload_id}_{Path(path).name}", file_handle)},
                data={"overwrite": "true"},
                timeout=600,
            )
        response.raise_for_status()
        data = response.json()
        name = data.get("name")
        subfolder = data.get("subfolder", "")
        if not name:
            raise ValueError(f"ComfyUI no confirmó la carga de {Path(path).name}.")
        return f"{subfolder}/{name}".lstrip("/")

    def _download_video(self, video_url, filename):
        suffix = Path(filename).suffix or ".mp4"
        timestamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        destination = get_comfyui_videos_dir() / f"MMH3 - {timestamp}{suffix}"
        stem = destination.stem
        counter = 1
        while destination.exists():
            destination = destination.with_name(f"{stem}_{counter}{suffix}")
            counter += 1

        self.status.emit(f"Descargando {destination.name}...")
        with requests.get(video_url, stream=True, timeout=600) as response:
            response.raise_for_status()
            with open(destination, "wb") as file_handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_handle.write(chunk)
        return str(destination)

    @Slot()
    def run(self):
        try:
            with open(self.workflow_path, "r", encoding="utf-8") as file_handle:
                workflow = json.load(file_handle)
            node_ids = get_workflow_node_ids(workflow)

            upload_id = uuid.uuid4().hex
            media = []
            for path in self.image_paths:
                uploaded_path = self._upload_file(path, upload_id)
                with Image.open(path) as image:
                    width, height = image.size
                media.append({
                    "kind": "picture",
                    "file": f"{uploaded_path} [input]",
                    "name": Path(path).name,
                    "duration": None,
                    "width": width,
                    "height": height,
                    "has_audio": False,
                    "audio_mode": "off",
                })
            for path in self.audio_paths:
                uploaded_path = self._upload_file(path, upload_id)
                media.append({
                    "kind": "audio",
                    "file": f"{uploaded_path} [input]",
                    "name": Path(path).name,
                    "duration": None,
                    "width": None,
                    "height": None,
                    "has_audio": True,
                    "audio_mode": "off",
                })

            workflow[node_ids["media"]]["inputs"]["media_state"] = json.dumps(media, ensure_ascii=False)
            workflow[node_ids["prompt"]]["inputs"]["value"] = self.prompt
            workflow[node_ids["duration"]]["inputs"]["value"] = self.duration
            lora_inputs = workflow[node_ids["loras"]]["inputs"]
            for key in list(lora_inputs):
                if key.startswith("lora_"):
                    del lora_inputs[key]
            for index, (name, weight) in enumerate(self.loras, start=1):
                lora_inputs[f"lora_{index}"] = {"on": True, "lora": name, "strength": weight}

            self.status.emit("Enviando workflow a ComfyUI...")
            response = requests.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow, "client_id": upload_id},
                timeout=120,
            )
            response.raise_for_status()
            prompt_id = response.json().get("prompt_id")
            if not prompt_id:
                raise ValueError("ComfyUI no devolvió el identificador del trabajo.")
            self.queued.emit(prompt_id)
            self._wait_for_result(prompt_id)
        except Exception as exc:
            self.failed.emit(str(exc))

    def _wait_for_result(self, prompt_id):
        self.status.emit("Trabajo en cola de ComfyUI...")
        generation_started = False
        generation_start_time = None
        while True:
            response = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=120)
            response.raise_for_status()
            result = response.json().get(prompt_id)
            if result:
                status = result.get("status", {})
                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    raise ValueError(f"ComfyUI no pudo generar el vídeo: {messages}")
                for output in result.get("outputs", {}).values():
                    for file_info in output.get("gifs", []) + output.get("images", []):
                        filename = file_info.get("filename")
                        if filename:
                            query = urlencode({
                                "filename": filename,
                                "subfolder": file_info.get("subfolder", ""),
                                "type": file_info.get("type", "output"),
                            })
                            video_url = f"{self.base_url}/view?{query}"
                            video_path = self._download_video(video_url, filename)
                            self.completed.emit(video_url, video_path)
                            return
                raise ValueError("ComfyUI completó el trabajo, pero no devolvió un archivo de vídeo.")
            if not generation_started:
                generation_started = True
                generation_start_time = time.monotonic()
                self.status.emit("Generando vídeo en ComfyUI...")
            self.elapsed.emit(int(time.monotonic() - generation_start_time))
            time.sleep(1)


class ModernApp(QMainWindow):
    start_ollama_task = Signal(str, str, object)

    def __init__(self):
        super().__init__()
        self.selected_minimax_images = []
        self.selected_modal_images = []
        self.selected_vision_image = ""
        self.selected_modal_audios = []
        self.minimax_history = load_minimax_history()
        self.setWindowTitle("MiniMax + Vision Studio")
        self.resize(1400, 900)
        self.setMinimumSize(1024, 768)
        self.setStyleSheet(CSS)
        self._set_window_icon()

        self._active_task = None
        self.stop_button_minimax = None
        self.stop_button_vision = None
        self.comfyui_catalog_thread = None
        self.comfyui_catalog_worker = None
        self.comfyui_render_thread = None
        self.comfyui_render_worker = None

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_minimax_tab(), "MiniMax H3")
        self.tabs.addTab(self._build_vision_tab(), "Descripción visual")
        self.tabs.addTab(self._build_comfyui_modal_tab(), "ComfyUI Modal")
        self.setCentralWidget(self.tabs)

        self.current_busy_text = ""
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_index = 0
        self.busy_spinner_label = QLabel("")
        self.busy_spinner_label.setVisible(False)
        self.busy_spinner_label.setStyleSheet("QLabel { color: #7c3aed; font-weight: 700; font-size: 12px; }")
        self.statusBar().addPermanentWidget(self.busy_spinner_label)
        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self._animate_spinner)
        self.statusBar().showMessage("Comprobando conexión con Ollama...")
        QTimer.singleShot(250, self.check_connection)

    def _set_window_icon(self):
        icon_path = Path(__file__).with_name("app_icon.ico")
        if icon_path.exists():
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(icon_path)))

    def _build_minimax_tab(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)

        left_card = QFrame()
        left_card.setObjectName("card")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(12)

        label = QLabel("Texto de entrada")
        label.setObjectName("section-title")
        left_layout.addWidget(label)

        self.minimax_input = QPlainTextEdit()
        self.minimax_input.setPlaceholderText("Describe el objetivo, contexto, tono y restricciones del prompt...")
        self.minimax_input.setMinimumHeight(220)
        left_layout.addWidget(self.minimax_input, 1)

        model_row = QHBoxLayout()
        model_row.setSpacing(12)
        model_label = QLabel("Modelo Ollama")
        model_label.setObjectName("section-title")
        model_row.addWidget(model_label)
        model_row.addStretch()
        left_layout.addLayout(model_row)

        self.minimax_model = QComboBox()
        self.minimax_model.addItems(["agente-minimax", "agente-minimax-lite", "agente-minimax-cloud"])
        left_layout.addWidget(self.minimax_model)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        btn_images = QPushButton("Cargar imágenes")
        btn_images.clicked.connect(self.select_minimax_images)
        btn_clear = QPushButton("Eliminar todo")
        btn_clear.setObjectName("danger-button")
        btn_clear.clicked.connect(self.clear_minimax_images)
        btn_generate = QPushButton("Generar prompt")
        btn_generate.setObjectName("primary-button")
        btn_generate.clicked.connect(self.generate_minimax_prompt)
        self.stop_button_minimax = QPushButton("Parar")
        self.stop_button_minimax.setObjectName("danger-button")
        self.stop_button_minimax.setEnabled(False)
        self.stop_button_minimax.clicked.connect(self.stop_execution)

        actions.addWidget(btn_images)
        actions.addWidget(btn_clear)
        actions.addStretch()
        actions.addWidget(btn_generate)
        actions.addWidget(self.stop_button_minimax)
        left_layout.addLayout(actions)

        log_title = QLabel("Registro en tiempo real")
        log_title.setObjectName("section-title")
        left_layout.addWidget(log_title)

        self.minimax_log = QPlainTextEdit()
        self.minimax_log.setReadOnly(True)
        self.minimax_log.setPlaceholderText("Aquí verás el progreso de la generación...")
        self.minimax_log.setMaximumHeight(160)
        self.minimax_log.setStyleSheet("QPlainTextEdit { font-family: Consolas, monospace; font-size: 11px; }")
        left_layout.addWidget(self.minimax_log)

        right_card = QFrame()
        right_card.setObjectName("card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(18, 18, 18, 18)
        right_layout.setSpacing(12)

        preview_title = QLabel("Vista previa de imágenes")
        preview_title.setObjectName("section-title")
        right_layout.addWidget(preview_title)

        preview_panel = ReorderableImageList(self)
        preview_panel.filesDropped.connect(self.add_minimax_images)
        preview_panel.orderChanged.connect(self._sync_minimax_image_order)
        self.minimax_preview_list = preview_panel
        self._render_minimax_preview_empty()
        right_layout.addWidget(preview_panel, 0)

        output_title = QLabel("Prompt generado")
        output_title.setObjectName("section-title")
        right_layout.addWidget(output_title)

        self.minimax_output = QPlainTextEdit()
        self.minimax_output.setPlaceholderText("Tu prompt final aparecerá aquí...")
        self.minimax_output.setMinimumHeight(200)
        right_layout.addWidget(self.minimax_output, 1)

        copy_row = QHBoxLayout()
        copy_row.setContentsMargins(0, 6, 0, 0)
        copy_row.addStretch()
        btn_send_to_modal = QPushButton("Enviar a ComfyUI Modal")
        btn_send_to_modal.clicked.connect(self.send_minimax_to_comfyui)
        copy_row.addWidget(btn_send_to_modal)
        btn_copy = QPushButton("Copiar todo")
        btn_copy.clicked.connect(self.copy_minimax_output)
        copy_row.addWidget(btn_copy)
        right_layout.addLayout(copy_row, 0)

        history_card = QFrame()
        history_card.setObjectName("card")
        history_layout = QVBoxLayout(history_card)
        history_layout.setContentsMargins(18, 18, 18, 18)
        history_layout.setSpacing(12)

        history_title = QLabel("Historial de prompts")
        history_title.setObjectName("section-title")
        history_layout.addWidget(history_title)

        history_scroll = QScrollArea()
        history_scroll.setWidgetResizable(True)
        history_scroll.setFrameShape(QFrame.NoFrame)

        self.minimax_history_container = QWidget()
        self.minimax_history_container_layout = QVBoxLayout(self.minimax_history_container)
        self.minimax_history_container_layout.setContentsMargins(0, 0, 4, 0)
        self.minimax_history_container_layout.setSpacing(10)
        self.minimax_history_container_layout.addStretch(1)

        history_scroll.setWidget(self.minimax_history_container)
        history_layout.addWidget(history_scroll, 1)
        self._refresh_minimax_history_list()

        splitter.addWidget(left_card)
        splitter.addWidget(right_card)
        splitter.addWidget(history_card)
        splitter.setSizes([380, 560, 300])
        main_layout.addWidget(splitter, 1)

        return container

    def _build_vision_tab(self):
        container = QWidget()
        outer = QHBoxLayout(container)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        left_card = QFrame()
        left_card.setObjectName("card")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(12)

        model_label = QLabel("Modelo")
        model_label.setObjectName("section-title")
        left_layout.addWidget(model_label)

        self.vision_model = QComboBox()
        self.vision_model.addItems(["Pro", "Lite"])
        left_layout.addWidget(self.vision_model)

        precision_label = QLabel("Precisión")
        precision_label.setObjectName("section-title")
        left_layout.addWidget(precision_label)

        self.precision_group = QButtonGroup(self)
        self.precision_values = {}
        for value, label in [
            ("basica", "Básica"),
            ("equilibrada", "Equilibrada"),
            ("detallada", "Detallada"),
            ("muy_detallada", "Muy detallada"),
        ]:
            radio = QRadioButton(label)
            if value == "equilibrada":
                radio.setChecked(True)
            self.precision_group.addButton(radio)
            self.precision_values[value] = radio
            left_layout.addWidget(radio)

        prompt_label = QLabel("Prompt personalizado")
        prompt_label.setObjectName("section-title")
        left_layout.addWidget(prompt_label)

        self.vision_prompt = QPlainTextEdit()
        self.vision_prompt.setPlaceholderText("Añade instrucciones adicionales para la descripción...")
        self.vision_prompt.setMaximumHeight(140)
        left_layout.addWidget(self.vision_prompt)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        btn_load = QPushButton("Cargar imagen")
        btn_load.clicked.connect(self.select_vision_image)
        btn_generate = QPushButton("Generar descripción")
        btn_generate.setObjectName("primary-button")
        btn_generate.clicked.connect(self.generate_vision_description)
        self.stop_button_vision = QPushButton("Parar")
        self.stop_button_vision.setObjectName("danger-button")
        self.stop_button_vision.setEnabled(False)
        self.stop_button_vision.clicked.connect(self.stop_execution)
        actions.addWidget(btn_load)
        actions.addStretch()
        actions.addWidget(btn_generate)
        actions.addWidget(self.stop_button_vision)
        left_layout.addLayout(actions)

        left_layout.addStretch()
        left_card.setMaximumWidth(380)

        right_card = QFrame()
        right_card.setObjectName("card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(18, 18, 18, 18)
        right_layout.setSpacing(12)

        preview_title = QLabel("Imagen seleccionada")
        preview_title.setObjectName("section-title")
        right_layout.addWidget(preview_title)

        preview_panel = ImageDropZone(self)
        preview_panel.setObjectName("drop-zone")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        self.vision_preview_label = QLabel("Arrastra una imagen aquí o cárgala desde el botón")
        self.vision_preview_label.setObjectName("preview-empty")
        self.vision_preview_label.setAlignment(Qt.AlignCenter)
        self.vision_preview_label.setMinimumHeight(300)
        self.vision_preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.vision_preview_label.setWordWrap(True)
        preview_layout.addWidget(self.vision_preview_label)
        preview_panel.dropped.connect(self.handle_vision_drop)
        right_layout.addWidget(preview_panel, 1)

        output_title = QLabel("Descripción generada")
        output_title.setObjectName("section-title")
        right_layout.addWidget(output_title)

        self.vision_output = QPlainTextEdit()
        self.vision_output.setPlaceholderText("La descripción saldrá aquí...")
        self.vision_output.setMinimumHeight(320)
        right_layout.addWidget(self.vision_output, 1)

        copy_row = QHBoxLayout()
        copy_row.addStretch()
        btn_copy = QPushButton("Copiar descripción")
        btn_copy.clicked.connect(self.copy_vision_output)
        copy_row.addWidget(btn_copy)
        right_layout.addLayout(copy_row)

        outer.addWidget(left_card, 0)
        outer.addWidget(right_card, 1)
        return container

    def _build_comfyui_modal_tab(self):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        settings_card = QFrame()
        settings_card.setObjectName("card")
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(18, 18, 18, 18)
        settings_layout.setSpacing(12)

        endpoint_label = QLabel("Endpoint de ComfyUI")
        endpoint_label.setObjectName("section-title")
        settings_layout.addWidget(endpoint_label)
        self.comfyui_modal_url = QLineEdit(COMFYUI_MODAL_URL)
        self.comfyui_modal_url.setClearButtonEnabled(True)
        settings_layout.addWidget(self.comfyui_modal_url)

        connection_row = QHBoxLayout()
        self.comfyui_connection_label = QLabel("Catálogo no cargado")
        self.comfyui_connection_label.setObjectName("preview-empty")
        self.comfyui_refresh_button = QPushButton("Actualizar LoRAs")
        self.comfyui_refresh_button.clicked.connect(self.refresh_comfyui_loras)
        connection_row.addWidget(self.comfyui_connection_label, 1)
        connection_row.addWidget(self.comfyui_refresh_button)
        settings_layout.addLayout(connection_row)

        prompt_label = QLabel("Prompt para vídeo")
        prompt_label.setObjectName("section-title")
        settings_layout.addWidget(prompt_label)
        self.comfyui_prompt = QPlainTextEdit()
        self.comfyui_prompt.setPlaceholderText("El prompt que se enviará al workflow de ComfyUI...")
        self.comfyui_prompt.setMinimumHeight(260)
        settings_layout.addWidget(self.comfyui_prompt, 1)

        prompt_action = QHBoxLayout()
        use_prompt_button = QPushButton("Usar prompt generado")
        use_prompt_button.clicked.connect(self.use_minimax_prompt_for_comfyui)
        prompt_action.addWidget(use_prompt_button)
        prompt_action.addStretch()
        settings_layout.addLayout(prompt_action)

        workflow_label = QLabel("Workflow")
        workflow_label.setObjectName("section-title")
        settings_layout.addWidget(workflow_label)
        self.comfyui_workflow = QComboBox()
        for workflow_path in get_workflow_paths():
            self.comfyui_workflow.addItem(workflow_path.stem, str(workflow_path))
        self.comfyui_workflow.setEnabled(self.comfyui_workflow.count() > 0)
        settings_layout.addWidget(self.comfyui_workflow)

        duration_label = QLabel("Duración del vídeo")
        duration_label.setObjectName("section-title")
        settings_layout.addWidget(duration_label)
        self.comfyui_duration = QDoubleSpinBox()
        self.comfyui_duration.setRange(5.17, 15.08)
        self.comfyui_duration.setSingleStep(0.01)
        self.comfyui_duration.setValue(10.13)
        self.comfyui_duration.setDecimals(2)
        self.comfyui_duration.setSuffix(" s")
        settings_layout.addWidget(self.comfyui_duration)

        render_row = QHBoxLayout()
        self.comfyui_render_status = QLabel("Listo para preparar un vídeo")
        self.comfyui_render_status.setObjectName("preview-empty")
        self.comfyui_render_button = QPushButton("Generar vídeo")
        self.comfyui_render_button.setObjectName("primary-button")
        self.comfyui_render_button.clicked.connect(self.generate_comfyui_video)
        render_row.addWidget(self.comfyui_render_status, 1)
        render_row.addWidget(self.comfyui_render_button)
        settings_layout.addLayout(render_row)

        lora_card = QFrame()
        lora_card.setObjectName("card")
        lora_layout = QVBoxLayout(lora_card)
        lora_layout.setContentsMargins(18, 18, 18, 18)
        lora_layout.setSpacing(12)

        lora_label = QLabel("LoRAs disponibles en Modal")
        lora_label.setObjectName("section-title")
        lora_layout.addWidget(lora_label)
        self.comfyui_lora_list = QListWidget()
        self.comfyui_lora_list.setAlternatingRowColors(True)
        self.comfyui_lora_list.setMinimumHeight(180)
        self.comfyui_lora_list.setMaximumHeight(300)
        lora_layout.addWidget(self.comfyui_lora_list)
        self.comfyui_lora_controls = {}
        cached_loras = load_comfyui_loras()
        if cached_loras:
            self._populate_comfyui_loras(cached_loras)
            self.comfyui_connection_label.setText(f"Catálogo guardado: {len(cached_loras)} LoRAs")

        image_label = QLabel("Imágenes de referencia")
        image_label.setObjectName("section-title")
        lora_layout.addWidget(image_label)
        self.comfyui_image_list = ReorderableImageList(self)
        self.comfyui_image_list.filesDropped.connect(self.add_modal_images)
        self.comfyui_image_list.orderChanged.connect(self._sync_modal_image_order)
        self.comfyui_image_list.setMinimumHeight(150)
        self.comfyui_image_list.setMaximumHeight(230)
        lora_layout.addWidget(self.comfyui_image_list)
        image_actions = QHBoxLayout()
        add_image_button = QPushButton("Añadir imágenes")
        add_image_button.clicked.connect(self.select_modal_images)
        remove_images_button = QPushButton("Eliminar todas")
        remove_images_button.setObjectName("danger-button")
        remove_images_button.clicked.connect(self.clear_modal_images)
        image_actions.addWidget(add_image_button)
        image_actions.addWidget(remove_images_button)
        lora_layout.addLayout(image_actions)
        self._render_modal_images()

        audio_label = QLabel("Audios de referencia")
        audio_label.setObjectName("section-title")
        lora_layout.addWidget(audio_label)
        self.comfyui_audio_list = ReorderableFileList()
        self.comfyui_audio_list.filesDropped.connect(self.add_modal_audios)
        self.comfyui_audio_list.orderChanged.connect(self._sync_modal_audio_order)
        self.comfyui_audio_list.setMaximumHeight(130)
        lora_layout.addWidget(self.comfyui_audio_list)
        audio_row = QHBoxLayout()
        load_audio_button = QPushButton("Cargar audios")
        load_audio_button.clicked.connect(self.select_modal_audios)
        remove_audio_button = QPushButton("Eliminar seleccionado")
        remove_audio_button.setObjectName("danger-button")
        remove_audio_button.clicked.connect(self.remove_selected_modal_audio)
        audio_row.addWidget(load_audio_button)
        audio_row.addWidget(remove_audio_button)
        lora_layout.addLayout(audio_row)

        result_card = QFrame()
        result_card.setObjectName("card")
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(18, 18, 18, 18)
        result_layout.setSpacing(12)
        result_title = QLabel("Vídeo generado")
        result_title.setObjectName("section-title")
        result_layout.addWidget(result_title)
        self.comfyui_video_widget = QVideoWidget()
        self.comfyui_video_widget.setMinimumSize(280, 220)
        result_layout.addWidget(self.comfyui_video_widget, 1)
        self.comfyui_audio_output = QAudioOutput(self)
        self.comfyui_media_player = QMediaPlayer(self)
        self.comfyui_media_player.setAudioOutput(self.comfyui_audio_output)
        self.comfyui_media_player.setVideoOutput(self.comfyui_video_widget)
        self.comfyui_video_url = ""
        self.comfyui_video_path = ""
        video_actions = QHBoxLayout()
        self.comfyui_open_video_button = QPushButton("Abrir vídeo")
        self.comfyui_open_video_button.setEnabled(False)
        self.comfyui_open_video_button.clicked.connect(self.open_comfyui_video)
        video_actions.addWidget(self.comfyui_open_video_button)
        open_downloads_button = QPushButton("Abrir descargas")
        open_downloads_button.clicked.connect(self.open_comfyui_downloads)
        video_actions.addWidget(open_downloads_button)
        video_actions.addStretch()
        result_layout.addLayout(video_actions)
        log_label = QLabel("Registro de vídeo")
        log_label.setObjectName("section-title")
        result_layout.addWidget(log_label)
        self.comfyui_log = QPlainTextEdit()
        self.comfyui_log.setReadOnly(True)
        self.comfyui_log.setPlaceholderText("Aquí aparecerán las subidas, la cola y el render de ComfyUI...")
        self.comfyui_log.setMaximumHeight(180)
        self.comfyui_log.setStyleSheet("QPlainTextEdit { font-family: Consolas, monospace; font-size: 11px; }")
        result_layout.addWidget(self.comfyui_log)

        lora_card.setMinimumWidth(360)
        layout.addWidget(settings_card, 30)
        layout.addWidget(lora_card, 35)
        layout.addWidget(result_card, 35)
        return container

    def _render_minimax_preview_empty(self):
        self.minimax_preview_list.clear()
        item = QListWidgetItem()
        item.setFlags(Qt.NoItemFlags)
        empty = QLabel("Arrastra imágenes aquí o usa \"Cargar imágenes\"")
        empty.setObjectName("preview-empty")
        empty.setAlignment(Qt.AlignCenter)
        empty.setWordWrap(True)
        item.setSizeHint(empty.sizeHint())
        self.minimax_preview_list.addItem(item)
        self.minimax_preview_list.setItemWidget(item, empty)

    def _render_minimax_preview(self):
        self.minimax_preview_list.clear()

        if not self.selected_minimax_images:
            self._render_minimax_preview_empty()
            return

        for path in self.selected_minimax_images:
            try:
                pixmap = self._pixmap_from_path(path, GalleryImageTile.TILE_SIZE)
            except Exception:
                pixmap = QPixmap()

            tile = GalleryImageTile(path, pixmap)
            tile.removed.connect(self.remove_minimax_image)

            item = QListWidgetItem()
            item.setData(Qt.UserRole, path)
            item.setSizeHint(tile.sizeHint())
            self.minimax_preview_list.addItem(item)
            self.minimax_preview_list.setItemWidget(item, tile)

    def _sync_minimax_image_order(self):
        order = []
        for i in range(self.minimax_preview_list.count()):
            path = self.minimax_preview_list.item(i).data(Qt.UserRole)
            if path:
                order.append(path)
        if order:
            self.selected_minimax_images = order

    def _pixmap_from_path(self, path, size):
        image = Image.open(path).convert("RGBA")
        image.thumbnail(size)
        data = image.tobytes("raw", "RGBA")
        qimage = QImage(data, image.width, image.height, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimage).scaled(size[0], size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _normalize_image_paths(self, paths):
        allowed = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        normalized = []
        seen = set()
        for path in paths:
            if not path:
                continue
            lower = os.path.splitext(path)[1].lower()
            if lower not in allowed:
                continue
            if path not in seen:
                normalized.append(path)
                seen.add(path)
        return normalized

    def add_minimax_images(self, paths):
        valid = self._normalize_image_paths(paths)
        if not valid:
            QMessageBox.warning(self, "Formato no válido", "Solo se aceptan imágenes con formato PNG, JPG, JPEG, BMP o WEBP.")
            return
        current = list(self.selected_minimax_images)
        for path in valid:
            if path not in current:
                current.append(path)
        self.selected_minimax_images = current
        self._render_minimax_preview()

    def select_minimax_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecciona imágenes para el prompt",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not paths:
            return
        self.add_minimax_images(paths)

    def use_minimax_prompt_for_comfyui(self):
        prompt = self.minimax_output.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Sin prompt", "Genera o escribe un prompt antes de enviarlo a ComfyUI.")
            return
        self.comfyui_prompt.setPlainText(prompt)
        self.selected_modal_images = list(self.selected_minimax_images)
        self._render_modal_images()
        self.statusBar().showMessage("Prompt y referencias preparados para ComfyUI Modal.")

    def send_minimax_to_comfyui(self):
        self.use_minimax_prompt_for_comfyui()
        if self.comfyui_prompt.toPlainText().strip():
            self.tabs.setCurrentIndex(2)

    def select_modal_audios(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecciona audios de referencia",
            "",
            "Audios (*.wav *.mp3 *.m4a *.aac *.flac *.ogg)",
        )
        if not paths:
            return
        self.add_modal_audios(paths)

    def add_modal_images(self, paths):
        valid = self._normalize_image_paths(paths)
        if not valid:
            QMessageBox.warning(self, "Formato no válido", "Solo se aceptan imágenes PNG, JPG, JPEG, BMP o WEBP.")
            return
        self.selected_modal_images = list(dict.fromkeys(self.selected_modal_images + valid))
        self._render_modal_images()

    def select_modal_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Añadir imágenes de referencia",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if paths:
            self.add_modal_images(paths)

    def clear_modal_images(self):
        self.selected_modal_images = []
        self._render_modal_images()

    def remove_modal_image(self, path):
        if path in self.selected_modal_images:
            self.selected_modal_images.remove(path)
            self._render_modal_images()

    def _render_modal_images(self):
        if not hasattr(self, "comfyui_image_list"):
            return
        self.comfyui_image_list.clear()
        for path in self.selected_modal_images:
            try:
                pixmap = self._pixmap_from_path(path, GalleryImageTile.TILE_SIZE)
            except Exception:
                pixmap = QPixmap()
            tile = GalleryImageTile(path, pixmap)
            tile.removed.connect(self.remove_modal_image)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, path)
            item.setSizeHint(tile.sizeHint())
            self.comfyui_image_list.addItem(item)
            self.comfyui_image_list.setItemWidget(item, tile)

    def _sync_modal_image_order(self):
        self.selected_modal_images = [
            self.comfyui_image_list.item(index).data(Qt.UserRole)
            for index in range(self.comfyui_image_list.count())
            if self.comfyui_image_list.item(index).data(Qt.UserRole)
        ]

    def add_modal_audios(self, paths):
        allowed = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
        valid = [path for path in paths if os.path.splitext(path)[1].lower() in allowed]
        if not valid:
            QMessageBox.warning(self, "Formato no válido", "Solo se aceptan audios WAV, MP3, M4A, AAC, FLAC u OGG.")
            return
        self.selected_modal_audios = list(dict.fromkeys(self.selected_modal_audios + valid))
        self._render_modal_audios()

    def _render_modal_audios(self):
        self.comfyui_audio_list.clear()
        for path in self.selected_modal_audios:
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.comfyui_audio_list.addItem(item)

    def _sync_modal_audio_order(self):
        self.selected_modal_audios = [
            self.comfyui_audio_list.item(index).data(Qt.UserRole)
            for index in range(self.comfyui_audio_list.count())
        ]

    def remove_selected_modal_audio(self):
        item = self.comfyui_audio_list.currentItem()
        if not item:
            return
        path = item.data(Qt.UserRole)
        if path in self.selected_modal_audios:
            self.selected_modal_audios.remove(path)
        self._render_modal_audios()

    def generate_comfyui_video(self):
        if self.comfyui_render_thread and self.comfyui_render_thread.isRunning():
            return
        base_url = self.comfyui_modal_url.text().strip().rstrip("/")
        prompt = self.comfyui_prompt.toPlainText().strip()
        workflow_path = Path(self.comfyui_workflow.currentData() or "")
        if not base_url.startswith(("https://", "http://")):
            QMessageBox.warning(self, "URL no válida", "Introduce una URL HTTP o HTTPS válida para ComfyUI.")
            return
        if not prompt:
            QMessageBox.warning(self, "Sin prompt", "Genera un prompt en MiniMax H3 o escríbelo en esta pestaña.")
            return
        if not self.selected_modal_images:
            QMessageBox.warning(self, "Sin imágenes", "Añade al menos una imagen de referencia para el workflow.")
            return
        if not workflow_path.is_file():
            QMessageBox.critical(self, "Workflow no encontrado", "Selecciona un workflow API válido.")
            return
        try:
            with open(workflow_path, "r", encoding="utf-8") as file_handle:
                workflow = json.load(file_handle)
            get_workflow_node_ids(workflow)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            QMessageBox.critical(self, "Workflow incompatible", str(exc))
            return

        selected_loras = [
            (name, weight.value())
            for name, (enabled, weight) in self.comfyui_lora_controls.items()
            if enabled.isChecked()
        ]
        self.comfyui_render_button.setEnabled(False)
        self.comfyui_render_status.setText("Preparando archivos...")
        self.comfyui_log.clear()
        self._append_comfyui_log(
            f"Iniciando: {len(self.selected_modal_images)} imágenes, "
            f"{len(self.selected_modal_audios)} audios y {len(selected_loras)} LoRAs."
        )
        self.comfyui_render_thread = QThread(self)
        self.comfyui_render_worker = ComfyUIRenderWorker(
            base_url,
            workflow_path,
            prompt,
            self.comfyui_duration.value(),
            list(self.selected_modal_images),
            list(self.selected_modal_audios),
            selected_loras,
        )
        self.comfyui_render_worker.moveToThread(self.comfyui_render_thread)
        self.comfyui_render_thread.started.connect(self.comfyui_render_worker.run)
        self.comfyui_render_worker.status.connect(self._handle_comfyui_render_status)
        self.comfyui_render_worker.elapsed.connect(self._handle_comfyui_render_elapsed)
        self.comfyui_render_worker.queued.connect(self._handle_comfyui_video_queued)
        self.comfyui_render_worker.completed.connect(self._handle_comfyui_video_completed)
        self.comfyui_render_worker.failed.connect(self._handle_comfyui_video_failed)
        self.comfyui_render_worker.completed.connect(self.comfyui_render_thread.quit)
        self.comfyui_render_worker.failed.connect(self.comfyui_render_thread.quit)
        self.comfyui_render_thread.finished.connect(self.comfyui_render_worker.deleteLater)
        self.comfyui_render_thread.finished.connect(self.comfyui_render_thread.deleteLater)
        self.comfyui_render_thread.start()

    def _handle_comfyui_video_queued(self, prompt_id):
        self.comfyui_render_status.setText(f"Vídeo en cola: {prompt_id}")
        self._append_comfyui_log(f"ComfyUI aceptó el trabajo: {prompt_id}")
        self.statusBar().showMessage(f"ComfyUI aceptó el trabajo {prompt_id}.")

    def _handle_comfyui_render_status(self, message):
        self.comfyui_render_status.setText(message)
        self._append_comfyui_log(message)

    def _handle_comfyui_render_elapsed(self, elapsed_seconds):
        minutes, seconds = divmod(elapsed_seconds, 60)
        self.comfyui_render_status.setText(
            f"Generando vídeo en ComfyUI... {minutes:02d}:{seconds:02d}"
        )

    def _handle_comfyui_video_completed(self, video_url, video_path):
        self.comfyui_video_url = video_url
        self.comfyui_video_path = video_path
        self.comfyui_media_player.setSource(QUrl.fromLocalFile(video_path))
        self.comfyui_media_player.play()
        self.comfyui_open_video_button.setEnabled(True)
        self.comfyui_render_status.setText("Vídeo descargado")
        self.comfyui_render_button.setEnabled(True)
        self._append_comfyui_log(f"Vídeo descargado: {video_path}")
        self.statusBar().showMessage("Vídeo generado y descargado desde ComfyUI Modal.")

    def _handle_comfyui_video_failed(self, error_text):
        self.comfyui_render_status.setText("No se pudo crear el vídeo")
        self.comfyui_render_button.setEnabled(True)
        self._append_comfyui_log(f"ERROR: {error_text}")
        QMessageBox.critical(self, "Error al crear el vídeo", error_text)

    def _append_comfyui_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.comfyui_log.appendPlainText(f"[{timestamp}] {message}")

    def open_comfyui_video(self):
        if self.comfyui_video_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.comfyui_video_path))

    def open_comfyui_downloads(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(get_comfyui_videos_dir())))

    def refresh_comfyui_loras(self):
        if self.comfyui_catalog_thread and self.comfyui_catalog_thread.isRunning():
            return
        base_url = self.comfyui_modal_url.text().strip().rstrip("/")
        if not base_url.startswith(("https://", "http://")):
            QMessageBox.warning(self, "URL no válida", "Introduce una URL HTTP o HTTPS válida para ComfyUI.")
            return

        self.comfyui_refresh_button.setEnabled(False)
        self.comfyui_connection_label.setText("Conectando con Modal...")
        self.comfyui_catalog_thread = QThread(self)
        self.comfyui_catalog_worker = ComfyUICatalogWorker(base_url)
        self.comfyui_catalog_worker.moveToThread(self.comfyui_catalog_thread)
        self.comfyui_catalog_thread.started.connect(self.comfyui_catalog_worker.run)
        self.comfyui_catalog_worker.finished.connect(self._handle_comfyui_loras_loaded)
        self.comfyui_catalog_worker.failed.connect(self._handle_comfyui_loras_failed)
        self.comfyui_catalog_worker.finished.connect(self.comfyui_catalog_thread.quit)
        self.comfyui_catalog_worker.failed.connect(self.comfyui_catalog_thread.quit)
        self.comfyui_catalog_thread.finished.connect(self.comfyui_catalog_worker.deleteLater)
        self.comfyui_catalog_thread.finished.connect(self.comfyui_catalog_thread.deleteLater)
        self.comfyui_catalog_thread.start()

    def _handle_comfyui_loras_loaded(self, base_url, loras):
        save_comfyui_loras(loras)
        self._populate_comfyui_loras(loras)
        self.comfyui_connection_label.setText(f"Conectado: {len(loras)} LoRAs disponibles")
        self.comfyui_refresh_button.setEnabled(True)
        self.statusBar().showMessage(f"ComfyUI Modal conectado en {base_url}.")

    def _populate_comfyui_loras(self, loras):
        self.comfyui_lora_list.clear()
        self.comfyui_lora_controls = {}
        for name in loras:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 4, 8, 4)
            enabled = QCheckBox(name)
            weight = QDoubleSpinBox()
            weight.setRange(-2.0, 2.0)
            weight.setSingleStep(0.05)
            weight.setValue(1.0)
            weight.setDecimals(2)
            weight.setFixedWidth(88)
            row_layout.addWidget(enabled, 1)
            row_layout.addWidget(weight)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self.comfyui_lora_list.addItem(item)
            self.comfyui_lora_list.setItemWidget(item, row)
            self.comfyui_lora_controls[name] = (enabled, weight)

    def _handle_comfyui_loras_failed(self, error_text):
        self.comfyui_connection_label.setText("No se pudo conectar con Modal")
        self.comfyui_refresh_button.setEnabled(True)
        QMessageBox.critical(self, "Error de ComfyUI Modal", error_text)

    def remove_minimax_image(self, path):
        if path in self.selected_minimax_images:
            self.selected_minimax_images.remove(path)
            self._render_minimax_preview()

    def clear_minimax_images(self):
        self.selected_minimax_images = []
        self._render_minimax_preview()

    def handle_vision_drop(self, paths):
        valid = self._normalize_image_paths(paths)
        if not valid:
            QMessageBox.warning(self, "Formato no válido", "Solo se aceptan imágenes PNG, JPG, JPEG, BMP o WEBP.")
            return
        self.set_vision_image(valid[0])

    def set_vision_image(self, path):
        self.selected_vision_image = path
        try:
            pixmap = self._pixmap_from_path(path, (520, 380))
            self.vision_preview_label.setPixmap(pixmap)
            self.vision_preview_label.setText("")
            self.vision_preview_label.setAlignment(Qt.AlignCenter)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo cargar la imagen: {exc}")

    def select_vision_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecciona una imagen para describir",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return
        self.set_vision_image(path)

    def check_connection(self):
        try:
            response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            if response.status_code == 200:
                self.statusBar().showMessage("Conectado con Ollama. Listo para usar.")
            else:
                self.statusBar().showMessage("Ollama responde con un error. Comprueba que el servidor esté activo.")
        except Exception:
            self.statusBar().showMessage("No se pudo conectar con Ollama en http://localhost:11434")

    def _animate_spinner(self):
        if not self.current_busy_text:
            self.busy_spinner_label.setVisible(False)
            return
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)
        self.busy_spinner_label.setText(f"{self.spinner_frames[self.spinner_index]} {self.current_busy_text}")
        self.busy_spinner_label.setVisible(True)

    def _set_busy(self, message, busy):
        self.current_busy_text = message if busy else ""
        self.minimax_input.setEnabled(not busy)
        self.minimax_model.setEnabled(not busy)
        self.minimax_output.setEnabled(not busy)
        self.vision_model.setEnabled(not busy)
        self.vision_prompt.setEnabled(not busy)
        self.vision_output.setEnabled(not busy)
        self.tabs.setEnabled(not busy)
        self.stop_button_minimax.setEnabled(busy)
        self.stop_button_vision.setEnabled(busy)
        if busy:
            self.spinner_timer.start(100)
            self._animate_spinner()
            self.statusBar().showMessage(f"Procesando: {message}")
        else:
            self.spinner_timer.stop()
            self.busy_spinner_label.setVisible(False)
            self.busy_spinner_label.setText("")
            self.statusBar().showMessage("Conectado con Ollama. Listo para usar.")

    def stop_execution(self):
        if self._active_task and len(self._active_task) >= 3:
            target_key, worker_thread, worker = self._active_task[0], self._active_task[1], self._active_task[2]
            if worker and hasattr(worker, 'request_stop'):
                worker.request_stop()
                self.statusBar().showMessage("Deteniendo ejecución...")

    def _get_timeout_for_model(self, model_name):
        heavy_models = ["agente-minimax", "agente-minimax-cloud", "Pro", "orcarouter/Qwen3.8-27B-Uncensored:latest"]
        return OLLAMA_TIMEOUT_HEAVY if model_name in heavy_models else OLLAMA_TIMEOUT_NORMAL

    def _get_url_for_model(self, model_name):
        return OLLAMA_URL_CLOUD if model_name == "agente-minimax-cloud" else OLLAMA_URL

    def _is_cloud_model(self, model_name):
        return model_name == "agente-minimax-cloud"

    def _start_background_task(self, model_name, prompt, image_paths, target_key):
        timeout = self._get_timeout_for_model(model_name)
        url = self._get_url_for_model(model_name)
        is_cloud = self._is_cloud_model(model_name)
        worker_thread = QThread(self)
        worker = OllamaWorker(timeout=timeout, url=url, is_cloud=is_cloud)
        worker.moveToThread(worker_thread)
        self.start_ollama_task.connect(worker.run, Qt.QueuedConnection)
        worker.finished.connect(self._handle_background_result, Qt.QueuedConnection)
        worker.failed.connect(self._handle_background_error, Qt.QueuedConnection)
        worker.chunk.connect(self._handle_background_chunk, Qt.QueuedConnection)
        worker.status.connect(self._handle_background_status, Qt.QueuedConnection)
        worker.stopped.connect(self._handle_execution_stopped, Qt.QueuedConnection)
        worker.finished.connect(worker_thread.quit)
        worker.failed.connect(worker_thread.quit)
        worker.stopped.connect(worker_thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.stopped.connect(worker.deleteLater)
        worker_thread.finished.connect(worker_thread.deleteLater)
        self._active_task = (target_key, worker_thread, worker)
        self._minimax_chunk_chars = 0
        if target_key == "minimax":
            self.minimax_output.setPlainText("")
            self._append_minimax_log(f"Solicitud iniciada con el modelo '{model_name}'.")
        elif target_key == "vision":
            self.vision_output.setPlainText("")
        self._set_busy("Procesando solicitud...", True)
        worker_thread.start()
        self.start_ollama_task.emit(model_name, prompt, image_paths)

    def _append_minimax_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.minimax_log.appendPlainText(f"[{timestamp}] {message}")

    def _handle_background_chunk(self, delta):
        if not self._active_task or not delta:
            return
        target_key = self._active_task[0]
        if target_key == "minimax":
            output_box = self.minimax_output
        elif target_key == "vision":
            output_box = self.vision_output
        else:
            return

        cursor = output_box.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        output_box.setTextCursor(cursor)
        output_box.insertPlainText(delta)
        output_box.ensureCursorVisible()
        QApplication.processEvents()

        if target_key == "minimax":
            self._minimax_chunk_chars += len(delta)

    def _handle_background_status(self, message):
        self.current_busy_text = message
        self.statusBar().showMessage(f"Procesando: {message}")
        if self._active_task and self._active_task[0] == "minimax":
            self._append_minimax_log(message)

    def _handle_background_result(self, result):
        if not self._active_task:
            return
        target_key = self._active_task[0]
        self._set_busy("", False)
        if target_key == "minimax":
            self.minimax_output.setPlainText(result)
            self.statusBar().showMessage("Prompt generado con MiniMax H3.")
            self._append_minimax_log(f"Completado. {len(result)} caracteres generados.")
            self._save_minimax_history_entry(result)
        elif target_key == "vision":
            self.vision_output.setPlainText(result)
            self.statusBar().showMessage("Descripción visual generada.")
        QApplication.beep()
        self._active_task = None

    def _handle_background_error(self, error_text):
        self._set_busy("", False)
        if self._active_task and self._active_task[0] == "minimax":
            QMessageBox.critical(self, "Error al generar el prompt", f"No se pudo generar el prompt:\n{error_text}")
            self.statusBar().showMessage("Error al comunicarse con Ollama.")
            self._append_minimax_log(f"ERROR: {error_text}")
        elif self._active_task and self._active_task[0] == "vision":
            QMessageBox.critical(self, "Error al describir la imagen", f"No se pudo describir la imagen:\n{error_text}")
            self.statusBar().showMessage("Error al comunicarse con el modelo de visión.")
        self._active_task = None

    def _handle_execution_stopped(self):
        self._set_busy("", False)
        if self._active_task:
            target_key = self._active_task[0]
            if target_key == "minimax":
                self._append_minimax_log("Ejecución detenida por el usuario.")
            self.statusBar().showMessage("Ejecución detenida.")
        self._active_task = None

    def _archive_history_images(self, entry_id, image_paths):
        if not image_paths:
            return []
        target_dir = get_minimax_history_images_dir() / entry_id
        saved = []
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            for index, path in enumerate(image_paths):
                if not path or not os.path.exists(path):
                    continue
                ext = os.path.splitext(path)[1] or ".png"
                dest = target_dir / f"img_{index}{ext}"
                shutil.copyfile(path, dest)
                saved.append(str(dest))
        except Exception:
            pass
        return saved

    def _save_minimax_history_entry(self, output_text):
        entry_id = str(uuid.uuid4())
        entry = {
            "id": entry_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "model": self.minimax_model.currentText(),
            "input": self.minimax_input.toPlainText(),
            "output": output_text,
            "images": self._archive_history_images(entry_id, self.selected_minimax_images),
            "favorite": False,
        }
        self.minimax_history.insert(0, entry)
        del self.minimax_history[HISTORY_MAX_ENTRIES:]
        save_minimax_history(self.minimax_history)
        self._refresh_minimax_history_list()

    def _clear_history_container(self):
        layout = self.minimax_history_container_layout
        while layout.count() > 1:
            child = layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

    def _make_history_entry_widget(self, entry):
        widget = HistoryEntryWidget(entry)
        widget.clicked.connect(self._load_minimax_history_item)
        widget.deleteRequested.connect(self._delete_minimax_history_entry)
        widget.favoriteToggled.connect(self._toggle_minimax_history_favorite)
        return widget

    def _refresh_minimax_history_list(self):
        self._clear_history_container()
        layout = self.minimax_history_container_layout

        if not self.minimax_history:
            empty = QLabel("Aún no hay prompts en el historial.")
            empty.setObjectName("preview-empty")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            layout.insertWidget(layout.count() - 1, empty)
            return

        favorites = [e for e in self.minimax_history if e.get("favorite")]
        if favorites:
            fav_section = CollapsibleSection("★ Favoritos", expanded=True)
            for entry in favorites:
                fav_section.add_widget(self._make_history_entry_widget(entry))
            layout.insertWidget(layout.count() - 1, fav_section)

        groups = []
        groups_by_day = {}
        for entry in self.minimax_history:
            try:
                day = datetime.fromisoformat(entry.get("timestamp", "")).date()
            except Exception:
                day = datetime.now().date()
            if day not in groups_by_day:
                groups_by_day[day] = []
                groups.append(day)
            groups_by_day[day].append(entry)

        for index, day in enumerate(groups):
            entries = groups_by_day[day]
            section = CollapsibleSection(
                f"{history_day_label(day)} ({len(entries)})", expanded=(index == 0)
            )
            for entry in entries:
                section.add_widget(self._make_history_entry_widget(entry))
            layout.insertWidget(layout.count() - 1, section)

    def _delete_minimax_history_entry(self, entry_id):
        entry = next((e for e in self.minimax_history if e.get("id") == entry_id), None)
        if not entry:
            return
        confirm = QMessageBox.question(
            self,
            "Eliminar entrada",
            "¿Seguro que quieres eliminar esta entrada del historial?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        entry_dir = get_minimax_history_images_dir() / entry_id
        self.minimax_history = [e for e in self.minimax_history if e.get("id") != entry_id]
        save_minimax_history(self.minimax_history)
        if entry_dir.exists():
            shutil.rmtree(entry_dir, ignore_errors=True)
        self._refresh_minimax_history_list()
        self.statusBar().showMessage("Entrada eliminada del historial.")

    def _toggle_minimax_history_favorite(self, entry_id, is_favorite):
        entry = next((e for e in self.minimax_history if e.get("id") == entry_id), None)
        if not entry:
            return
        entry["favorite"] = is_favorite
        save_minimax_history(self.minimax_history)
        self._refresh_minimax_history_list()

    def _load_minimax_history_item(self, entry_id):
        entry = next((e for e in self.minimax_history if e.get("id") == entry_id), None)
        if not entry:
            return
        self.minimax_input.setPlainText(entry.get("input", ""))
        self.minimax_output.setPlainText(entry.get("output", ""))
        restored_images = [p for p in entry.get("images", []) if os.path.exists(p)]
        self.selected_minimax_images = restored_images
        if restored_images:
            self._render_minimax_preview()
            self.statusBar().showMessage(f"Prompt del historial cargado con {len(restored_images)} imagen(es).")
        else:
            self._render_minimax_preview_empty()
            self.statusBar().showMessage("Prompt del historial cargado (sin imágenes).")

    def encode_image(self, image_path):
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def generate_minimax_prompt(self):
        text_input = self.minimax_input.toPlainText().strip()
        if not text_input and not self.selected_minimax_images:
            QMessageBox.warning(self, "Falta contenido", "Añade texto o al menos una imagen antes de generar el prompt.")
            return

        self.minimax_log.clear()

        prompt = (
            "Act as an expert prompt engineer for MiniMax H3. "
            "Generate a final prompt in English only, with high quality, clarity, completeness, and production-ready structure. "
            "Combine all information from the provided text and images. "
            "Include context, objective, tone, constraints, output format, and relevant visual details. "
            "Return only the final prompt in English, without explanations, notes, or extra commentary.\n\n"
            f"User text:\n{text_input or 'No text was provided.'}"
        )

        self._start_background_task(self.minimax_model.currentText(), prompt, self.selected_minimax_images, "minimax")

    def copy_minimax_output(self):
        text = self.minimax_output.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Sin contenido", "Primero genera un prompt para poder copiarlo.")
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Prompt copiado al portapapeles.")

    def get_selected_precision(self):
        for value, radio in self.precision_values.items():
            if radio.isChecked():
                return value
        return "equilibrada"

    def generate_vision_description(self):
        if not self.selected_vision_image:
            QMessageBox.warning(self, "Falta imagen", "Selecciona una imagen antes de generar la descripción.")
            return

        precision_map = {
            "basica": "Describe the image in 1-2 brief sentences. Highlight the main subject, setting, and mood.",
            "equilibrada": "Describe the image in 3-5 clear sentences. Mention the main elements, colors, composition, lighting, and overall impression.",
            "detallada": "Provide a detailed observation of the image. Explain visible elements, composition, contrast, texture, lighting, style, and relevant details.",
            "muy_detallada": "Provide a very detailed and exhaustive description of the image, analyzing composition, perspective, lighting, palette, materials, subjects, expressions, visual context, and stylistic meaning.",
        }

        custom_prompt = self.vision_prompt.toPlainText().strip()
        precision_instruction = precision_map.get(self.get_selected_precision(), precision_map["equilibrada"])
        final_prompt = (
            "You are an expert visual analysis assistant. "
            f"{precision_instruction} "
            "Respond in English only and keep the description useful, precise, and natural. "
            "If visible text appears in the image, describe it when relevant. "
            f"Additional user prompt: {custom_prompt if custom_prompt else 'No additional instructions.'}"
        )

        self._start_background_task(self.get_vision_model_name(), final_prompt, [self.selected_vision_image], "vision")

    def get_vision_model_name(self):
        return (
            "orcarouter/Qwen3.8-27B-Uncensored:latest"
            if self.vision_model.currentText() == "Pro"
            else "lukey03/qwen3.5-9b-abliterated-vision:latest"
        )

    def copy_vision_output(self):
        text = self.vision_output.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Sin contenido", "Primero genera una descripción para poder copiarla.")
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Descripción copiada al portapapeles.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ModernApp()
    window.show()
    sys.exit(app.exec())
