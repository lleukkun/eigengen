from typing import Dict, List, Optional, Generator
import os
import contextlib

from eigengen import log, providers, utils, gitfiles, indexing
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


def process_request(model: providers.Model, messages: List[Dict[str, str]], system_message: str) -> Generator[str, None, None]:
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


def default_mode(model: str, git_files: Optional[List[str]], user_files: Optional[List[str]], prompt: str) -> None:
    """
    Handles the default mode of operation, preparing messages and processing the request.
    Args:
        model (str): The model nickname to use.
        git_files (Optional[List[str]]): List of git files for context.
        user_files (Optional[List[str]]): List of user-specified files for context.
        prompt (str): The user's prompt.
    """
    messages: List[Dict[str, str]] = []

    # Get the relevant files based on context
    relevant_files = get_context_aware_files(git_files, user_files)

    if relevant_files:
        project_root = gitfiles.find_git_root() if git_files else os.getcwd()
        with open_fd(project_root, os.O_RDONLY) as dir_fd:
            for fname in relevant_files:
                with os.fdopen(os.open(fname, os.O_RDONLY, dir_fd=dir_fd), 'r') as f:
                    original_content = f.read()
                # Add the content of the file to the messages
                messages += [
                    {"role": "user", "content": utils.encode_code_block(original_content, fname)},
                    {"role": "assistant", "content": "ok"}
                ]
    # Add the user's prompt to the messages
    messages.append({"role": "user", "content": prompt})

    model_pair = providers.create_model_pair(model)
    # Process the request and print the response
    for chunk in process_request(model_pair.large, messages, PROMPTS["general"]):
        print(chunk, end="", flush=True)
    print("")


def get_file_list(use_git_files: bool = True, user_files: Optional[List[str]] = None) -> List[str]:
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
        if use_git_files:
            # Make user files relative to the git root
            user_files = [gitfiles.make_relative_to_git_root(f) for f in user_files]
        file_set.update(user_files)

    if use_git_files:
        # Get the filtered list of git files
        git_files = set(gitfiles.get_filtered_git_files())
        file_set.update(git_files)

    file_list = list(file_set) if file_set else []
    return file_list


def get_context_aware_files(git_files: Optional[List[str]], user_files: Optional[List[str]]) -> List[str]:
    """
    Determines the list of files that are relevant based on the current context.
    Args:
        git_files (Optional[List[str]]): List of git files.
        user_files (Optional[List[str]]): List of user-specified files.
    Returns:
        List[str]: List of relevant files.
    """
    if not git_files:
        return user_files or []

    # Ensure user_files are always included
    user_files = user_files or []
    relevant_files = set(user_files)

    # Get locally modified git files if in git mode
    local_modifications = gitfiles.get_locally_modified_git_files() if git_files else []
    relevant_files.update(local_modifications)

    # If there are no user_files and no local modifications, add default context
    if not user_files and not local_modifications:
        # Get default context (top-3 files with highest total_refcount)
        default_context = indexing.get_default_context(git_files)
        relevant_files.update(default_context)

    # Read the cache state
    cache_state = indexing.read_cache_state()

    # Find files that use symbols defined in the relevant files
    files_using_relevant_symbols = {}
    for file in relevant_files:
        if file in cache_state.entries:
            entry = cache_state.entries[file]
            for symbol in entry.provides:
                for using_file, using_entry in cache_state.entries.items():
                    if symbol in using_entry.uses and using_file not in relevant_files:
                        files_using_relevant_symbols[using_file] = files_using_relevant_symbols.get(using_file, 0) + 1

    # Sort files by relevance (number of used symbols) and take the top 5
    sorted_files = sorted(files_using_relevant_symbols.items(), key=lambda x: x[1], reverse=True)
    top_5_relevant_files = [file for file, _ in sorted_files[:5]]

    # Add the top 5 most relevant files to the relevant_files set
    relevant_files.update(top_5_relevant_files)

    print(f"relevant files: {relevant_files}")
    return list(relevant_files)
