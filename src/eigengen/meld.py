import re
import os

from eigengen import utils, operations, providers, prompts
from eigengen.progress import ProgressIndicator  # Added import


def meld_changes(
    model: providers.Model, filepath: str, changes: str, git_root: str = None
) -> None:
    """
    Melds the changes proposed by the LLM into the specified file.

    Args:
        filepath: The path to the file to meld changes into.
        response: The LLM response containing suggested changes within code blocks.
        git_root: If provided, used to interpret file paths that are relative to the Git root.
    """

    target_full_path = (
        os.path.abspath(os.path.join(git_root, filepath))
        if git_root
        else os.path.abspath(filepath)
    )
    # If git_root is available and the block path is not absolute, assume
    # it is relative to git_root.

    try:
        with open(target_full_path, "r") as f:
            original_content = f.read()
    except FileNotFoundError:
        # It's acceptable if the file does not exist; it will be created.
        original_content = ""

    apply_meld(model, target_full_path, original_content, changes)


def apply_meld(
    model: providers.Model, filepath: str, original_content: str, change_content: str
) -> None:
    payload = (utils.encode_code_block(original_content, filepath)
               + "\n" + utils.encode_code_block(change_content, "changes"))
    # Prepare the conversation messages to send to the LLM.
    messages = [
        {
            "role": "user",
            "content": payload
        }
    ]

    result = ""
    # Initialize and start the progress indicator.
    with ProgressIndicator() as _:
        try:
            chunk_iterator = operations.process_request(
                model,
                messages,
                prompts.get_prompt("meld"),
                utils.encode_code_block(original_content, filepath),
            )
            for chunk in chunk_iterator:
                result += chunk
        except Exception as e:
            print(f"An error occurred during LLM processing: {e}")

    if not result:
        print("No response received from the LLM.")
        return

    # For deepseek models, remove the first <think></think> block.
    if model.model_name.startswith("deepseek"):
        result = re.sub(r"<think>.*?</think>", "", result)

    # Strip any leading or trailing whitespace.
    result = result.strip()
    processed_file_lines = result.splitlines()

    # If the file is wrapped in code fences (e.g. ```), remove them.
    if processed_file_lines and processed_file_lines[0].startswith("```"):
        processed_file_lines = processed_file_lines[1:-1]

    # --- Diff Preview ---
    current_working_directory = os.getcwd()
    rel_filepath = os.path.relpath(filepath, current_working_directory)
    new_content = "\n".join(processed_file_lines)
    diff_output = utils.generate_unified_diff(
        original_content,
        new_content,
        fromfile=f"a/{rel_filepath}",
        tofile=f"b/{rel_filepath}"
    )

    # Show the diff to the user.
    utils.pipe_output_via_pager(diff_output)

    # Ask the user if they want to apply the changes.
    apply_changes = input("Do you want to apply these changes? (y/n): ").strip().lower()
    if apply_changes in ("y", "yes"):
        # Instead of applying a patch, we simply write the new file content directly.
        new_content = "\n".join(processed_file_lines) + "\n"
        # create the directory if it doesn't exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(new_content)
        print("Changes applied successfully.")
    else:
        print("Changes not applied.")

def generate_meld_diff(
    model: providers.Model, filepath: str, changes: str, git_root: str = None
) -> tuple[str, str]:
    """
    Given a changes string and filepath, generate a unified diff without applying the changes.

    Returns:
        A tuple containing the diff output string and the new file content.
    """
    target_full_path = (
        os.path.abspath(os.path.join(git_root, filepath))
        if git_root
        else os.path.abspath(filepath)
    )

    try:
        with open(target_full_path, "r") as f:
            original_content = f.read()
    except FileNotFoundError:
        original_content = ""

    payload = (utils.encode_code_block(original_content, filepath) +
               "\n" + utils.encode_code_block(changes, "changes"))
    messages = [{"role": "user", "content": payload}]

    result = ""
    try:
        chunk_iterator = operations.process_request(
            model,
            messages,
            prompts.get_prompt("meld"),
            utils.encode_code_block(original_content, filepath),
        )
        for chunk in chunk_iterator:
            result += chunk
    except Exception as e:
        print(f"An error occurred during LLM processing in generate_meld_diff: {e}")
        return ("", "")

    if not result:
        return ("", "")

    if model.model_name.startswith("deepseek"):
        result = re.sub(r"<think>.*?</think>", "", result)

    result = result.strip()
    processed_file_lines = result.splitlines()
    if processed_file_lines and processed_file_lines[0].startswith("```"):
        processed_file_lines = processed_file_lines[1:-1]

    new_content = "\n".join(processed_file_lines)

    current_working_directory = os.getcwd()
    rel_filepath = os.path.relpath(filepath, current_working_directory)
    diff_output = utils.generate_unified_diff(
        original_content,
        new_content,
        fromfile=f"a/{rel_filepath}",
        tofile=f"b/{rel_filepath}"
    )

    return diff_output, new_content


def apply_meld_diff(filepath: str, new_content: str) -> None:
    """
    Apply the new content to the file at filepath by writing it.
    """
    final_content = new_content.rstrip() + "\n"
    # check if filepath has a directory part
    if os.path.dirname(filepath):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        f.write(final_content)
    print("Changes applied successfully.")
