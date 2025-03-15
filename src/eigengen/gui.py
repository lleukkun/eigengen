import html
import os
import sys

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from eigengen.chat import EggChat
from eigengen.config import EggConfig  # Assuming EggConfig can be instantiated with defaults


class ChatWorker(QThread):
    """
    A QThread subclass that runs the EggChat._get_answer method on a background thread.
    Once the assistant's response is retrieved, it emits the resultReady signal.
    """
    resultReady = Signal(str)

    def __init__(self, eggchat: EggChat, user_message: str, parent=None):
        super().__init__(parent)
        self.eggchat = eggchat
        self.user_message = user_message

    def run(self):
        # Call the EggChat method to get the answer (blocking call)
        answer = self.eggchat._get_answer(self.user_message, use_progress=False)
        self.resultReady.emit(answer)


def html_format_message(sender: str, message: str) -> str:
    """
    Format a message as HTML for display in the QTextEdit.

    This function escapes HTML characters, replaces newline characters with <br> tags,
    and converts text enclosed in triple backticks into a simple styled <pre> block.
    The sender is highlighted with a color (blue for user, green for assistant).
    """
    escaped = html.escape(message)
    # Split the text on triple backticks to detect code blocks
    parts = escaped.split("```")
    formatted = ""
    for idx, part in enumerate(parts):
        if idx % 2 == 0:
            formatted += part
        else:
            # Wrap detected code blocks in a styled preformatted block.
            formatted += f'<pre style="background-color:#f0f0f0; padding:5px; border-radius:4px;">{part}</pre>'
    color = "blue" if sender.lower() == "user" else "green"
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
    def __init__(self, config: EggConfig = None, parent=None):
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

        # Conversation display (rich-text capable)
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        right_layout.addWidget(self.chat_display)

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

    @Slot()
    def on_file_double_clicked(self, index):
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
                except Exception as e:
                    self.chat_display.append(f"<p style='color:red;'>Error reading file: {file_path}</p>")

    @Slot()
    def send_message(self):
        """
        Retrieve the message from the input area, add it to the conversation, and use a background
        worker to obtain the assistant’s reply. The send button is disabled until the response is ready.
        """
        user_message = self.input_edit.toPlainText().strip()
        if not user_message:
            return

        # Append the user's message to the chat display.
        self.chat_display.append(html_format_message("user", user_message))
        self.input_edit.clear()

        # Disable the send button while processing.
        self.send_button.setEnabled(False)
        # Create and start the ChatWorker to get the assistant's answer.
        self.worker = ChatWorker(self.eggchat, user_message)
        self.worker.resultReady.connect(self.display_assistant_response)
        self.worker.finished.connect(lambda: self.send_button.setEnabled(True))
        self.worker.start()

    @Slot(str)
    def display_assistant_response(self, response: str):
        """
        Append the assistant's response to the chat display with basic syntax highlighting.
        """
        self.chat_display.append(html_format_message("assistant", response))
        # Auto-scroll to the bottom of the chat display.
        self.chat_display.moveCursor(QTextCursor.End)

    @Slot()
    def clear_chat(self):
        """
        Clear the conversation display and reset the EggChat message history.
        """
        self.chat_display.clear()
        self.eggchat.messages = []


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EggChatGUI()
    window.show()
    sys.exit(app.exec())
