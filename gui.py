import os
import threading

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap
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


LOGO_PATH = resource_path("logo.png")


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


class ModeButton(QPushButton):
    def __init__(self, text, on_click):
        super().__init__(text)
        self.setCheckable(True)
        self.clicked.connect(on_click)
        self.setCursor(Qt.PointingHandCursor)


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

        outer = QVBoxLayout(central)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)

        self.header = QFrame()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(16)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("LogoLabel")
        if os.path.exists(LOGO_PATH):
            logo_pixmap = QPixmap(LOGO_PATH)
            if not logo_pixmap.isNull():
                self.logo_label.setPixmap(
                    logo_pixmap.scaled(
                        170,
                        52,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
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
            "Artwork batch mode", lambda: self.select_mode("Artwork batch mode")
        )
        mode_row.addWidget(self.standard_mode_button)
        mode_row.addWidget(self.artwork_mode_button)
        card_layout.addLayout(mode_row)

        mode_help = QLabel("Artwork mode supports _M, _B and files without a suffix.")
        mode_help.setText("Artwork mode supports _M, _B")
        mode_help.setObjectName("Muted")
        card_layout.addWidget(mode_help)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.run_button = QPushButton("Run Batch")
        self.undo_button = QPushButton("Undo")
        self.reset_button = QPushButton("Reset")
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
        status_layout.addWidget(status_title)
        status_layout.addWidget(self.status_label)
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
            button = QPushButton("Choose ROOT folder")
            button.clicked.connect(self.browse_root)
            self.root_button = button
            self.root_badge = badge
        else:
            button = QPushButton("Choose CSV file")
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
                background: #2bd0b7;
                color: white;
            }
            QPushButton#Accent:hover {
                background: #22b6a0;
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
                background: #2bd0b7;
                color: white;
                font-size: 12px;
                font-weight: 600;
                padding: 10px 14px;
                text-align: left;
            }
            QPushButton#PickerActive:hover {
                background: #22b6a0;
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
                background: #2bd0b7;
                color: white;
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
            self.root_button.setObjectName("PickerActive")
            self.root_badge.setText("Selected")
            self.root_badge.setObjectName("BadgeActive")
        else:
            self.root_button.setText("Choose ROOT folder")
            self.root_button.setObjectName("Picker")
            self.root_badge.setText("Not selected")
            self.root_badge.setObjectName("BadgeIdle")

        if self.csv_path:
            self.csv_button.setText(f"Selected: {shorten_path(self.csv_path, 'CSV')}")
            self.csv_button.setObjectName("PickerActive")
            self.csv_badge.setText("Selected")
            self.csv_badge.setObjectName("BadgeActive")
        else:
            self.csv_button.setText("Choose CSV file")
            self.csv_button.setObjectName("Picker")
            self.csv_badge.setText("Not selected")
            self.csv_badge.setObjectName("BadgeIdle")

        self._refresh_styles(self.root_button, self.csv_button, self.root_badge, self.csv_badge)

    def update_mode_state(self):
        self.standard_mode_button.setChecked(self.mode_label == "Standard mode")
        self.artwork_mode_button.setChecked(self.mode_label == "Artwork batch mode")
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
