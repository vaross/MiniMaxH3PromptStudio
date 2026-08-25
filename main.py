import base64
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image
from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QButtonGroup,
    QSplitter,
    QDockWidget,
)


OLLAMA_URL = "http://localhost:11434"
OLLAMA_URL_CLOUD = os.getenv("MODAL_OLLAMA_URL", "https://vilchesdiaz-alvaro--agente-minimax-h3-fastapi-app.modal.run")
OLLAMA_TIMEOUT_NORMAL = 600  # 10 minutos
OLLAMA_TIMEOUT_HEAVY = 1800  # 30 minutos
HISTORY_MAX_ENTRIES = 200


def get_minimax_history_path():
    base = os.getenv("APPDATA") or str(Path.home())
    folder = Path(base) / "MiniMaxPromptStudio"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "minimax_history.json"


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
            if not self.stop_requested:
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
        }
        self.status.emit(f"Conectando con el modelo '{model_name}' en la nube...")
        print(f"[DEBUG] Connecting to {self.url}/generar, model: {model_name}, timeout: {self.timeout}s")
        self.response = requests.post(
            f"{self.url}/generar", json=payload, timeout=self.timeout
        )
        self.response.raise_for_status()
        self.status.emit("Generando respuesta...")
        print("[DEBUG] Generating response from cloud...")

        try:
            result = self.response.json()
            if isinstance(result, dict):
                full_text = result.get("response", result.get("text", str(result)))
            else:
                full_text = str(result)
        except json.JSONDecodeError:
            full_text = self.response.text

        if not full_text:
            raise ValueError("La respuesta de la nube no tiene el formato esperado.")

        print(f"[DEBUG] Completed. Total: {len(full_text)} chars")
        self.chunk.emit(full_text)
        self.finished.emit(full_text.strip())


