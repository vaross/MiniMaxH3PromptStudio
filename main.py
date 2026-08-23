import base64
import os
import sys
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
)


OLLAMA_URL = "http://localhost:11434"

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

    @Slot(str, str, object)
    def run(self, model_name, prompt, image_paths):
        try:
            image_paths = image_paths or []
            images = []
            for image_path in image_paths:
                with open(image_path, "rb") as f:
                    images.append(base64.b64encode(f.read()).decode("utf-8"))

            payload = {
                "model": model_name,
                "messages": [{
                    "role": "user",
                    "content": prompt,
                    "images": images,
                }],
                "stream": False,
            }
            response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=180)
            response.raise_for_status()
            body = response.json()
            if "message" not in body or "content" not in body["message"]:
                raise ValueError("La respuesta de Ollama no tiene el formato esperado.")
            self.finished.emit(body["message"]["content"].strip())
        except Exception as exc:
            self.failed.emit(str(exc))


class ModernApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.selected_minimax_images = []
        self.selected_vision_image = ""
        self.setWindowTitle("MiniMax + Vision Studio")
        self.resize(1180, 820)
        self.setMinimumSize(980, 720)
        self.setStyleSheet(CSS)
        self._set_window_icon()

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_minimax_tab(), "MiniMax H3")
        self.tabs.addTab(self._build_vision_tab(), "Descripción visual")
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
        outer = QHBoxLayout(container)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(18)

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
        self.minimax_input.setMinimumHeight(260)
        left_layout.addWidget(self.minimax_input)

        model_row = QHBoxLayout()
        model_row.setSpacing(12)
        model_label = QLabel("Modelo Ollama")
        model_label.setObjectName("section-title")
        model_row.addWidget(model_label)
        model_row.addStretch()
        left_layout.addLayout(model_row)

        self.minimax_model = QComboBox()
        self.minimax_model.addItems(["agente-minimax", "agente-minimax-lite"])
        left_layout.addWidget(self.minimax_model)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        btn_images = QPushButton("Cargar imágenes")
        btn_images.clicked.connect(self.select_minimax_images)
        btn_clear = QPushButton("Eliminar todo")
        btn_clear.setObjectName("danger-button")
        btn_clear.clicked.connect(self.clear_minimax_images)
        btn_generate = QPushButton("Generar prompt")
        btn_generate.setObjectName("primary-button")
        btn_generate.clicked.connect(self.generate_minimax_prompt)

        actions.addWidget(btn_images)
        actions.addWidget(btn_clear)
        actions.addStretch()
        actions.addWidget(btn_generate)
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
        right_layout.addWidget(preview_panel)

        output_title = QLabel("Prompt generado")
        output_title.setObjectName("section-title")
        right_layout.addWidget(output_title)

        self.minimax_output = QPlainTextEdit()
        self.minimax_output.setPlaceholderText("Tu prompt final aparecerá aquí...")
        self.minimax_output.setMinimumHeight(220)
        right_layout.addWidget(self.minimax_output)

        copy_row = QHBoxLayout()
        copy_row.addStretch()
        btn_copy = QPushButton("Copiar todo")
        btn_copy.clicked.connect(self.copy_minimax_output)
        copy_row.addWidget(btn_copy)
        right_layout.addLayout(copy_row)

        left_card.setFixedWidth(540)
        outer.addWidget(left_card)
        outer.addWidget(right_card)
        return container

    def _build_vision_tab(self):
        container = QWidget()
        outer = QHBoxLayout(container)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(18)

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
        self.vision_prompt.setMaximumHeight(120)
        left_layout.addWidget(self.vision_prompt)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        btn_load = QPushButton("Cargar imagen")
        btn_load.clicked.connect(self.select_vision_image)
        btn_generate = QPushButton("Generar descripción")
        btn_generate.setObjectName("primary-button")
        btn_generate.clicked.connect(self.generate_vision_description)
        actions.addWidget(btn_load)
        actions.addStretch()
        actions.addWidget(btn_generate)
        left_layout.addLayout(actions)

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
        self.vision_preview_label.setMinimumHeight(320)
        self.vision_preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.vision_preview_label.setWordWrap(True)
        preview_layout.addWidget(self.vision_preview_label)
        preview_panel.dropped.connect(self.handle_vision_drop)
        right_layout.addWidget(preview_panel)

        output_title = QLabel("Descripción generada")
        output_title.setObjectName("section-title")
        right_layout.addWidget(output_title)

        self.vision_output = QPlainTextEdit()
        self.vision_output.setPlaceholderText("La descripción saldrá aquí...")
        self.vision_output.setMinimumHeight(220)
        right_layout.addWidget(self.vision_output)

        copy_row = QHBoxLayout()
        copy_row.addStretch()
        btn_copy = QPushButton("Copiar descripción")
        btn_copy.clicked.connect(self.copy_vision_output)
        copy_row.addWidget(btn_copy)
        right_layout.addLayout(copy_row)

        left_card.setFixedWidth(440)
        outer.addWidget(left_card)
        outer.addWidget(right_card)
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
        if busy:
            self.spinner_timer.start(100)
            self._animate_spinner()
            self.statusBar().showMessage(f"Procesando: {message}")
        else:
            self.spinner_timer.stop()
            self.busy_spinner_label.setVisible(False)
            self.busy_spinner_label.setText("")
            self.statusBar().showMessage("Conectado con Ollama. Listo para usar.")

    def _start_background_task(self, model_name, prompt, image_paths, target_key):
        worker_thread = QThread(self)
        worker = OllamaWorker()
        worker.moveToThread(worker_thread)
        worker.finished.connect(self._handle_background_result)
        worker.failed.connect(self._handle_background_error)
        worker_thread.started.connect(lambda: worker.run(model_name, prompt, image_paths))
        worker.finished.connect(worker_thread.quit)
        worker.failed.connect(worker_thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker_thread.finished.connect(worker_thread.deleteLater)
        self._active_task = (target_key, worker_thread)
        self._set_busy("Procesando solicitud...", True)
        worker_thread.start()

    def _handle_background_result(self, result):
        target_key = self._active_task[0]
        self._set_busy("", False)
        if target_key == "minimax":
            self.minimax_output.setPlainText(result)
            self.statusBar().showMessage("Prompt generado con MiniMax H3.")
        elif target_key == "vision":
            self.vision_output.setPlainText(result)
            self.statusBar().showMessage("Descripción visual generada.")
        self._active_task = None

    def _handle_background_error(self, error_text):
        self._set_busy("", False)
        if self._active_task and self._active_task[0] == "minimax":
            QMessageBox.critical(self, "Error al generar el prompt", f"No se pudo generar el prompt:\n{error_text}")
            self.statusBar().showMessage("Error al comunicarse con Ollama.")
        elif self._active_task and self._active_task[0] == "vision":
            QMessageBox.critical(self, "Error al describir la imagen", f"No se pudo describir la imagen:\n{error_text}")
            self.statusBar().showMessage("Error al comunicarse con el modelo de visión.")
        self._active_task = None

    def encode_image(self, image_path):
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def generate_minimax_prompt(self):
        text_input = self.minimax_input.toPlainText().strip()
        if not text_input and not self.selected_minimax_images:
            QMessageBox.warning(self, "Falta contenido", "Añade texto o al menos una imagen antes de generar el prompt.")
            return

        prompt = (
            "Act as an expert prompt engineer for MiniMax H3. "
            "Generate a final prompt in English only, with high quality, clarity, completeness, and production-ready structure. "
            "Combine all information from the provided text and images. "
            "Include context, objective, tone, constraints, output format, and relevant visual details. "
            "Return only the final prompt in English, without explanations, notes, or extra commentary.\n\n"
            f"User text:\n{text_input or 'No text was provided.'}"
        )

        self._active_task = ("minimax", None)
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
