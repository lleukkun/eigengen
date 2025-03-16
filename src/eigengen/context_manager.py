import os
from typing import Callable, Dict, Optional, Set

from PySide6.QtCore import QEvent, QModelIndex, QRect, Qt, Signal
from PySide6.QtWidgets import (
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyledItemDelegate,
    QTreeView,
    QVBoxLayout,
    QWidget,
    QStyle, QStyleOptionButton, QStyleOptionViewItem
)
from qtpy.QtCore import QPersistentModelIndex


class FileSelectionDelegate(QStyledItemDelegate):
    """
    A delegate for rendering file items with a custom selection button.
    """
    def __init__(self, is_selected_callback: Callable[[str], bool],
                 toggle_callback: Callable[[str], None],
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.is_selected_callback = is_selected_callback
        self.toggle_callback = toggle_callback
        self.button_size = 20
        self.margin = 4

    def get_item_level(self, index: QModelIndex) -> int:
        level = 0
        while index.parent().isValid():
            level += 1
            index = index.parent()
        return level

    def paint(self, painter, option, index: QModelIndex | QPersistentModelIndex) -> None:
        file_path = index.model().filePath(index)
        selected = self.is_selected_callback(file_path)
        # Compute the item's depth for proper indentation.
        level = self.get_item_level(index)
        base_indent = option.widget.indentation() if option.widget else 20
        effective_indent = base_indent * level

        # Define the checkbox rectangle.
        check_box_rect = QRect(
            option.rect.left() + self.margin + effective_indent,
            option.rect.top() + (option.rect.height() - self.button_size) // 2,
            self.button_size,
            self.button_size,
        )

        # Draw a standard checkbox.
        checkbox_option = QStyleOptionButton()
        checkbox_option.rect = check_box_rect
        checkbox_option.state = QStyle.State_Enabled | (QStyle.State_On if selected else QStyle.State_Off)
        if option.state & QStyle.State_HasFocus:
            checkbox_option.state |= QStyle.State_HasFocus
        option.widget.style().drawControl(QStyle.CE_CheckBox, checkbox_option, painter)

        # Adjust the text rectangle to avoid overlapping with the checkbox.
        text_rect = QRect(option.rect)
        text_rect.setLeft(check_box_rect.right() + self.margin)
        text_option = QStyleOptionViewItem(option)
        text_option.rect = text_rect

        super().paint(painter, text_option, index)

    def editorEvent(self, event: QEvent, model, option, index: QModelIndex) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            level = self.get_item_level(index)
            base_indent = option.widget.indentation() if option.widget else 20
            effective_indent = base_indent * level
            checkbox_rect = QRect(
                option.rect.left() + self.margin + effective_indent,
                option.rect.top() + (option.rect.height() - self.button_size) // 2,
                self.button_size,
                self.button_size,
            )
            if checkbox_rect.contains(event.pos()):
                file_path = model.filePath(index)
                self.toggle_callback(file_path)
                return True
        return super().editorEvent(event, model, option, index)


class FileBrowserContextWidget(QWidget):
    """
    A widget that manages the left-panel file explorer and selected files list.
    Emits a 'fileDoubleClicked' signal when a file (not a directory) is double-clicked.
    """
    fileDoubleClicked = Signal(str)  # emits the file path

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.selected_files: Set[str] = set()
        self.selected_file_widgets: Dict[str, QWidget] = {}

        layout = QVBoxLayout(self)

        # Selected Files Section.
        selected_files_label = QLabel("Selected Files")
        layout.addWidget(selected_files_label)

        self.selected_files_container = QWidget()
        # Changed background color alpha from 0 (fully transparent) to 25 for improved visibility.
        self.selected_files_container.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        self.selected_files_layout = QVBoxLayout(self.selected_files_container)
        self.selected_files_layout.setContentsMargins(0, 0, 0, 0)
        self.selected_files_layout.setSpacing(0)
        layout.addWidget(self.selected_files_container)

        # File Explorer Section.
        file_label = QLabel("File Explorer")
        layout.addWidget(file_label)

        self.tree_view = QTreeView()
        # Changed background color alpha from 0 to 50 for a less transparent appearance.
        self.tree_view.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        # Enable mouse tracking to ensure that our delegate receives mouse events.
        self.tree_view.setMouseTracking(True)
        layout.addWidget(self.tree_view)

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

        # Apply the custom delegate to display a plus/minus selection indicator.
        self.tree_view.setItemDelegateForColumn(0, FileSelectionDelegate(
            is_selected_callback=self.is_file_selected,
            toggle_callback=self.toggle_file_selection
        ))

        instruction = QLabel("Double-click a file to load its content as a quote.")
        layout.addWidget(instruction)

    def _on_file_double_clicked(self, index: QModelIndex) -> None:
        if not self.fs_model.isDir(index):
            file_path = self.fs_model.filePath(index)
            if os.path.isfile(file_path):
                self.fileDoubleClicked.emit(file_path)

    def is_file_selected(self, file_path: str) -> bool:
        return file_path in self.selected_files

    def toggle_file_selection(self, file_path: str) -> None:
        if file_path in self.selected_files:
            self._remove_selected_file(file_path)
        else:
            self._add_selected_file(file_path)
        self.tree_view.viewport().update()

    def _add_selected_file(self, file_path: str) -> None:
        if file_path in self.selected_files:
            return
        self.selected_files.add(file_path)
        file_item = QWidget()
        file_item.setStyleSheet("background-color: rgba(0, 0, 0, 25);")
        layout = QHBoxLayout(file_item)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        label = QLabel(os.path.basename(file_path))
        layout.addWidget(label)
        remove_button = QPushButton("-")
        remove_button.setFixedSize(20, 20)
        remove_button.setFlat(True)
        remove_button.setStyleSheet(
            "QPushButton {"
            "background-color: #0078d7;"
            "color: white;"
            "border: 1px solid #005a9e;"
            "border-radius: 3px;"
            "padding: 0; margin: 0;"
            "}"
            "QPushButton:pressed {"
            "background-color: #005a9e;"
            "}"
        )
        remove_button.clicked.connect(lambda: self._remove_selected_file(file_path))
        layout.addWidget(remove_button)
        self.selected_files_layout.addWidget(file_item)
        self.selected_file_widgets[file_path] = file_item

    def _remove_selected_file(self, file_path: str) -> None:
        if file_path not in self.selected_files:
            return
        self.selected_files.remove(file_path)
        widget = self.selected_file_widgets.pop(file_path, None)
        if widget is not None:
            self.selected_files_layout.removeWidget(widget)
            widget.deleteLater()
        self.tree_view.viewport().update()
