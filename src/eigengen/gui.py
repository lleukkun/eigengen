import os
import sys
from typing import Dict, List, Optional, Set, Tuple, cast

from PySide6.QtCore import QEvent, QModelIndex, QRect, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from qtpy.QtCore import QPersistentModelIndex
from superqt.utils import CodeSyntaxHighlight

from eigengen import meld, utils
from eigengen.chat import EggChat
from eigengen.config import EggConfig
from eigengen.utils import extract_code_blocks


class CodeBlockWidget(QPlainTextEdit):
    """A widget for displaying syntax-highlighted code blocks."""

    def __init__(self, code_text: str, lang: str = "", parent: Optional[QWidget] = None):
        """
        Initialize a code block widget with syntax highlighting.

        Args:
            code_text: The code content to display
            lang: The programming language for syntax highlighting (defaults to python)
            parent: The parent widget
        """
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
    """A widget representing a single chat message with support for code blocks."""

    def __init__(self, sender: str, message: str, parent: Optional[QWidget] = None):
        """
        Initialize a chat message widget.

        Args:
            sender: The name of the message sender (user or assistant)
            message: The content of the message
            parent: The parent widget
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        # Header indicating the sender.
        header = QLabel(f"<b>[{sender.capitalize()}]</b>")
        layout.addWidget(header)

        # Use the extract_code_blocks() to parse code blocks.
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

    def __init__(self, eggchat: EggChat, user_message: str, parent: Optional[QWidget] = None):
        """
        Initialize the worker thread.

        Args:
            eggchat: The EggChat instance to use for getting responses
            user_message: The user message to process
            parent: The parent widget
        """
        super().__init__(parent)
        self.eggchat = eggchat
        self.user_message = user_message

    def run(self) -> None:
        """Execute the chat request on a background thread."""
        # Call the EggChat method to get the answer (blocking call)
        answer = self.eggchat._get_answer(self.user_message, use_progress=False)
        self.result_ready.emit(answer)


class FileSelectionDelegate(QStyledItemDelegate):
    """
    A delegate for rendering file items in the tree view with selection buttons.
    """

    def __init__(self, is_selected_callback, toggle_callback, parent=None):
        """
        Initialize the delegate.

        Args:
            is_selected_callback: Function to check if a file is selected
            toggle_callback: Function to toggle file selection
            parent: The parent widget
        """
        super().__init__(parent)
        self.is_selected_callback = is_selected_callback
        self.toggle_callback = toggle_callback
        self.button_size = 20
        self.margin = 4

    def paint(self, painter: QPainter,
              option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        """
        Paint the item with a selection button.

        Args:
            painter: The QPainter to use
            option: The style options
            index: The model index of the item
        """
        # Obtain the file path from the model.
        file_path = cast(QFileSystemModel, index.model()).filePath(index)
        selected = self.is_selected_callback(file_path)

        # Adjust the text rectangle to leave room for the custom button.
        option2 = QStyleOptionViewItem(option)
        option2.rect = QRect(option.rect)
        option2.rect.setLeft(option.rect.left() + self.button_size + self.margin * 2)
        super().paint(painter, option2, index)

        # Define the button rectangle.
        button_rect = QRect(
            option.rect.left() + self.margin,
            option.rect.top() + (option.rect.height() - self.button_size) // 2,
            self.button_size,
            self.button_size,
        )

        # Prepare the button parameters.
        blue = QColor(0, 120, 215)
        symbol = "-" if selected else "+"

        painter.save()
        # Use QPainter.Antialiasing correctly.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Draw the blue button background.
        painter.setBrush(blue)
        painter.setPen(Qt.PenStyle.NoPen)
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
        painter.setPen(Qt.GlobalColor.white)
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(button_rect, Qt.AlignmentFlag.AlignCenter, symbol)
        painter.restore()

    def editorEvent(self, event: QEvent, model: QFileSystemModel, option: QStyleOptionViewItem,
                   index: QModelIndex) -> bool:
        """
        Handle mouse events on the delegate.

        Args:
            event: The event to process
            model: The model containing the data
            option: The style options
            index: The model index of the item

        Returns:
            True if the event was handled, False otherwise
        """
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            indicator_rect = QRect(
                option.rect.left() + self.margin,
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
    def __init__(self, config: Optional[EggConfig] = None, parent: Optional[QWidget] = None):
        """
        Initialize the EggChat GUI.

        Args:
            config: The EggConfig to use (creates a default if None)
            parent: The parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("EggChat GUI")
        self.resize(800, 600)

        # Initialize EggChat instance; if no configuration is provided, create a default one.
        if config is None:
            config = EggConfig()
        self.eggchat = EggChat(config, user_files=None)

        # Set up the central widget and layout.
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)

        # Create a horizontal splitter to divide the file explorer (left) and chat area (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Initialize data structures for managing selected files.
        self.selected_files: Set[str] = set()
        self.selected_file_widgets: Dict[str, QWidget] = {}

        # Setup left and right panels
        left_panel = self._setup_left_panel()
        right_panel = self._setup_right_panel()

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([200, 600])

    def _setup_left_panel(self) -> QWidget:
        """
        Create and configure the left panel with file selection and explorer.

        Returns:
            The configured left panel widget
        """
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)

        # Selected Files Section
        selected_files_label = QLabel("Selected Files")
        left_layout.addWidget(selected_files_label)

        self.selected_files_container = QWidget()
        self.selected_files_layout = QVBoxLayout(self.selected_files_container)
        self.selected_files_layout.setContentsMargins(0, 0, 0, 0)
        self.selected_files_layout.setSpacing(0)  # Set spacing to zero for a compact list.
        left_layout.addWidget(self.selected_files_container)

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
        self.tree_view.doubleClicked.connect(self._on_file_double_clicked)

        # Set the custom delegate to display a plus/minus button on each file item.
        self.tree_view.setItemDelegateForColumn(0, FileSelectionDelegate(
            is_selected_callback=self.is_file_selected,
            toggle_callback=self.toggle_file_selection
        ))

        instruction = QLabel("Double-click a file to load its content as a quote.")
        left_layout.addWidget(instruction)

        return left_panel

    def _setup_right_panel(self) -> QWidget:
        """
        Create and configure the right panel with chat display and controls.

        Returns:
            The configured right panel widget
        """
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_panel.setLayout(right_layout)

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
        self.send_button.clicked.connect(self._send_message)
        btn_layout.addWidget(self.send_button)

        self.clear_button = QPushButton("Clear Chat")
        self.clear_button.clicked.connect(self._clear_chat)
        btn_layout.addWidget(self.clear_button)
        right_layout.addLayout(btn_layout)

        return right_panel

    @Slot(QModelIndex)
    def _on_file_double_clicked(self, index: QModelIndex) -> None:
        """
        Load the selected file's content into the input area as a quoted message.

        This mimics the /quote command of the terminal UI.

        Args:
            index: The model index of the clicked file
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
                    error_msg = f"<p style='color:red;'>Error reading file {file_path}: {str(e)}</p>"
                    self.chat_layout.addWidget(QLabel(error_msg))

    @Slot()
    def _send_message(self) -> None:
        """
        Retrieve the message from the input area, add it to the conversation, and use a background
        worker to obtain the assistant's reply. The send button is disabled until the response is ready.
        """
        user_message = self.input_edit.toPlainText().strip()
        if not user_message:
            return

        self._append_chat_message("user", user_message)
        self.input_edit.clear()

        # Disable the send button while processing.
        self.send_button.setEnabled(False)
        # Create and start the ChatWorker to get the assistant's answer.
        self.worker = ChatWorker(self.eggchat, user_message)
        self.worker.result_ready.connect(self._display_assistant_response)
        self.worker.finished.connect(lambda: self.send_button.setEnabled(True))
        self.worker.start()

    @Slot(str)
    def _display_assistant_response(self, response: str) -> None:
        """
        Append the assistant's response to the chat display with basic syntax highlighting.
        If the response contains change descriptions, add an 'Apply Meld' button below the message.

        Args:
            response: The assistant's response text
        """
        self._append_chat_message("assistant", response)
        # Check for change descriptions (using the extraction helper).
        changes = utils.extract_change_descriptions(response)
        if changes:
            meld_button = QPushButton("Apply Meld")
            meld_button.clicked.connect(lambda: self._open_meld_dialog(changes, meld_button))
            self.chat_layout.addWidget(meld_button)
            # Auto-scroll after adding the button.
            self._scroll_to_bottom()

    def _open_meld_dialog(self, changes: Dict[str, List[str]], trigger_button: QPushButton) -> None:
        """
        Opens a modal dialog showing the proposed diff(s) for each file found in the change descriptions.
        The user can review the diff and click 'Apply Changes' or 'Cancel'.
        After applying, the triggering button is disabled.

        Args:
            changes: Dictionary mapping file paths to lists of change descriptions
            trigger_button: The button that triggered the dialog
        """
        diff_results = []
        # Process each file from the change descriptions.
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

    def _apply_meld_changes(self, diff_results: List[Tuple[str, str, str]],
                           dialog: QDialog, trigger_button: QPushButton) -> None:
        """
        Applies the changes for each file by writing the new content to disk,
        then closes the dialog and disables the trigger button.

        Args:
            diff_results: List of tuples containing (file_path, new_content, diff_text)
            dialog: The dialog to close after applying changes
            trigger_button: The button to disable after applying changes
        """
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

    def _append_chat_message(self, sender: str, message: str) -> None:
        """
        Create and append a ChatMessageWidget for the given sender and message.
        Afterwards, auto-scroll to the bottom of the conversation.

        Args:
            sender: The name of the message sender (user or assistant)
            message: The content of the message
        """
        msg_widget = ChatMessageWidget(sender, message)
        self.chat_layout.addWidget(msg_widget)
        # Auto-scroll to the bottom.
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        """Scroll the chat area to the bottom to show the latest messages."""
        vsb = self.chat_scroll_area.verticalScrollBar()
        vsb.setValue(vsb.maximum())

    @Slot()
    def _clear_chat(self) -> None:
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

        Args:
            file_path: The path of the file to check

        Returns:
            True if the file is selected, False otherwise
        """
        return file_path in self.selected_files

    def toggle_file_selection(self, file_path: str) -> None:
        """
        Toggle the selection state of the given file.
        If the file is selected, remove it; otherwise, add it.
        Updates both the UI list and refreshes the file browser display.

        Args:
            file_path: The path of the file to toggle
        """
        if file_path in self.selected_files:
            self._remove_selected_file(file_path)
        else:
            self._add_selected_file(file_path)
        # Force an update of the tree view so that the delegate repaints the selection indicator.
        self.tree_view.viewport().update()

    def _add_selected_file(self, file_path: str) -> None:
        """
        Add the given file to the selected files list and update the UI.

        Args:
            file_path: The path of the file to add
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
        remove_button.clicked.connect(lambda: self._remove_selected_file(file_path))
        layout.addWidget(remove_button)

        self.selected_files_layout.addWidget(file_item)
        self.selected_file_widgets[file_path] = file_item

    def _remove_selected_file(self, file_path: str) -> None:
        """
        Remove the given file from the selected files list and update the UI.

        Args:
            file_path: The path of the file to remove
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
