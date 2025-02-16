import logging
import os

from eigengen import prompts, providers, utils

logger = logging.getLogger(__name__)


def meld_changes(pm: providers.ProviderManager,
                 filepath: str,
                 changes: str,
                 git_root: str = None) -> None:
    """
    Melds the changes proposed by the LLM into the specified file.

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

    system_prompt = prompts.get_prompt("meld")
    response = pm.process_request(providers.ModelType.SMALL,
                       providers.ReasoningAmount.LOW,
                       system_prompt,
                       [{"role": "user", "content": changes}])
    full_response = "".join(response)
    # response is in a Markdown code block; extract the content
    blocks = utils.extract_code_blocks(full_response)
    if len(blocks) != 1:
        logger.error("Expected exactly one code block in the response.")
        return
    new_content = blocks[0][3]

    diff_output = produce_diff(filepath, original_content, new_content)

    # Show the diff preview to the user.
    utils.pipe_output_via_pager(diff_output)

    # Ask the user if they want to apply the changes.
    apply_changes = input("Do you want to apply these changes? (y/n): ").strip().lower()
    if apply_changes in ("y", "yes"):
        # Write the new content directly to the file.
        new_content = new_content.rstrip() + "\n"
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(new_content)
    else:
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
