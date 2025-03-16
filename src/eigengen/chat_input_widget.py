from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


class ChatInputWidget(QWidget):
    send_message = Signal(str)
    clear_chat = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("Type your message here...")
        self.input_edit.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        layout.addWidget(self.input_edit)

        btn_layout = QHBoxLayout()
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send_clicked)
        btn_layout.addWidget(self.send_button)

        self.clear_button = QPushButton("Clear Chat")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        btn_layout.addWidget(self.clear_button)
        layout.addLayout(btn_layout)

    def _on_send_clicked(self):
        text = self.input_edit.toPlainText().strip()
        if text:
            self.send_message.emit(text)
            self.input_edit.clear()

    def _on_clear_clicked(self):
        self.clear_chat.emit()
