import os
import sys

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QBrush, QFont, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from eigengen import meld, utils
from eigengen.chat import EggChat
from eigengen.chat_area_widget import ChatAreaWidget
from eigengen.chat_input_widget import ChatInputWidget
from eigengen.chat_worker import ChatWorker
from eigengen.config import EggConfig
from eigengen.context_manager import FileBrowserContextWidget


class EggChatGUI(QMainWindow):
    def __init__(self, config: EggConfig, parent: QWidget | None):
        super().__init__(parent)
        # Load background image.
        from importlib.resources import files
        try:
            bg_path = files("eigengen.assets").joinpath("background.webp")
            bg_pixmap = QPixmap(str(bg_path))
            if not bg_pixmap.isNull():
                palette = self.palette()
                palette.setBrush(QPalette.Window, QBrush(bg_pixmap))
                self.setPalette(palette)
                self.setAutoFillBackground(True)
        except Exception as e:
            print(f"Failed to load background image: {e}")

        # Set application icon.
        try:
            icon_path = files("eigengen.assets").joinpath("egg_icon.png")
            icon_pixmap = QPixmap(str(icon_path))
            if not icon_pixmap.isNull():
                self.setWindowIcon(QIcon(icon_pixmap))
        except Exception as ex:
            print(f"Failed to load egg icon: {ex}")

        self.setWindowTitle("EggChat GUI")
        self.resize(800, 600)
        if config is None:
            config = EggConfig()
        self.eggchat = EggChat(config, user_files=None)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Left panel: File browser and selected files.
        left_panel = QWidget()
        left_panel.setStyleSheet("background-color: rgba(0, 0, 0, 200);")
        left_layout = QVBoxLayout(left_panel)
        self.file_browser = FileBrowserContextWidget()
        self.file_browser.setStyleSheet("background-color: rgba(0, 0, 0, 0)")
        self.file_browser.fileDoubleClicked.connect(self._on_file_double_clicked)
        left_layout.addWidget(self.file_browser)


        # Right panel: Chat area and input area.
        self.chat_area_widget = ChatAreaWidget()
        self.chat_input_widget = ChatInputWidget()
        self.chat_input_widget.send_message.connect(self._send_message)
        self.chat_input_widget.clear_chat.connect(self._clear_chat)

        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: rgba(0, 0, 0, 200);")
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(self.chat_area_widget, 2)
        right_layout.addWidget(self.chat_input_widget, 1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([200, 600])

    @Slot(str)
    def _on_file_double_clicked(self, file_path: str) -> None:
        """
        Load the content of the double-clicked file as a quoted message.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            quoted_content = "\n".join("> " + line for line in content.splitlines())
            self.chat_input_widget.input_edit.setPlainText(quoted_content)
        except Exception as e:
            error_msg = f"Error reading file {file_path}: {str(e)}"
            self.chat_area_widget.append_message("system", error_msg)

    @Slot(str)
    def _send_message(self, user_message: str) -> None:
        """
        Append the user message to the chat and start a ChatWorker
        to retrieve the assistant response.
        """
        self.chat_area_widget.append_message("user", user_message)
        self._start_chat_worker(user_message)

    def _start_chat_worker(self, user_message: str) -> None:
        self.chat_input_widget.send_button.setEnabled(False)
        self.worker = ChatWorker(self.eggchat, user_message)
        self.worker.result_ready.connect(self._display_assistant_response)
        self.worker.finished.connect(lambda: self.chat_input_widget.send_button.setEnabled(True))
        self.worker.start()

    @Slot(str)
    def _display_assistant_response(self, response: str) -> None:
        self.chat_area_widget.append_message("assistant", response)
        changes = utils.extract_change_descriptions(response)
        if changes:
            meld_button = QPushButton("Apply Meld")
            meld_button.clicked.connect(lambda: self._open_meld_dialog(changes, meld_button))
            self.chat_area_widget.chat_layout.addWidget(meld_button)
            self.chat_area_widget.scroll_to_bottom()

    def _open_meld_dialog(self, changes, trigger_button: QPushButton) -> None:
        diff_results = []
        for file_path, change_list in changes.items():
            aggregated_changes = "\n".join(change_list)
            try:
                original_content = ""
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        original_content = f.read()
                new_content, diff_text = meld.get_merged_content_and_diff(
                    self.eggchat.pm, file_path, original_content, aggregated_changes
                )
                diff_results.append((file_path, new_content, diff_text))
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Error Processing File",
                    f"Could not process changes for {file_path}: {str(e)}"
                )
        if not diff_results:
            QMessageBox.information(self, "No Changes", "No valid changes to apply.")
            return
        combined_diff = ""
        for file_path, _, diff_text in diff_results:
            combined_diff += f"--- Changes for: {file_path} ---\n{diff_text}\n"
        dialog = QDialog(self)
        dialog.setWindowTitle("Meld Diff Preview")
        dialog.setModal(True)
        dialog_layout = QVBoxLayout(dialog)
        description_label = QLabel("Review the diff changes below:")
        dialog_layout.addWidget(description_label)
        diff_display = QPlainTextEdit(dialog)
        diff_display.setReadOnly(True)
        # Set fixed width font for the diff display widget based on the operating system.
        if sys.platform.startswith("darwin"):
            font_name = "SF Mono"
        elif sys.platform.startswith("win"):
            font_name = "Consolas"
        else:
            font_name = "Monospace"
        diff_display.setFont(QFont(font_name))
        diff_display.setPlainText(combined_diff)
        diff_display.setStyleSheet("background-color: rgba(0, 0, 0, 230);")
        dialog_layout.addWidget(diff_display)
        button_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply Changes", dialog)
        cancel_btn = QPushButton("Cancel", dialog)
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(cancel_btn)
        dialog_layout.addLayout(button_layout)
        apply_btn.clicked.connect(lambda: self._apply_meld_changes(diff_results, dialog, trigger_button))
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def _apply_meld_changes(self, diff_results, dialog: QDialog, trigger_button: QPushButton) -> None:
        success_count = 0
        for file_path, new_content, _ in diff_results:
            try:
                meld.apply_new_content(file_path, new_content)
                success_count += 1
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to apply changes to {file_path}:\n{str(e)}")
        if success_count > 0:
            QMessageBox.information(
                self,
                "Changes Applied",
                f"Successfully applied changes to {success_count} file(s)."
            )
            dialog.accept()
            trigger_button.setEnabled(False)
        else:
            QMessageBox.warning(self, "No Changes Applied", "Failed to apply any changes.")

    @Slot()
    def _clear_chat(self) -> None:
        self.chat_area_widget.clear_messages()
        self.eggchat.messages = []
