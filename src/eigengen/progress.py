import threading
import time
from typing import Generator, Optional

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.styles import Style

# ignore T201 for this file
# ruff: noqa: T201


class ProgressIndicator:
    """
    Displays a pulsating '.oO(   ~o~   )Oo.' message with animated text in a separate thread,
    using prompt_toolkit for colored outputs.
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

        # Define the style for the progress word
        self.style = Style.from_dict(
            {
                "progress": "ansicyan"  # You can customize the color as desired
            }
        )

    def _generate_animation_frames(self) -> Generator[FormattedText, None, None]:
        """
        Generates formatted frames for animating the position of the word within the message.

        Yields:
            FormattedText: The next formatted frame in the animation sequence.
        """
        position = 3  # Position of the word initially
        step = 1  # Step size initially

        while True:
            if position + len(self.word) > self.space_avail - 1:
                step = -1  # Switch direction to move left
            if position <= 0:
                step = 1  # Switch direction to move right
            position += step

            spaces_left = " " * position
            spaces_right = " " * (self.space_avail - len(self.word) - position)

            # Create FormattedText directly without assembling a string
            formatted_frame = FormattedText(
                [("", ".oO("), ("", spaces_left), ("class:progress", self.word), ("", spaces_right), ("", ")Oo.")]
            )

            yield formatted_frame

    def _animate(self):
        try:
            print("\033[?25l", end="")  # Hide the cursor
            while self._running:
                frame = next(self.animation_frames)
                print("\r", end="", flush=False)
                print_formatted_text(frame, end="", style=self.style, flush=True)
                time.sleep(self.interval)
        finally:
            # Clear the line after stopping
            print(" " * self.total_size + "\r", end="", flush=True)
            print("\033[?25h", end="")  # Show the cursor

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

    def __enter__(self):
        """Enter the runtime context related to this object."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context and ensure the progress indicator stops."""
        self.stop()
