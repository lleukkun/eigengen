import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget
from superqt.utils import CodeSyntaxHighlight

from eigengen.utils import extract_code_blocks


class CodeBlockWidget(QTextEdit):
    def __init__(self, content: str, lang: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0);")
        self.setPlainText(content)
        self.setReadOnly(True)  # Disable editing in the code block widget

        if sys.platform.startswith("darwin"):
            font_name = "Menlo"
        elif sys.platform.startswith("win"):
            font_name = "Consolas"
        else:
            font_name = "Monospace"
        self.setFont(QFont(font_name))
        self.lang = lang
        self.highlighter = CodeSyntaxHighlight(self.document(), lang=self.lang, theme="solarized-dark")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.document().contentsChanged.connect(self._updateSize)

    def _updateSize(self):
        self.document().setTextWidth(self.viewport().width())
        self.updateGeometry()
        self.adjustSize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.document().setTextWidth(self.viewport().width())
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        self.document().setTextWidth(self.viewport().width())
        doc_size = self.document().documentLayout().documentSize()
        margins = self.contentsMargins().top() + self.contentsMargins().bottom()
        frame = int(self.frameWidth() * 2)
        total_height = int(doc_size.height() + margins + frame)
        return QSize(self.width(), total_height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


class ChatMessageWidget(QWidget):
    def __init__(self, sender: str, message: str, parent: QWidget = None):
        super().__init__(parent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0);")
        layout = QVBoxLayout(self)
        header = QLabel(f"<b>[{sender.capitalize()}]</b>")
        layout.addWidget(header)

        code_blocks = extract_code_blocks(message)
        last_index = 0

        if not code_blocks:
            if message.strip():
                text_label = QLabel(message.replace("\n", "<br>"))
                text_label.setWordWrap(True)
                layout.addWidget(text_label)
        else:
            for block in code_blocks:
                text_segment = message[last_index:block.start_index]
                if text_segment.strip():
                    text_label = QLabel(text_segment.replace("\n", "<br>"))
                    text_label.setWordWrap(True)
                    layout.addWidget(text_label)
                code_widget = CodeBlockWidget(block.content, block.lang)
                layout.addWidget(code_widget)
                last_index = block.end_index

            remaining_text = message[last_index:]
            if remaining_text.strip():
                text_label = QLabel(remaining_text.replace("\n", "<br>"))
                text_label.setWordWrap(True)
                layout.addWidget(text_label)
