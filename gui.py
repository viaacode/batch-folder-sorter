import os
import random
import threading

from PySide6.QtCore import (
    QObject,
    QPointF,
    Property,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from batch_restructure import run_batch, undo_batch


MODE_OPTIONS = {
    "Standard mode": "standard",
    "Artwork batch mode": "artwork",
}


def resource_path(filename):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


LOGO_PATH = resource_path("assets/meemoo-logo_lockup-pos-rgb.svg")


def shorten_path(path, fallback):
    if not path:
        return fallback
    name = os.path.basename(path.rstrip(os.sep)) or path
    return name if len(name) <= 28 else f"{name[:25]}..."


class BatchWorker(QObject):
    log = Signal(str)
    status = Signal(str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, root_path, csv_path, mode, stop_event):
        super().__init__()
        self.root_path = root_path
        self.csv_path = csv_path
        self.mode = mode
        self.stop_event = stop_event

    def run(self):
        try:
            self.status.emit("Preparing batch...")
            result = run_batch(
                self.root_path,
                self.csv_path,
                False,
                stop_event=self.stop_event,
                mode=self.mode,
                logger=self.log.emit,
            )
            result["action"] = "run"
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class UndoWorker(QObject):
    log = Signal(str)
    status = Signal(str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, root_path, operations):
        super().__init__()
        self.root_path = root_path
        self.operations = operations

    def run(self):
        try:
            self.status.emit("Undoing last batch...")
            result = undo_batch(self.root_path, self.operations, logger=self.log.emit)
            result["action"] = "undo"
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class RippleButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._ripple_radius = 0.0
        self._ripple_opacity = 0.0
        self._ripple_center = QPointF()
        self._ripple_group = None
        self.setCursor(Qt.PointingHandCursor)

    def _get_ripple_radius(self):
        return self._ripple_radius

    def _set_ripple_radius(self, value):
        self._ripple_radius = value
        self.update()

    def _get_ripple_opacity(self):
        return self._ripple_opacity

    def _set_ripple_opacity(self, value):
        self._ripple_opacity = value
        self.update()

    ripple_radius = Property(float, _get_ripple_radius, _set_ripple_radius)
    ripple_opacity = Property(float, _get_ripple_opacity, _set_ripple_opacity)

    def mousePressEvent(self, event):
        self._ripple_center = event.position()
        self._ripple_group = QParallelAnimationGroup(self)

        radius = QPropertyAnimation(self, b"ripple_radius", self._ripple_group)
        radius.setStartValue(0.0)
        radius.setEndValue(max(self.width(), self.height()) * 0.8)
        radius.setDuration(360)
        radius.setEasingCurve(QEasingCurve.OutCubic)

        opacity = QPropertyAnimation(self, b"ripple_opacity", self._ripple_group)
        opacity.setStartValue(0.2)
        opacity.setEndValue(0.0)
        opacity.setDuration(360)
        opacity.setEasingCurve(QEasingCurve.OutCubic)

        self._ripple_group.start()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setClipRect(self.rect())

        if self._ripple_opacity > 0:
            if self.objectName() in {"Accent", "PickerActive", "ModeActive"}:
                color = QColor(255, 255, 255, int(self._ripple_opacity * 90))
            else:
                color = QColor(43, 208, 183, int(self._ripple_opacity * 70))
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(
                self._ripple_center, self._ripple_radius, self._ripple_radius
            )

        # macOS can omit QPushButton text when the object name is changed
        # dynamically. Paint picker labels explicitly so selected paths remain visible.
        if self.objectName() in {"Picker", "PickerActive"} and self.text():
            text_color = (
                QColor("#145c50")
                if self.objectName() == "PickerActive"
                else QColor("#213029")
            )
            if not self.isEnabled():
                text_color = QColor("#968f83")
            painter.setPen(text_color)
            painter.setFont(self.font())
            painter.drawText(
                self.rect().adjusted(14, 0, -14, 0),
                Qt.AlignLeft | Qt.AlignVCenter,
                self.text(),
            )


class ModeButton(RippleButton):
    def __init__(self, text, on_click):
        super().__init__(text)
        self.setCheckable(True)
        self.clicked.connect(on_click)
        self.setCursor(Qt.PointingHandCursor)


class ConfettiOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.particles = []
        self.frame = 0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._advance)
        self.hide()

    def start(self):
        self.setGeometry(self.parentWidget().rect())
        colors = ["#00c8aa", "#e39a32", "#213029", "#d9f4ee", "#b64a2e"]
        self.particles = [
            {
                "x": self.width() * random.uniform(0.15, 0.85),
                "y": random.uniform(-30, 20),
                "vx": random.uniform(-2.4, 2.4),
                "vy": random.uniform(1.2, 4.2),
                "size": random.randint(5, 10),
                "color": QColor(random.choice(colors)),
                "angle": random.uniform(0, 360),
                "spin": random.uniform(-8, 8),
            }
            for _ in range(90)
        ]
        self.frame = 0
        self.show()
        self.raise_()
        self.timer.start()

    def _advance(self):
        self.frame += 1
        for particle in self.particles:
            particle["x"] += particle["vx"]
            particle["y"] += particle["vy"]
            particle["vy"] += 0.08
            particle["angle"] += particle["spin"]
        if self.frame > 115:
            self.timer.stop()
            self.hide()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for particle in self.particles:
            painter.save()
            painter.translate(particle["x"], particle["y"])
            painter.rotate(particle["angle"])
            painter.setBrush(particle["color"])
            painter.setPen(Qt.NoPen)
            size = particle["size"]
            painter.drawRoundedRect(-size / 2, -size / 2, size, size * 0.65, 2, 2)
            painter.restore()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.worker = None
        self.root_path = ""
        self.csv_path = ""
        self.mode_label = "Standard mode"
        self.log_visible = False
        self.last_run_result = None
        self.spinner_frames = ["◐", "◓", "◑", "◒"]
        self.spinner_index = 0

        self.setWindowTitle("Batch Folder Sorter")
        self.resize(760, 620)
        self.setMinimumSize(720, 600)
        icon_path = LOGO_PATH if os.path.exists(LOGO_PATH) else resource_path("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()
        self._apply_styles()
        self.update_selection_state()
        self.update_mode_state()
        self.set_running_state(False)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self.confetti = ConfettiOverlay(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)

        self.header = QFrame()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(16)

        self.logo_label = QSvgWidget(LOGO_PATH)
        self.logo_label.setObjectName("LogoLabel")
        self.logo_label.setFixedSize(132, 80)
        header_layout.addWidget(self.logo_label, 0, Qt.AlignLeft | Qt.AlignVCenter)

        title_stack = QVBoxLayout()
        title_stack.setSpacing(4)

        self.title_label = QLabel("Batch Folder Sorter")
        self.subtitle_label = QLabel(
            "meemoo ingest preparation for standard sorting and artwork batch processing"
        )
        title_stack.addWidget(self.title_label)
        title_stack.addWidget(self.subtitle_label)
        header_layout.addLayout(title_stack, 1)
        outer.addWidget(self.header)

        self.card = QFrame()
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(12)

        heading = QLabel("Batch Setup")
        heading.setObjectName("SectionTitle")
        desc = QLabel(
            "Choose the ROOT folder, select the CSV metadata file, then pick the workflow."
        )
        desc.setWordWrap(True)
        desc.setObjectName("Muted")
        card_layout.addWidget(heading)
        card_layout.addWidget(desc)

        card_layout.addLayout(self._build_picker_row("ROOT folder", "root"))
        card_layout.addLayout(self._build_picker_row("CSV file", "csv"))

        mode_title = QLabel("Processing mode")
        mode_title.setObjectName("FieldTitle")
        card_layout.addWidget(mode_title)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        self.standard_mode_button = ModeButton(
            "Standard mode", lambda: self.select_mode("Standard mode")
        )
        self.artwork_mode_button = ModeButton(
            "Artwork batch mode",
            lambda: self.select_mode("Artwork batch mode"),
        )
        mode_row.addWidget(self.standard_mode_button)
        mode_row.addWidget(self.artwork_mode_button)
        card_layout.addLayout(mode_row)

        mode_help = QLabel("Artwork mode supports _M, _B")
        mode_help.setObjectName("Muted")
        card_layout.addWidget(mode_help)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.run_button = RippleButton("Run Batch")
        self.undo_button = RippleButton("Undo")
        self.reset_button = RippleButton("Reset")
        self.run_button.clicked.connect(self.start_run)
        self.undo_button.clicked.connect(self.undo_last_run)
        self.reset_button.clicked.connect(self.reset_ui)
        actions.addWidget(self.run_button)
        actions.addWidget(self.undo_button)
        actions.addWidget(self.reset_button)
        card_layout.addLayout(actions)
        outer.addWidget(self.card)

        self.status_card = QFrame()
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(22, 16, 22, 16)
        status_layout.setSpacing(8)
        status_title = QLabel("Status")
        status_title.setObjectName("SectionTitle")
        self.status_label = QLabel("Ready.")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("Muted")
        self.spinner_label = QLabel(self.spinner_frames[0])
        self.spinner_label.setObjectName("Spinner")
        self.spinner_label.hide()
        self.spinner_timer = QTimer(self)
        self.spinner_timer.setInterval(120)
        self.spinner_timer.timeout.connect(self._advance_spinner)
        status_layout.addWidget(status_title)
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addWidget(self.spinner_label, 0, Qt.AlignVCenter)
        status_row.addWidget(self.status_label, 1)
        status_layout.addLayout(status_row)
        outer.addWidget(self.status_card)

        self.log_card = QFrame()
        log_layout = QVBoxLayout(self.log_card)
        log_layout.setContentsMargins(22, 16, 22, 16)
        log_layout.setSpacing(8)
        log_title = QLabel("Detailed Log")
        log_title.setObjectName("SectionTitle")
        log_help = QLabel("Use this panel only when you need per-file detail.")
        log_help.setObjectName("Muted")
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        log_layout.addWidget(log_title)
        log_layout.addWidget(log_help)
        log_layout.addWidget(self.log_box)
        self.log_card.hide()
        outer.addWidget(self.log_card)
        outer.addStretch()

    def _build_picker_row(self, title, kind):
        layout = QVBoxLayout()
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("FieldTitle")
        badge = QLabel("Not selected")
        badge.setObjectName("BadgeIdle")
        top.addWidget(title_label)
        top.addStretch()
        top.addWidget(badge)
        layout.addLayout(top)

        if kind == "root":
            button = RippleButton("Choose ROOT folder")
            button.clicked.connect(self.browse_root)
            self.root_button = button
            self.root_badge = badge
        else:
            button = RippleButton("Choose CSV file")
            button.clicked.connect(self.browse_csv)
            self.csv_button = button
            self.csv_badge = badge

        layout.addWidget(button)
        return layout

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f3efe6;
            }
            QFrame {
                background: #fbf8f1;
                border: 1px solid #d8d0c2;
                border-radius: 18px;
            }
            QFrame#Header {
                background: #fffdf8;
                border: 1px solid #d8d0c2;
            }
            QLabel {
                color: #213029;
                background: transparent;
                border: none;
            }
            QLabel#SectionTitle {
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#FieldTitle {
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#Muted {
                color: #6b756e;
                font-size: 12px;
            }
            QLabel#Spinner {
                color: #00c8aa;
                font-size: 20px;
                font-weight: 700;
                min-width: 20px;
            }
            QLabel#BadgeIdle, QLabel#BadgeActive {
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#BadgeIdle {
                background: #ece5d7;
                color: #6b756e;
            }
            QLabel#BadgeActive {
                background: #dcefe6;
                color: #159d89;
            }
            QPushButton {
                background: #eee7d8;
                color: #213029;
                border: none;
                border-radius: 14px;
                padding: 12px 14px;
                font-size: 13px;
                font-weight: 600;
                text-align: center;
            }
            QPushButton:hover {
                background: #e1d7c4;
            }
            QPushButton:disabled {
                background: #d6d1c8;
                color: #968f83;
            }
            QPushButton#Accent {
                background: #00c8aa;
                color: white;
            }
            QPushButton#Accent:hover {
                background: #00b49a;
            }
            QPushButton#Picker {
                background: #eee7d8;
                color: #213029;
                font-size: 12px;
                font-weight: 600;
                padding: 10px 14px;
                text-align: left;
            }
            QPushButton#Picker:hover {
                background: #e1d7c4;
            }
            QPushButton#PickerActive {
                background: #d9f4ee;
                color: #145c50;
                border: 1px solid #8edccd;
                font-size: 12px;
                font-weight: 600;
                padding: 10px 14px;
                text-align: left;
            }
            QPushButton#PickerActive:hover {
                background: #c5eee5;
            }
            QPushButton#Undo {
                background: #e39a32;
                color: white;
            }
            QPushButton#Undo:hover {
                background: #c98528;
            }
            QPushButton#Danger {
                background: #b64a2e;
                color: white;
            }
            QPushButton#Danger:hover {
                background: #953c25;
            }
            QPushButton#Mode, QPushButton#ModeActive {
                padding: 10px 14px;
            }
            QPushButton#Mode {
                background: #ece5d7;
                color: #213029;
            }
            QPushButton#ModeActive {
                background: #00c8aa;
                color: white;
            }
            QPushButton:pressed {
                padding-top: 13px;
                padding-bottom: 11px;
            }
            QTextEdit {
                background: #1f2b25;
                color: #e8f0eb;
                border: none;
                border-radius: 14px;
                padding: 10px;
                font-family: Menlo;
                font-size: 12px;
            }
            """
        )
        self.header.setObjectName("Header")
        self.title_label.setStyleSheet(
            "color: #213029; font-size: 28px; font-weight: 700; border: none;"
        )
        self.title_label.setAlignment(Qt.AlignLeft)
        self.subtitle_label.setStyleSheet(
            "color: #6b756e; font-size: 13px; border: none;"
        )
        self.subtitle_label.setAlignment(Qt.AlignLeft)
        self.run_button.setObjectName("Accent")
        self.undo_button.setObjectName("Picker")
        self.root_button.setObjectName("Picker")
        self.csv_button.setObjectName("Picker")

    def update_selection_state(self):
        if self.root_path:
            self.root_button.setText(f"Selected: {shorten_path(self.root_path, 'ROOT')}")
            self.root_button.setToolTip(self.root_path)
            self.root_button.setObjectName("PickerActive")
            self.root_badge.setText("Selected")
            self.root_badge.setObjectName("BadgeActive")
        else:
            self.root_button.setText("Choose ROOT folder")
            self.root_button.setToolTip("")
            self.root_button.setObjectName("Picker")
            self.root_badge.setText("Not selected")
            self.root_badge.setObjectName("BadgeIdle")

        if self.csv_path:
            self.csv_button.setText(f"Selected: {shorten_path(self.csv_path, 'CSV')}")
            self.csv_button.setToolTip(self.csv_path)
            self.csv_button.setObjectName("PickerActive")
            self.csv_badge.setText("Selected")
            self.csv_badge.setObjectName("BadgeActive")
        else:
            self.csv_button.setText("Choose CSV file")
            self.csv_button.setToolTip("")
            self.csv_button.setObjectName("Picker")
            self.csv_badge.setText("Not selected")
            self.csv_badge.setObjectName("BadgeIdle")

        self._refresh_styles(self.root_button, self.csv_button, self.root_badge, self.csv_badge)
        self.root_button.setStyleSheet(
            "color: #145c50;" if self.root_path else "color: #213029;"
        )
        self.csv_button.setStyleSheet(
            "color: #145c50;" if self.csv_path else "color: #213029;"
        )

    def update_mode_state(self):
        self.standard_mode_button.setChecked(self.mode_label == "Standard mode")
        self.artwork_mode_button.setChecked(
            self.mode_label == "Artwork batch mode"
        )
        self.standard_mode_button.setObjectName(
            "ModeActive" if self.mode_label == "Standard mode" else "Mode"
        )
        self.artwork_mode_button.setObjectName(
            "ModeActive" if self.mode_label == "Artwork batch mode" else "Mode"
        )
        self._refresh_styles(self.standard_mode_button, self.artwork_mode_button)

    def _refresh_styles(self, *widgets):
        self.style().unpolish(self)
        self.style().polish(self)
        for widget in widgets:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def select_mode(self, mode_label):
        self.mode_label = mode_label
        self.update_mode_state()
        self.set_status(f"{mode_label} selected.")

    def set_status(self, message):
        self.status_label.setText(message)

    def _advance_spinner(self):
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)
        self.spinner_label.setText(self.spinner_frames[self.spinner_index])

    def show_message(self, title, text, icon=QMessageBox.Information):
        box = QMessageBox(self)
        box.setOption(QMessageBox.Option.DontUseNativeDialog, True)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(icon)
        box.setStandardButtons(QMessageBox.Ok)
        box.setStyleSheet(
            """
            QMessageBox {
                background: #fbf8f1;
            }
            QMessageBox QLabel {
                color: #213029;
                font-size: 14px;
                min-width: 320px;
            }
            QMessageBox QPushButton {
                background: #eee7d8;
                color: #213029;
                border: none;
                border-radius: 12px;
                padding: 10px 18px;
                min-width: 88px;
                font-size: 13px;
                font-weight: 700;
            }
            QMessageBox QPushButton:hover {
                background: #e1d7c4;
            }
            """
        )
        box.exec()

    def append_log(self, message):
        self.log_box.append(message)

    def clear_log(self):
        self.log_box.clear()

    def update_undo_button_state(self, is_running):
        undo_available = (
            (not is_running)
            and bool(self.last_run_result)
            and bool(self.last_run_result.get("operations"))
        )
        self.undo_button.setEnabled(undo_available)
        self.undo_button.setObjectName("Undo" if undo_available else "Picker")
        self._refresh_styles(self.undo_button)

    def set_running_state(self, is_running):
        self.root_button.setEnabled(not is_running)
        self.csv_button.setEnabled(not is_running)
        self.run_button.setEnabled(not is_running)
        self.reset_button.setEnabled(not is_running)
        self.standard_mode_button.setEnabled(not is_running)
        self.artwork_mode_button.setEnabled(not is_running)
        self.update_undo_button_state(is_running)
        self.spinner_label.setVisible(is_running)
        if is_running:
            self.spinner_timer.start()
        else:
            self.spinner_timer.stop()
            self.spinner_index = 0
            self.spinner_label.setText(self.spinner_frames[0])

    def browse_root(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select ROOT folder", self.root_path or os.getcwd()
        )
        if path:
            self.root_path = path
            self.update_selection_state()
            self.set_status("ROOT folder selected.")

    def browse_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV metadata file",
            self.csv_path or os.getcwd(),
            "CSV files (*.csv)",
        )
        if path:
            self.csv_path = path
            self.update_selection_state()
            self.set_status("CSV file selected.")

    def toggle_log(self):
        self.log_visible = not self.log_visible
        self.log_card.setVisible(self.log_visible)
        self.toggle_log_button.setText("Hide details" if self.log_visible else "Show details")

    def reset_ui(self):
        if self.worker_thread and self.worker_thread.isRunning():
            self.show_message(
                "Busy",
                "Wait for the current process to finish.",
                QMessageBox.Warning,
            )
            return
        self.root_path = ""
        self.csv_path = ""
        self.mode_label = "Standard mode"
        self.clear_log()
        self.update_selection_state()
        self.update_mode_state()
        self.set_status("Ready.")

    def start_run(self):
        if self.worker_thread and self.worker_thread.isRunning():
            return
        if not self.root_path:
            self.show_message(
                "Missing ROOT folder",
                "Please select the ROOT folder.",
                QMessageBox.Warning,
            )
            return
        if not self.csv_path:
            self.show_message(
                "Missing CSV file",
                "Please select the CSV metadata file.",
                QMessageBox.Warning,
            )
            return

        self.stop_event.clear()
        self.clear_log()
        self.set_status(f"Running {self.mode_label.lower()}...")
        self.set_running_state(True)

        self.worker_thread = QThread(self)
        self.worker = BatchWorker(
            self.root_path,
            self.csv_path,
            MODE_OPTIONS[self.mode_label],
            self.stop_event,
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.status.connect(self.set_status)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self.on_worker_error)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def undo_last_run(self):
        if self.worker_thread and self.worker_thread.isRunning():
            return
        if not self.last_run_result or not self.last_run_result.get("operations"):
            self.show_message(
                "Undo unavailable",
                "There is nothing to undo yet.",
                QMessageBox.Information,
            )
            return

        self.clear_log()
        self.set_status("Undoing last batch...")
        self.set_running_state(True)

        self.worker_thread = QThread(self)
        self.worker = UndoWorker(
            self.last_run_result["root_path"],
            self.last_run_result["operations"],
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.status.connect(self.set_status)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self.on_worker_error)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def on_worker_finished(self, result):
        self.worker = None
        self.worker_thread = None

        if result.get("action") == "undo":
            self.last_run_result = None
            self.set_running_state(False)
            self.set_status("Last batch was undone.")
            self.show_message(
                "Undo complete",
                "The last batch was restored.",
                QMessageBox.Information,
            )
            return

        cancelled = result.get("cancelled", False)
        self.last_run_result = result if result.get("operations") else None
        self.set_running_state(False)

        if cancelled:
            self.set_status("Processing cancelled.")
            self.show_message("Stopped", "Process was cancelled.", QMessageBox.Information)
        else:
            self.set_status("Batch processing completed.")
            self.confetti.start()
            self.show_message(
                "Finished",
                "Batch processing completed.",
                QMessageBox.Information,
            )

    def on_worker_error(self, message):
        self.set_running_state(False)
        self.worker = None
        self.worker_thread = None
        self.set_status("Oops, something went wrong.")
        self.append_log(f"Error detail: {message}")
        self.show_message(
            "Oops",
            "Oops, something went wrong.",
            QMessageBox.Critical,
        )


if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