class ModernApp(QMainWindow):
    start_ollama_task = Signal(str, str, object)

    def __init__(self):
        super().__init__()
        self.selected_minimax_images = []
        self.selected_vision_image = ""
        self.minimax_history = load_minimax_history()
        self.setWindowTitle("MiniMax + Vision Studio")
        self.resize(1400, 900)
        self.setMinimumSize(1024, 768)
        self.setStyleSheet(CSS)
        self._set_window_icon()

        self._active_task = None
        self.stop_button_minimax = None
        self.stop_button_vision = None

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_minimax_tab(), "MiniMax H3")
        self.tabs.addTab(self._build_vision_tab(), "Descripción visual")
        self.setCentralWidget(self.tabs)

        self._setup_history_dock()

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

    def _setup_history_dock(self):
        dock = QDockWidget("Historial de prompts", self)
        dock.setObjectName("HistoryDock")
        dock_widget = QWidget()
        dock_layout = QVBoxLayout(dock_widget)
        dock_layout.setContentsMargins(0, 0, 0, 0)

        self.minimax_history_list = QListWidget()
        self.minimax_history_list.itemClicked.connect(self._load_minimax_history_item)
        dock_layout.addWidget(self.minimax_history_list)

        dock.setWidget(dock_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self._refresh_minimax_history_list()

    def _build_minimax_tab(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

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

        right_card = QFrame()
        right_card.setObjectName("card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(18, 18, 18, 18)
        right_layout.setSpacing(12)

        preview_title = QLabel("Vista previa de imágenes")
        preview_title.setObjectName("section-title")
        right_layout.addWidget(preview_title)

        preview_panel = ImageDropZone(self)
        preview_panel.setObjectName("drop-zone")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(10)
        preview_panel.dropped.connect(self.add_minimax_images)
        self.minimax_preview_container = preview_panel
        self.minimax_preview_layout = preview_layout
        self._render_minimax_preview_empty()
        right_layout.addWidget(preview_panel, 1)

        output_title = QLabel("Prompt generado")
        output_title.setObjectName("section-title")
        right_layout.addWidget(output_title)

        self.minimax_output = QPlainTextEdit()
        self.minimax_output.setPlaceholderText("Tu prompt final aparecerá aquí...")
        self.minimax_output.setMinimumHeight(180)
        right_layout.addWidget(self.minimax_output, 1)

        copy_row = QHBoxLayout()
        copy_row.addStretch()
        btn_copy = QPushButton("Copiar todo")
        btn_copy.clicked.connect(self.copy_minimax_output)
        copy_row.addWidget(btn_copy)
        right_layout.addLayout(copy_row)

        splitter.addWidget(left_card)
        splitter.addWidget(right_card)
        splitter.setSizes([400, 600])
        main_layout.addWidget(splitter, 1)

        log_card = QFrame()
        log_card.setObjectName("card")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(18, 14, 18, 14)
        log_layout.setSpacing(8)

        log_title = QLabel("Registro en tiempo real")
        log_title.setObjectName("section-title")
        log_layout.addWidget(log_title)

        self.minimax_log = QPlainTextEdit()
        self.minimax_log.setReadOnly(True)
        self.minimax_log.setPlaceholderText("Aquí verás el progreso de la generación...")
        self.minimax_log.setMaximumHeight(120)
        self.minimax_log.setStyleSheet("QPlainTextEdit { font-family: Consolas, monospace; font-size: 11px; }")
        log_layout.addWidget(self.minimax_log)

        main_layout.addWidget(log_card, 0)

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
        self.vision_output.setMinimumHeight(180)
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

    def _render_minimax_preview_empty(self):
        while self.minimax_preview_layout.count():
            item = self.minimax_preview_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        empty = QLabel("Arrastra imágenes aquí o usa \"Cargar imágenes\"")
        empty.setObjectName("preview-empty")
        empty.setAlignment(Qt.AlignCenter)
        empty.setWordWrap(True)
        self.minimax_preview_layout.addWidget(empty)

    def _render_minimax_preview(self):
        while self.minimax_preview_layout.count():
            item = self.minimax_preview_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.selected_minimax_images:
            self._render_minimax_preview_empty()
            return

        for index, path in enumerate(self.selected_minimax_images):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 2, 4, 2)
            row_layout.setSpacing(10)

            label = QLabel()
            label.setFixedSize(100, 72)
            label.setStyleSheet("border: 1px solid #dfe8ff; border-radius: 10px; background: #f8fbff;")
            label.setAlignment(Qt.AlignCenter)
            try:
                pixmap = self._pixmap_from_path(path, (100, 72))
                label.setPixmap(pixmap)
            except Exception:
                label.setText("IMG")

            text = QLabel(os.path.basename(path))
            text.setWordWrap(True)
            text.setMaximumWidth(230)

            remove_btn = QPushButton("✕")
            remove_btn.setObjectName("danger-button")
            remove_btn.clicked.connect(lambda checked, idx=index: self.remove_minimax_image(idx))
            remove_btn.setFixedWidth(28)

            row_layout.addWidget(label)
            row_layout.addWidget(text, 1)
            row_layout.addWidget(remove_btn)
            self.minimax_preview_layout.addWidget(row)

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

    def remove_minimax_image(self, index):
        if 0 <= index < len(self.selected_minimax_images):
            del self.selected_minimax_images[index]
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

    def _save_minimax_history_entry(self, output_text):
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "model": self.minimax_model.currentText(),
            "input": self.minimax_input.toPlainText(),
            "output": output_text,
        }
        self.minimax_history.insert(0, entry)
        del self.minimax_history[HISTORY_MAX_ENTRIES:]
        save_minimax_history(self.minimax_history)
        self._refresh_minimax_history_list()

    def _refresh_minimax_history_list(self):
        self.minimax_history_list.clear()
        for entry in self.minimax_history:
            preview = entry.get("input", "").strip().replace("\n", " ")
            if len(preview) > 60:
                preview = preview[:60] + "…"
            if not preview:
                preview = "(sin texto de entrada)"
            item = QListWidgetItem(f"{entry.get('timestamp', '')} — {preview}")
            item.setData(Qt.UserRole, entry.get("id"))
            self.minimax_history_list.addItem(item)

    def _load_minimax_history_item(self, item):
        entry_id = item.data(Qt.UserRole)
        entry = next((e for e in self.minimax_history if e.get("id") == entry_id), None)
        if not entry:
            return
        self.minimax_input.setPlainText(entry.get("input", ""))
        self.minimax_output.setPlainText(entry.get("output", ""))
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
