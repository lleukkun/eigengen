import contextlib
import logging
import os

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def open_fd(path, flags):
    """
    Context manager to open a file descriptor and ensure it is closed after use.
    Args:
        path (str): The file path to open.
        flags (int): Flags to determine the mode in which the file is opened.
    Yields:
        int: The file descriptor.
    """
    fd = os.open(path, flags)
    try:
        yield fd  # Yield control back to the context block
    finally:
        os.close(fd)  # Ensure fd is closed after the block
