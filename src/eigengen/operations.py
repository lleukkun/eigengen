from typing import Dict, List, Optional, Generator
import os
import contextlib

from eigengen import log, providers, utils
from eigengen.prompts import PROMPTS as PROMPTS

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


def process_request(model: providers.Model, messages: List[Dict[str, str]], system_message: str, prediction: str|None=None) -> Generator[str, None, None]:
    """
    Processes a request by interfacing with the specified model and handling the conversation flow.
    Args:
        model (providers.Model): The Model instance to use.
        messages (List[Dict[str, str]]): The list of messages in the conversation.
        system_message (str): The system message to use.
    Yields:
        str: Chunks of the final answer as they are generated.
    """


    steering_messages = []
    if model.model_name not in ("o1-preview", "o1-mini"):
        # For models other than 'o1-preview' and 'o1-mini', use a system role message
        steering_messages = [{"role": "system", "content": system_message}]
    else:
        # For 'o1-preview' and 'o1-mini', embed the operating instructions in a user-assistant exchange
        steering_messages = [
            {"role": "user", "content": f"Your operating instructions are here:\n\n{system_message}"},
            {"role": "assistant", "content": "Understood. I now have my operating instructions."}
        ]

    combined_messages = steering_messages + messages

    final_answer: str = ""
    for chunk in model.provider.make_request(model.model_name, combined_messages, model.max_tokens, model.temperature):
        final_answer += chunk
        yield chunk

    # Log the request and response
    log.log_request_response(model.model_name, messages, final_answer)


def default_mode(model: str, user_files: Optional[List[str]], prompt: str) -> None:
    """
    Handles the default mode of operation, preparing messages and processing the request.
    Args:
        model (str): The model nickname to use.
        user_files (Optional[List[str]]): List of user-specified files for context.
        prompt (str): The user's prompt.
    """
    messages: List[Dict[str, str]] = []
    msg_content = prompt

    if user_files:
        project_root = os.getcwd()
        with open_fd(project_root, os.O_RDONLY) as dir_fd:
            for fname in user_files:
                with os.fdopen(os.open(fname, os.O_RDONLY, dir_fd=dir_fd), 'r') as f:
                    original_content = f.read()
                # Add the content of the file to the messages
                msg_content += "\n" + utils.encode_code_block(original_content, fname)
    # Add the user's prompt to the messages
    messages.append({"role": "user", "content": msg_content})

    model_pair = providers.create_model_pair(model)
    # Process the request and print the response
    for chunk in process_request(model_pair.large, messages, PROMPTS["general"]):
        print(chunk, end="", flush=True)
    print("")


def get_file_list(user_files: Optional[List[str]] = None) -> List[str]:
    """
    Compiles a list of files to be used based on git files and user-specified files.
    Args:
        use_git_files (bool, optional): Whether to include git files. Defaults to True.
        user_files (Optional[List[str]], optional): User-specified files. Defaults to None.
    Returns:
        List[str]: Combined list of relevant files.
    """
    file_set = set()

    if user_files:
        file_set.update(user_files)

    file_list = list(file_set) if file_set else []
    return file_list
