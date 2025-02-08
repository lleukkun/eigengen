import difflib
import re
import os

from eigengen import utils, operations, providers, prompts
from eigengen.progress import ProgressIndicator  # Added import


def meld_changes(
    model: providers.Model, filepath: str, response: str, git_root: str = None
) -> None:
    """
    Melds the changes proposed by the LLM into the specified file.

    Args:
        filepath: The path to the file to meld changes into.
        response: The LLM response containing suggested changes within code blocks.
        git_root: If provided, used to interpret file paths that are relative to the Git root.
    """
    code_blocks = utils.extract_code_blocks(response)
    target_block = None
    target_full_path = (
        os.path.abspath(os.path.join(git_root, filepath))
        if git_root
        else os.path.abspath(filepath)
    )

    for _, _, block_path, block_content, _, _ in code_blocks:
        if not block_path:
            continue  # Skip blocks without path information

        # If git_root is available and the block path is not absolute, assume it is relative to git_root.
        block_full_path = (
            os.path.abspath(block_path)
            if not git_root
            else os.path.abspath(os.path.join(git_root, block_path))
        )

        if block_full_path == target_full_path:
            target_block = block_content
            break

    if not target_block:
        print(f"No code block found for file: {target_full_path}")
        return

    try:
        with open(target_full_path, "r") as f:
            original_content = f.read()
    except FileNotFoundError:
        # It's acceptable if the file does not exist; it will be created.
        original_content = ""

    apply_meld(model, target_full_path, original_content, response)


def apply_meld(
    model: providers.Model, filepath: str, original_content: str, change_content: str
) -> None:
    # Remove <think></think> tags and any intervening text from change_content.
    change_content = re.sub(r"<think>.*?</think>", "", change_content, flags=re.DOTALL)

    # Prepare the conversation messages to send to the LLM.
    messages = [
        # Send the original file content to the LLM.
        {
            "role": "user",
            "content": utils.encode_code_block(original_content, filepath),
        },
        {"role": "assistant", "content": "ok"},
        # Send the change content to the LLM.
        {"role": "user", "content": utils.encode_code_block(change_content, "changes")},
        {"role": "assistant", "content": "ok"},
        # Instruct the LLM to integrate changes into the original file.
        {
            "role": "user",
            "content": f"You must integrate the relevant changes present in the changes file into the original {filepath}.\n"
            "You must respond with only the full file contents.\n"
            "You must not write anything else.",
        },
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
    diff_output = (
        "\n".join(
            difflib.unified_diff(
                original_content.splitlines(),
                processed_file_lines,
                fromfile=f"a/{rel_filepath}",
                tofile=f"b/{rel_filepath}",
                lineterm="",
            )
        )
        + "\n"
    )  # Ensure a final newline

    # Show the diff to the user.
    utils.pipe_output_via_pager(diff_output)

    # Ask the user if they want to apply the changes.
    apply_changes = input("Do you want to apply these changes? (y/n): ").strip().lower()
    if apply_changes in ("y", "yes"):
        # Instead of applying a patch, we simply write the new file content directly.
        new_content = "\n".join(processed_file_lines) + "\n"
        with open(filepath, "w") as f:
            f.write(new_content)
        print("Changes applied successfully.")
    else:
        print("Changes not applied.")
