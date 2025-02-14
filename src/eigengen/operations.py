import contextlib
import logging
import os
from typing import Generator

from eigengen import log, providers
from eigengen.prompts import PROMPTS as PROMPTS

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


def process_request(
    model: providers.Model, messages: list[dict[str, str]], system_message: str, reasoning_effort: str | None = None
) -> Generator[str, None, None]:
    """
    Processes a request by interfacing with the specified model and handling the conversation flow.
    Args:
        model (providers.Model): The Model instance to use.
        messages (list[dict[str, str]]): The list of messages in the conversation.
        system_message (str): The system message to use.
    Yields:
        str: Chunks of the final answer as they are generated.
    """

    steering_messages = []
    steering_role = "system"
    steering_messages = [{"role": steering_role, "content": system_message}]

    combined_messages = steering_messages + messages

    final_answer: str = ""
    for chunk in model.provider.make_request(model.model_name, combined_messages, model.temperature, reasoning_effort):
        final_answer += chunk
        yield chunk

    # Log the request and response
    log.log_request_response(model.model_name, messages, final_answer)
