import difflib
import subprocess

from eigengen import utils, operations
from eigengen.progress import ProgressIndicator  # Added import


def meld_changes(model_nickname: str, filepath: str, response: str) -> None:
    """
    Melds the changes proposed by the LLM into the specified file.

    Args:
        filepath: The path to the file to meld changes into.
        response: The LLM response containing suggested changes within code blocks.
    """

    code_blocks = utils.extract_code_blocks(response)
    target_block = None
    original_content = ""

    for _, block_lang, block_path, block_content, _, _ in code_blocks:
        if not block_path:
            continue  # Skip blocks without path information

        if block_path == filepath:
            target_block = block_content
            break

    if not target_block:
        print(f"No code block found for file: {filepath}")
        return

    try:
        with open(filepath, "r") as f:
            original_content = f.read()
    except FileNotFoundError:
        # this is perfectly ok, we're expected to create the file
        pass

    apply_meld(model_nickname, filepath, original_content, response)


def apply_meld(model_nickname: str, filepath: str, original_content: str, change_content: str) -> None:
    # Prepare the conversation messages to send to the LLM
    messages = [
        # Send the original file content to the LLM
        {"role": "user", "content": utils.encode_code_block(original_content, filepath)},
        # Assistant acknowledges receipt
        {"role": "assistant", "content": "ok"},
        # Send the change content to the LLM
        {"role": "user", "content": utils.encode_code_block(change_content, "changes")},
        # Assistant acknowledges receipt
        {"role": "assistant", "content": "ok"},
        # Instruct the LLM to integrate changes into the original file
        {"role": "user", "content":
            f"You must integrate the relevant changes present in the changes file into the original {filepath}.\n"
            "You must respond with only the full file contents.\n"
            "You must not write anything else."
        }
    ]

    # Initialize and start the progress indicator
    indicator = ProgressIndicator()
    indicator.start()

    # Process the request using the LLM and get the updated file content
    result = ""
    try:
        chunk_iterator = operations.process_request(model_nickname, messages, mode="meld")
        for chunk in chunk_iterator:
            result += chunk
    except Exception as e:
        print(f"An error occurred during LLM processing: {e}")
    finally:
        # Stop the progress indicator after response is complete or an error occurs
        indicator.stop()

    if not result:
        print("No response received from the LLM.")
        return

    processed_file_lines = "".join(result).splitlines()
    if processed_file_lines[0].startswith("```"):
        # we expect this, but some models may fail to wrap the output with fences
        processed_file_lines = processed_file_lines[1:-1]

    # Generate a unified diff between the original content and the updated content
    diff_output = "\n".join(
        difflib.unified_diff(
            original_content.splitlines(),
            processed_file_lines,
            fromfile=f"a/{filepath}",
            tofile=f"b/{filepath}",
            lineterm=""
        )
    ) + "\n"  # add final newline
    # Print the diff output
    print(diff_output)

    # Ask the user if they want to apply the changes
    apply_changes = input("Do you want to apply these changes? (y/n): ").strip().lower()
    if apply_changes in ('y', 'yes'):
        # Apply the diff using the patch command
        try:
            # Run the patch command with the diff output
            patch_process = subprocess.Popen(["patch", "-u", "-p1", filepath], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            patch_stdout, patch_stderr = patch_process.communicate(input=diff_output.encode())
            if patch_process.returncode == 0:
                print("Changes applied successfully.")
            else:
                print("Failed to apply changes.")
                if patch_stderr:
                    print(patch_stderr.decode())
        except FileNotFoundError:
            print("Error: 'patch' command not found. Please ensure it is installed and available in your PATH.")
    else:
        print("Changes not applied.")
