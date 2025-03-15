import html
import os
import sys

from PySide6.QtCore import QModelIndex, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from superqt.utils import CodeSyntaxHighlight
from eigengen.utils import extract_code_blocks  # Added import for extract_code_blocks

from eigengen.chat import EggChat
from eigengen.config import EggConfig  # Assuming EggConfig can be instantiated with defaults


class CodeBlockWidget(QPlainTextEdit):
    def __init__(self, code_text: str, lang: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setPlainText(code_text)
        self.setReadOnly(True)
        self.setFont(QFont("Courier", 10))

        # Attach the superqt syntax highlighter.
        # Use provided language (defaulting to "python" if none is given) and "monokai" style.
        self.highlight = CodeSyntaxHighlight(self.document(), lang if lang else "python", "monokai")

        # Update the text edit palette with the highlighter's background color.
        palette = self.palette()
        palette.setColor(QPalette.Base, QColor(self.highlight.background_color))
        self.setPalette(palette)

class ChatMessageWidget(QWidget):
    def __init__(self, sender: str, message: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        # Header indicating the sender.
        header = QLabel(f"<b>[{sender.capitalize()}]</b>")
        layout.addWidget(header)
        
        # Use the same extract_code_blocks() as in chat.py to parse code blocks.
        code_blocks = extract_code_blocks(message)
        last_index = 0

        if not code_blocks:
            # If no code blocks were found, display the entire message as regular text.
            if message.strip():
                text_label = QLabel(message.replace("\n", "<br>"))
                text_label.setWordWrap(True)
                layout.addWidget(text_label)
        else:
            # Loop through each detected code block.
            for block in code_blocks:
                # Get any text before the code block and add it as a QLabel.
                text_segment = message[last_index:block.start_index]
                if text_segment.strip():
                    text_label = QLabel(text_segment.replace("\n", "<br>"))
                    text_label.setWordWrap(True)
                    layout.addWidget(text_label)
                # Instantiate a CodeBlockWidget using the extracted code and language information.
                code_widget = CodeBlockWidget(block.content, block.lang)
                layout.addWidget(code_widget)
                last_index = block.end_index

            # Append any text that follows after the last code block.
            remaining_text = message[last_index:]
            if remaining_text.strip():
                text_label = QLabel(remaining_text.replace("\n", "<br>"))
                text_label.setWordWrap(True)
                layout.addWidget(text_label)
        
        layout.addStretch()

class ChatWorker(QThread):
    """
    A QThread subclass that runs the EggChat._get_answer method on a background thread.
    Once the assistant's response is retrieved, it emits the resultReady signal.
    """
    result_ready = Signal(str)

    def __init__(self, eggchat: EggChat, user_message: str, parent=None):
        super().__init__(parent)
        self.eggchat = eggchat
        self.user_message = user_message

    def run(self):
        # Call the EggChat method to get the answer (blocking call)
        answer = self.eggchat._get_answer(self.user_message, use_progress=False)
        self.result_ready.emit(answer)


def html_format_message(sender: str, message: str) -> str:
    """
    Format a message as HTML for display in the QTextEdit, following the app's light/dark theme.

    This function escapes HTML characters, replaces newline characters with <br> tags,
    and converts text enclosed in triple backticks into a styled <pre> block—with colors
    dynamically selected based on whether the app is using a light or dark theme.
    """
    # Determine the current theme (light or dark) by inspecting the application's palette.
    app = QApplication.instance()
    is_dark = False
    if app:
        palette = app.palette()
        bg_color = palette.color(QPalette.Window)
        # Calculate brightness using the luminance formula.
        brightness = 0.299 * bg_color.red() + 0.587 * bg_color.green() + 0.114 * bg_color.blue()
        is_dark = brightness < 128

    # Set colors based on the detected theme.
    if is_dark:
        user_color = "#82AAFF"         # Light blue for user messages in dark mode.
        assistant_color = "#C3E88D"    # Light green for assistant messages in dark mode.
        code_bg = "#3C3F41"            # Darker background for code blocks.
        code_text = "#FFFFFF"          # White text for code blocks.
    else:
        user_color = "blue"            # Blue for user messages in light mode.
        assistant_color = "green"      # Green for assistant messages in light mode.
        code_bg = "#f0f0f0"            # Light grey background for code blocks.
        code_text = "black"            # Black text for code blocks.

    color = user_color if sender.lower() == "user" else assistant_color

    # Escape HTML characters in the message.
    escaped = html.escape(message)
    # Split the message on triple backticks to detect code block sections.
    parts = escaped.split("```")
    formatted = ""
    for idx, part in enumerate(parts):
        if idx % 2 == 0:
            # In non-code segments, replace newline characters with <br> tags.
            formatted += part.replace("\n", "<br>")
        else:
            # Wrap code blocks in a preformatted block with the chosen styles.
            formatted += f'<pre style="background-color:{code_bg}; color:{code_text}; padding:5px; border-radius:4px;">{part}</pre>'
    return f'<p style="color:{color}; margin:5px;"><b>[{sender.capitalize()}]</b> {formatted}</p>'


class EggChatGUI(QMainWindow):
    """
    EggChatGUI provides a graphical interface for interacting with EggChat.

    The main window is split horizontally. The left panel provides a file explorer (using a
    QTreeView) for browsing the current working directory. Double-clicking a file in the tree
    loads its contents into the input area as a quoted message (mimicking the /quote command).
    The right panel shows the conversation (using a read-only QTextEdit) plus a multi-line input
    area and buttons to send a message and clear the chat.
    """
    def __init__(self, config: EggConfig|None = None, parent: QWidget|None = None):
        super().__init__(parent)
        self.setWindowTitle("EggChat GUI")
        self.resize(800, 600)

        # Initialize EggChat instance; if no configuration is provided, create a default one.
        if config is None:
            config = EggConfig()  # TODO: Customize configuration as needed.
        self.eggchat = EggChat(config, user_files=None)

        # Set up the central widget and layout.
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)

        # Create a horizontal splitter to divide the file explorer (left) and chat area (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # ---- Left Panel: File Explorer ----
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        splitter.addWidget(left_panel)

        file_label = QLabel("File Explorer")
        left_layout.addWidget(file_label)

        self.tree_view = QTreeView()
        left_layout.addWidget(self.tree_view)

        # Set up the filesystem model to browse the current directory
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(os.getcwd())
        self.tree_view.setModel(self.fs_model)
        # Hide extra columns so only the name is displayed
        for i in range(1, self.fs_model.columnCount()):
            self.tree_view.hideColumn(i)
        self.tree_view.setRootIndex(self.fs_model.index(os.getcwd()))
        self.tree_view.setSortingEnabled(True)
        self.tree_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree_view.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        # Connect double-click events to load the file as a quoted message
        self.tree_view.doubleClicked.connect(self.on_file_double_clicked)

        instruction = QLabel("Double-click a file to load its content as a quote.")
        left_layout.addWidget(instruction)

        # ---- Right Panel: Chat Area ----
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_panel.setLayout(right_layout)
        splitter.addWidget(right_panel)

        # Conversation area: a scrollable widget containing individual message widgets.
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_scroll_area = QScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setWidget(self.chat_container)
        right_layout.addWidget(self.chat_scroll_area)

        # Input area for typing messages (plain text)
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("Type your message here...")
        right_layout.addWidget(self.input_edit)

        # Buttons for sending messages and clearing chat history
        btn_layout = QHBoxLayout()
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        btn_layout.addWidget(self.send_button)

        self.clear_button = QPushButton("Clear Chat")
        self.clear_button.clicked.connect(self.clear_chat)
        btn_layout.addWidget(self.clear_button)
        right_layout.addLayout(btn_layout)

        splitter.setSizes([200, 600])

    @Slot(QModelIndex)  # type: ignore
    def on_file_double_clicked(self, index: QModelIndex) -> None:
        """
        Load the selected file’s content into the input area as a quoted message.

        This mimics the /quote command of the terminal UI.
        """
        if not self.fs_model.isDir(index):
            file_path = self.fs_model.filePath(index)
            if os.path.isfile(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    quoted_content = "\n".join("> " + line for line in content.splitlines())
                    self.input_edit.setPlainText(quoted_content)
                except Exception:
                    self.chat_container.layout().addWidget(QLabel(f"<p style='color:red;'>Error reading file: {file_path}</p>"))

    @Slot()
    def send_message(self):
        """
        Retrieve the message from the input area, add it to the conversation, and use a background
        worker to obtain the assistant’s reply. The send button is disabled until the response is ready.
        """
        user_message = self.input_edit.toPlainText().strip()
        if not user_message:
            return

        self.append_chat_message("user", user_message)
        self.input_edit.clear()

        # Disable the send button while processing.
        self.send_button.setEnabled(False)
        # Create and start the ChatWorker to get the assistant's answer.
        self.worker = ChatWorker(self.eggchat, user_message)
        self.worker.result_ready.connect(self.display_assistant_response)
        self.worker.finished.connect(lambda: self.send_button.setEnabled(True))
        self.worker.start()

    @Slot(str)  # type: ignore
    def display_assistant_response(self, response: str) -> None:
        """
        Append the assistant's response to the chat display with basic syntax highlighting.
        """
        self.append_chat_message("assistant", response)

    def append_chat_message(self, sender: str, message: str) -> None:
        """
        Create and append a ChatMessageWidget for the given sender and message.
        Afterwards, auto-scroll to the bottom of the conversation.
        """
        msg_widget = ChatMessageWidget(sender, message)
        self.chat_layout.addWidget(msg_widget)
        # Auto-scroll to the bottom.
        vsb = self.chat_scroll_area.verticalScrollBar()
        vsb.setValue(vsb.maximum())

    @Slot()
    def clear_chat(self):
        """
        Clear the conversation display and reset the EggChat message history.
        """
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.eggchat.messages = []


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EggChatGUI()
    window.show()
    sys.exit(app.exec())
