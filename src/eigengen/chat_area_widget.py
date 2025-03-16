from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from eigengen.chat_widgets import ChatMessageWidget


class ChatAreaWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.chat_scroll_area = QScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setWidget(self.chat_container)
        self.chat_scroll_area.setStyleSheet("background-color: rgba(0, 0, 0, 100);")

        layout.addWidget(self.chat_scroll_area)

    def append_message(self, sender: str, message: str):
        msg_widget = ChatMessageWidget(sender, message)
        self.chat_layout.addWidget(msg_widget)
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        vsb = self.chat_scroll_area.verticalScrollBar()
        vsb.setValue(vsb.maximum())

    def clear_messages(self):
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
