import logging
import os

from eigengen import utils

logger = logging.getLogger(__name__)


def meld_changes(filepath: str, changes: str, git_root: str = None, unified_diff: bool = False) -> None:
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

    target_full_path = os.path.abspath(os.path.join(git_root, filepath)) if git_root else os.path.abspath(filepath)
    # If git_root is available and the block path is not absolute, assume
    # it is relative to git_root.

    try:
        with open(target_full_path, "r") as f:
            original_content = f.read()
    except FileNotFoundError:
        # It's acceptable if the file does not exist; it will be created.
        original_content = ""

    # Use the appropriate diff application method based on the unified_diff flag.
    new_content = (
        apply_gemini_diff(original_content, changes)
        if unified_diff
        else apply_contextual_diff(original_content, changes)
    )

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
    else:
        logger.info("Changes applied successfully.")
        logger.info("Changes not applied.")


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


def apply_contextual_diff(original_content: str, patch_content: str) -> str:
    orig_lines = original_content.splitlines()
    patch_lines = patch_content.splitlines()
    new_lines = []
    # Handle the case where the original file is empty:
    # Apply all addition lines in the diff (ignoring removal lines and diff markers).
    if not orig_lines:
        for line in patch_lines:
            if line.startswith("+"):
                new_lines.append(line[1:])
        return "\n".join(new_lines) + "\n"
    orig_pos = 0
    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        if line.startswith("@@"):
            # Extract the anchor text from the diff header.
            anchor = line[2:].strip()
            i += 1
            # Parse the diff block lines.
            removal_lines = []
            addition_lines = []
            while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                current = patch_lines[i]
                if current.startswith("-"):
                    removal_lines.append(current[1:])
                elif current.startswith("+"):
                    addition_lines.append(current[1:])
                i += 1

            # Determine if the anchor itself is scheduled for removal.
            anchor_removed = removal_lines and (removal_lines[0].strip() == anchor)

            # Locate the anchor in the original content.
            found = False
            for j in range(orig_pos, len(orig_lines)):
                if orig_lines[j].strip() == anchor:
                    new_lines.extend(orig_lines[orig_pos:j])
                    # If the anchor is being replaced, do not retain it.
                    if not anchor_removed:
                        new_lines.append(orig_lines[j])
                    orig_pos = j + 1
                    found = True
                    break
            if not found:
                # Skip this diff block if anchor not found.
                logger.error(f"Anchor not found: {anchor}")
                continue

            # Process removal lines.
            if removal_lines:
                # If the anchor was removed, skip the first removal line as it corresponds to the anchor.
                start_idx = 1 if anchor_removed else 0
                for rem in removal_lines[start_idx:]:
                    found_rem = False
                    for k in range(orig_pos, len(orig_lines)):
                        if orig_lines[k].strip() == rem.strip():
                            new_lines.extend(orig_lines[orig_pos:k])
                            orig_pos = k + 1
                            found_rem = True
                            break
                    if not found_rem:
                        # Removals not found are silently ignored.
                        pass

            # Insert addition lines.
            new_lines.extend(addition_lines)
        else:
            # Ignore lines outside diff segments.
            i += 1

    # Append any remaining original lines.
    new_lines.extend(orig_lines[orig_pos:])
    return "\n".join(new_lines) + "\n"


def apply_gemini_diff(original_content: str, diff_content: str) -> str:
    """
    Applies a unified diff (in Gemini's format) to the original content.

    Args:
        original_content (str): The original content of the file.
        diff_content (str): The unified diff content produced by Gemini.

    Returns:
        str: The new content after applying the diff.
    """
    import re

    old_lines = original_content.splitlines()
    diff_lines = diff_content.splitlines()
    new_lines = []
    old_index = 0

    hunk_header_pattern = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    i = 0
    while i < len(diff_lines):
        line = diff_lines[i]
        if line.startswith("---") or line.startswith("+++"):
            i += 1
            continue
        if line.startswith("@@"):
            m = hunk_header_pattern.match(line)
            if m:
                old_start = int(m.group(1)) - 1
                # old_count = int(m.group(2)) if m.group(2) else 1  # not used directly here
            else:
                i += 1
                continue

            # Append unchanged lines before this hunk.
            while old_index < old_start and old_index < len(old_lines):
                new_lines.append(old_lines[old_index])
                old_index += 1

            i += 1
            # Process hunk lines until the next hunk header or end of diff.
            while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
                diff_line = diff_lines[i]
                if diff_line.startswith(" "):
                    new_lines.append(diff_line[1:])
                    old_index += 1
                elif diff_line.startswith("-"):
                    # Removed line; skip it in the original content.
                    old_index += 1
                elif diff_line.startswith("+"):
                    new_lines.append(diff_line[1:])
                else:
                    # Fallback: treat unexpected lines as context.
                    new_lines.append(diff_line)
                    old_index += 1
                i += 1
        else:
            i += 1

    # Append any remaining unmodified lines.
    while old_index < len(old_lines):
        new_lines.append(old_lines[old_index])
        old_index += 1

    return "\n".join(new_lines) + "\n"
