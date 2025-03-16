from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from eigengen.chat import EggChat


class ChatWorker(QThread):
    """
    A QThread subclass that runs the EggChat._get_answer method on a background thread.
    Once the assistant's response is retrieved, it emits the result_ready signal.
    """
    result_ready = Signal(str)

    def __init__(self, eggchat: EggChat, user_message: str, parent: QWidget|None = None):
        super().__init__(parent)
        self.eggchat = eggchat
        self.user_message = user_message

    def run(self) -> None:
        answer = self.eggchat._get_answer(self.user_message, use_progress=False)
        self.result_ready.emit(answer)
