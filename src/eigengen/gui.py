import os
import sys

from PySide6.QtCore import QEvent, QModelIndex, QRect, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPalette, QPainter  # <-- Added QPainter import
from PySide6.QtWidgets import (
    QApplication,
    QDialog,  # <-- added for modal dialogs
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,  # <-- added for error reporting
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,  # <-- added to adjust option rect in delegate
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from superqt.utils import CodeSyntaxHighlight

from eigengen import meld, utils  # <-- added access to meld functions
from eigengen.chat import EggChat
from eigengen.config import EggConfig  # Assuming EggConfig can be instantiated with defaults
from eigengen.utils import extract_code_blocks  # Added import for extract_code_blocks


class CodeBlockWidget(QPlainTextEdit):
    def __init__(self, code_text: str, lang: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setPlainText(code_text)
        self.setReadOnly(True)
        # Use a generic fixed-width font to prevent runtime font aliasing cost on macOS.
        self.setFont(QFont("Monospace", 10))

        # Attach the superqt syntax highlighter.
        # Use provided language (defaulting to "python" if none is given) and "monokai" style.
        self.highlight = CodeSyntaxHighlight(self.document(), lang if lang else "python", "monokai")

        # Update the text edit palette with the highlighter's background color.
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(self.highlight.background_color))
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

class FileSelectionDelegate(QStyledItemDelegate):
    def __init__(self, is_selected_callback, toggle_callback, parent=None):
        super().__init__(parent)
        self.is_selected_callback = is_selected_callback
        self.toggle_callback = toggle_callback
        self.button_size = 20

    def paint(self, painter, option, index):
        # Obtain the file path from the model.
        file_path = index.model().filePath(index)
        selected = self.is_selected_callback(file_path)
        margin = 4

        # Adjust the text rectangle to leave room for the custom button.
        option2 = QStyleOptionViewItem(option)
        option2.rect = QRect(option.rect)
        option2.rect.setLeft(option.rect.left() + self.button_size + margin * 2)
        super().paint(painter, option2, index)

        # Define the button rectangle.
        button_rect = QRect(
            option.rect.left() + margin,
            option.rect.top() + (option.rect.height() - self.button_size) // 2,
            self.button_size,
            self.button_size,
        )

        # Prepare the button parameters.
        blue = QColor(0, 120, 215)
        symbol = "-" if selected else "+"

        painter.save()
        # Use QPainter.Antialiasing correctly.
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Draw the blue button background.
        painter.setBrush(blue)
        painter.setPen(Qt.NoPen)
        painter.drawRect(button_rect)

        # Optionally, draw a light bevel effect.
        highlight = blue.lighter(120)
        shadow = blue.darker(120)
        painter.setPen(highlight)
        painter.drawLine(button_rect.topLeft(), button_rect.topRight())
        painter.drawLine(button_rect.topLeft(), button_rect.bottomLeft())
        painter.setPen(shadow)
        painter.drawLine(button_rect.bottomLeft(), button_rect.bottomRight())
        painter.drawLine(button_rect.topRight(), button_rect.bottomRight())

        # Draw the appropriate symbol in white, using a bold font.
        painter.setPen(Qt.white)
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(button_rect, Qt.AlignCenter, symbol)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        # Use Qt.LeftButton (the preferred enum) instead of Qt.MouseButton.LeftButton.
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            margin = 4
            indicator_rect = QRect(
                option.rect.left() + margin,
                option.rect.top() + (option.rect.height() - self.button_size) // 2,
                self.button_size,
                self.button_size,
            )
            if indicator_rect.contains(event.pos()):
                file_path = model.filePath(index)
                self.toggle_callback(file_path)
                return True
        return super().editorEvent(event, model, option, index)

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

        # ---- Left Panel: File Explorer and Selected Files ----
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        splitter.addWidget(left_panel)

        # Selected Files Section
        selected_files_label = QLabel("Selected Files")
        left_layout.addWidget(selected_files_label)

        self.selected_files_container = QWidget()
        self.selected_files_layout = QVBoxLayout(self.selected_files_container)
        self.selected_files_layout.setContentsMargins(0, 0, 0, 0)
        self.selected_files_layout.setSpacing(0)  # Set spacing to zero for a compact list.
        left_layout.addWidget(self.selected_files_container)

        # Initialize data structures for managing selected files.
        self.selected_files = set()
        self.selected_file_widgets = {}

        # File Explorer Section
        file_label = QLabel("File Explorer")
        left_layout.addWidget(file_label)

        self.tree_view = QTreeView()
        left_layout.addWidget(self.tree_view)

        # Set up the filesystem model to browse the current directory.
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(os.getcwd())
        self.tree_view.setModel(self.fs_model)
        for i in range(1, self.fs_model.columnCount()):
            self.tree_view.hideColumn(i)
        self.tree_view.setRootIndex(self.fs_model.index(os.getcwd()))
        self.tree_view.setSortingEnabled(True)
        self.tree_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree_view.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.tree_view.doubleClicked.connect(self.on_file_double_clicked)

        # Set the custom delegate to display a plus/minus button on each file item.
        self.tree_view.setItemDelegateForColumn(0, FileSelectionDelegate(
            is_selected_callback=self.is_file_selected,
            toggle_callback=self.toggle_file_selection
        ))

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
        If the response contains change descriptions, add an 'Apply Meld' button below the message.
        """
        self.append_chat_message("assistant", response)
        # Check for change descriptions (using the extraction helper).
        changes = utils.extract_change_descriptions(response)
        if changes:
            meld_button = QPushButton("Apply Meld")
            meld_button.clicked.connect(lambda: self.open_meld_dialog(changes, meld_button))
            self.chat_layout.addWidget(meld_button)
            # Auto-scroll after adding the button.
            vsb = self.chat_scroll_area.verticalScrollBar()
            vsb.setValue(vsb.maximum())

    def open_meld_dialog(self, changes: dict[str, list[str]], trigger_button: QPushButton) -> None:
        """
        Opens a modal dialog showing the proposed diff(s) for each file found in the change descriptions.
        The user can review the diff and click 'Apply Changes' or 'Cancel'.
        After applying, the triggering button is disabled.
        """
        import os  # Ensure os is imported

        diff_results = []
        # Process each file from the change descriptions.
        for file_path, change_list in changes.items():
            aggregated_changes = "\n".join(change_list)
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        original_content = f.read()
                except Exception:
                    original_content = ""
            else:
                original_content = ""
            new_content, diff_text = meld.get_merged_content_and_diff(
                self.eggchat.pm, file_path, original_content, aggregated_changes
            )
            diff_results.append((file_path, new_content, diff_text))
        # Build a combined diff preview.
        combined_diff = ""
        for file_path, _, diff_text in diff_results:
            combined_diff += f"--- Changes for: {file_path} ---\n"
            combined_diff += diff_text + "\n"

        # Create and set up the modal dialog.
        dialog = QDialog(self)
        dialog.setWindowTitle("Meld Diff Preview")
        dialog.setModal(True)
        dialog_layout = QVBoxLayout(dialog)
        description_label = QLabel("Review the diff changes below:")
        dialog_layout.addWidget(description_label)
        diff_display = QPlainTextEdit(dialog)
        diff_display.setReadOnly(True)
        diff_display.setPlainText(combined_diff)
        dialog_layout.addWidget(diff_display)

        # Create Apply and Cancel buttons.
        button_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply Changes", dialog)
        cancel_btn = QPushButton("Cancel", dialog)
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(cancel_btn)
        dialog_layout.addLayout(button_layout)

        apply_btn.clicked.connect(lambda: self._apply_meld_changes(diff_results, dialog, trigger_button))
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def _apply_meld_changes(self, diff_results: list[tuple[str, str, str]],
                            dialog: QDialog, trigger_button: QPushButton) -> None:
        """
        Applies the changes for each file by writing the new content to disk,
        then closes the dialog and disables the trigger button.
        """
        for file_path, new_content, _ in diff_results:
            try:
                meld.apply_new_content(file_path, new_content)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to apply changes to {file_path}:\n{e}")
        dialog.accept()
        trigger_button.setEnabled(False)

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

    def is_file_selected(self, file_path: str) -> bool:
        """
        Returns True if the given file is currently selected.
        """
        return file_path in self.selected_files

    def toggle_file_selection(self, file_path: str) -> None:
        """
        Toggle the selection state of the given file.
        If the file is selected, remove it; otherwise, add it.
        Updates both the UI list and refreshes the file browser display.
        """
        if file_path in self.selected_files:
            self.remove_selected_file(file_path)
        else:
            self.add_selected_file(file_path)
        # Force an update of the tree view so that the delegate repaints the selection indicator.
        self.tree_view.viewport().update()

    def add_selected_file(self, file_path: str) -> None:
        """
        Add the given file to the selected files list and update the UI.
        """
        if file_path in self.selected_files:
            return
        self.selected_files.add(file_path)
        file_item = QWidget()
        layout = QHBoxLayout(file_item)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)  # Set inner layout spacing to zero for compactness.
        # Display only the base name of the file.
        label = QLabel(os.path.basename(file_path))
        layout.addWidget(label)

        # Create a custom-styled remove button.
        remove_button = QPushButton("-")
        remove_button.setFixedSize(20, 20)
        remove_button.setFlat(True)
        remove_button.setStyleSheet(
            "QPushButton {"
            "background-color: #0078d7;"   # Blue background
            "color: white;"                # White text
            "border: 1px solid #005a9e;"   # Slightly darker border for a bevel effect
            "border-radius: 3px;"
            "padding: 0; margin: 0;"
            "}"
            "QPushButton:pressed {"
            "background-color: #005a9e;"   # Darker blue on press
            "}"
        )
        remove_button.clicked.connect(lambda: self.remove_selected_file(file_path))
        layout.addWidget(remove_button)

        self.selected_files_layout.addWidget(file_item)
        self.selected_file_widgets[file_path] = file_item

    def remove_selected_file(self, file_path: str) -> None:
        """
        Remove the given file from the selected files list and update the UI.
        """
        if file_path not in self.selected_files:
            return
        self.selected_files.remove(file_path)
        widget = self.selected_file_widgets.pop(file_path, None)
        if widget is not None:
            self.selected_files_layout.removeWidget(widget)
            widget.deleteLater()
        # Update the tree view to refresh the selection indicator.
        self.tree_view.viewport().update()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EggChatGUI()
    window.show()
    sys.exit(app.exec())
