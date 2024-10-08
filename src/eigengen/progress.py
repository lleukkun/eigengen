import threading
import time
from typing import Optional, Generator

from colorama import Fore, Style


class ProgressIndicator:
    """
    Displays a pulsating '.oO(   ~o~   )Oo.' message with animated text in a separate thread.
    """

    def __init__(self, interval: float = 0.1, word: str = "~o~"):
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.word = word
        self.space_avail = 6 + len(self.word)
        self.total_size = self.space_avail + 2 * 4  # the opening/closing parts

        # Configuration for animation
        self.animation_frames = self._generate_animation_frames()

    def _generate_animation_frames(self) -> Generator[str, None, None]:
        """
        Generates frames for animating the position of the word within the message.

        Yields:
            str: The next frame in the animation sequence.
        """
        position = 3  # Position of the word initially
        step = 1  # Step size initially

        while True:
            if position + len(self.word) > self.space_avail - 1:
                step = -1  # switch direction
            if position <= 0:
                step = 1  # the other way!
            position += step

            spaces_left = " " * position
            spaces_right = " " * (self.space_avail - len(self.word) - position)
            frame = f".oO({spaces_left}{Fore.CYAN}{self.word}{Style.RESET_ALL}{spaces_right})Oo."
            yield frame

    def _animate(self):
        idx = 0
        while self._running:
            frame = next(self.animation_frames)
            print(f'\r{frame} ', end='', flush=True)
            time.sleep(self.interval)
            idx += 1
        # Clear the line after stopping
        print('\r' + ' ' * self.total_size + '\r', end='', flush=True)

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._animate, daemon=True)
            self._thread.start()

    def stop(self):
        if self._running:
            self._running = False
            if self._thread is not None:
                self._thread.join()
