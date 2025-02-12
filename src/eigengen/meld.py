import os

from eigengen import utils


def meld_changes(filepath: str, changes: str, git_root: str = None) -> None:
    """
    Melds the changes proposed by the LLM into the specified file.

    Args:
        model (providers.Model): The model instance used for processing.
        filepath (str): The path to the file to meld changes into.
        changes (str): A string containing the proposed changes in custom diff format.
        git_root (str, optional): If provided, used to interpret file paths that are relative to the Git root.

    Returns:
        None
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

    # Use the new apply_custom_diff() method to merge the custom diff with the original content.
    new_content = apply_custom_diff(original_content, changes)

    diff_output = produce_diff(target_full_path, original_content, new_content)

    # Show the diff preview to the user.
    utils.pipe_output_via_pager(diff_output)

    # Ask the user if they want to apply the changes.
    apply_changes = input("Do you want to apply these changes? (y/n): ").strip().lower()
    if apply_changes in ("y", "yes"):
        # Write the new content directly to the file.
        new_content = new_content.rstrip() + "\n"
        os.makedirs(os.path.dirname(target_full_path), exist_ok=True)
        with open(target_full_path, "w") as f:
            f.write(new_content)
        print("Changes applied successfully.")
    else:
        print("Changes not applied.")

def produce_diff(filename: str, original_content: str, new_content: str) -> str:
    """
    Produces a unified diff between the original content and the new content.

    Args:
        filename (str): The name of the file being diffed.
        original_content (str): The original content of the file.
        new_content (str): The new content of the file.

    Returns:
        str: The unified diff as a string.
    """
    current_working_directory = os.getcwd()
    rel_filepath = os.path.relpath(filename, current_working_directory)
    diff_output = utils.generate_unified_diff(
        original_content,
        new_content,
        fromfile=f"a/{rel_filepath}",
        tofile=f"b/{rel_filepath}",
    )
    return diff_output

def apply_custom_diff(original_content: str, patch_content: str) -> str:
    """
    Applies a custom diff patch to the original content and returns the updated content.

    The custom diff should contain one or more blocks structured as follows:
        |<<<<<<<
        |lines to be removed
        |=======
        |lines that will replace the removed lines
        |>>>>>>>

    For each block, if the original_content is non-empty, the function searches (using stripped comparisons)
    for the sequence of lines in the original content matching the removal block; if a match is found, it is
    replaced with the insertion block. However, if the original_content is an empty string, we interpret that as a signal that
    all codeblocks should be applied sequentially (ignoring any removal lines). This is useful when creating a new file.
    """
    patch_lines = patch_content.splitlines()

    # Special handling if the original content is empty:
    if original_content == "":
        new_lines = []
        i = 0  # pointer in patch_lines
        while i < len(patch_lines):
            if patch_lines[i].strip() == "<<<<<<<":
                i += 1
                # Skip removal block (if any)
                while i < len(patch_lines) and patch_lines[i].strip() != "=======":
                    i += 1

                # If the separator is found, skip it.
                if i < len(patch_lines) and patch_lines[i].strip() == "=======":
                    i += 1

                insertion_block = []
                # Collect insertion lines
                while i < len(patch_lines) and patch_lines[i].strip() != ">>>>>>>":
                    insertion_block.append(patch_lines[i])
                    i += 1

                # Skip the closing marker if present.
                if i < len(patch_lines) and patch_lines[i].strip() == ">>>>>>>":
                    i += 1

                new_lines.extend(insertion_block)
            else:
                i += 1
        return "\n".join(new_lines) + "\n"

    # Standard processing if original_content is not empty
    original_lines = original_content.splitlines()
    new_lines = []
    pos = 0  # pointer in original_lines

    i = 0  # pointer in patch_lines
    while i < len(patch_lines):
        if patch_lines[i].strip() == "<<<<<<<":
            i += 1
            removal_block = []
            # Collect removal lines
            while i < len(patch_lines) and patch_lines[i].strip() != "=======":
                removal_block.append(patch_lines[i])
                i += 1

            # If we did not find the separator, break out (or skip block)
            if i >= len(patch_lines) or patch_lines[i].strip() != "=======":
                break  # Incomplete block; stop processing.
            i += 1  # Skip the "=======" line

            insertion_block = []
            # Collect insertion lines
            while i < len(patch_lines) and patch_lines[i].strip() != ">>>>>>>":
                insertion_block.append(patch_lines[i])
                i += 1

            # Skip the closing marker if present.
            if i < len(patch_lines) and patch_lines[i].strip() == ">>>>>>>":
                i += 1

            # Search for the removal_block in original_lines starting from pos.
            found = False
            for j in range(pos, len(original_lines) - len(removal_block) + 1):
                match = True
                for k, rem_line in enumerate(removal_block):
                    if original_lines[j + k].strip() != rem_line.strip():
                        match = False
                        break
                if match:
                    new_lines.extend(original_lines[pos:j])
                    new_lines.extend(insertion_block)
                    pos = j + len(removal_block)
                    found = True
                    break
            # If not found, skip this patch block.
        else:
            i += 1

    new_lines.extend(original_lines[pos:])
    return "\n".join(new_lines) + "\n"
