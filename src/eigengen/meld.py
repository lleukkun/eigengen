import logging
import os

from eigengen import prompts, providers, utils
from eigengen.progress import ProgressIndicator

logger = logging.getLogger(__name__)


def apply_changes(pm: providers.ProviderManager, filepath: str, original_content: str, changes: str) -> str:
    """
    Applies changes to the original content using the LLM.
    """
    system_prompt = prompts.get_prompt("meld")
    encoded_original_content = utils.encode_code_block(original_content, filepath)
    messages = [
        ("user", f"{encoded_original_content}\n{changes}"),
    ]
    response = ""
    with ProgressIndicator() as _:
        chunks = pm.process_request(providers.ModelType.SMALL, providers.ReasoningAmount.LOW, system_prompt, messages)
        response = "".join(chunks)

    blocks = utils.extract_code_blocks(response)
    new_content = blocks[0].content if blocks and len(blocks) > 0 else original_content

    return new_content


def meld_changes(
    pm: providers.ProviderManager, filepath: str, changes: str, git_root: str | None = None, yes: bool = False
) -> None:
    """
    Melds the changes proposed by the LLM into the specified file.

    This function takes the proposed changes and the original content of the file,
    processes them through the LLM to generate a merged version, and then applies
    the changes to the file if the user confirms.

    Args:
        pm (providers.ProviderManager): The provider manager instance.
        filepath (str): The path to the file to meld changes into.
        changes (str): A string containing the proposed changes in custom diff format.
        git_root (str, optional): If provided, used to interpret file paths that are relative to the Git root.

    Returns:
        None
    """

    # If git_root is available and the block path is not absolute, assume
    # it is relative to git_root.

    try:
        with open(filepath, "r") as f:
            original_content = f.read()
    except FileNotFoundError:
        # It's acceptable if the file does not exist; it will be created.
        original_content = ""

    new_content = apply_changes(pm, filepath, original_content, changes)
    diff_output = produce_diff(filepath, original_content, new_content)

    # Show the diff preview to the user.
    if not yes:
        utils.pipe_output_via_pager(diff_output)

    # Ask the user if they want to apply the changes.
    apply = "y" if yes else input("Do you want to apply these changes? (y/n): ").strip().lower()

    if apply in ("y", "yes"):
        # Write the new content directly to the file.
        new_content = new_content.rstrip() + "\n"
        dirpath = os.path.dirname(filepath)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)

        with open(filepath, "w") as f:
            f.write(new_content)
    else:
        logger.info("Changes not applied.")


def produce_diff(filename: str, original_content: str, new_content: str) -> str:
    """
    Produces a unified diff between the original content and the new content.

    This function generates a unified diff that highlights the differences between
    the original and new content of a file. The diff is formatted to show the changes
    in a clear and readable manner.

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


def get_merged_content_and_diff(
    pm: providers.ProviderManager, filepath: str, original_content: str, changes: str
) -> tuple[str, str]:
    """
    For GUI use: Applies the proposed changes using the LLM and returns a tuple of:
    - new_content: the merged file content, and
    - diff_output: a unified diff between the original and new content.
    This function does not prompt for confirmation.
    """
    new_content = apply_changes(pm, filepath, original_content, changes)
    diff_output = produce_diff(filepath, original_content, new_content)
    return new_content, diff_output


def apply_new_content(filepath: str, new_content: str) -> None:
    """
    Writes the new content to the specified file.
    Ensures that directories exist and always writes with a trailing newline.
    """
    new_content = new_content.rstrip() + "\n"
    dirpath = os.path.dirname(filepath)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath, exist_ok=True)
    with open(filepath, "w") as f:
        f.write(new_content)
