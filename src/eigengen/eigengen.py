"""
eigengen.py: Entry point script for the Eigengen application.

This script handles command-line arguments and initiates different modes of operation,
such as indexing files, entering chat mode, listing history, and processing prompts.
"""

from typing import Optional
import argparse
import cProfile

import colorama

from eigengen.providers import MODEL_CONFIGS
from eigengen import operations, log, indexing, gitfiles, chat, utils

def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments provided to the script.

    Returns:
        argparse.Namespace: An object containing the parsed arguments.
    """
    parser = argparse.ArgumentParser("eigengen")
    parser.add_argument("--model", "-m", choices=list(MODEL_CONFIGS.keys()),
                        default="claude-sonnet", help="Choose Model")
    parser.add_argument("--files", "-f", nargs="+",
                        help="List of files to attach to the request (e.g., -f file1.txt file2.txt)")
    parser.add_argument("--git-files", "-g", action="store_true",
                        help="Include files from git ls-files, filtered by .eigengen_ignore")
    parser.add_argument("--prompt", "-p", help="Prompt string to use")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto",
                        help="Control color output: 'auto' (default), 'always', or 'never'")
    parser.add_argument("--list-history", nargs="?", const=5, type=int, metavar="N",
                        help="List the last N prompts (default 5)")
    parser.add_argument("--index", action="store_true",
                        help="Index the files for future use")
    parser.add_argument("--test-cache-loading", action="store_true",
                        help="Test cache loading")
    parser.add_argument("--profile", action="store_true",
                        help="Profile cache loading")
    # Add the --chat (-c) argument to enter chat mode
    parser.add_argument("--chat", "-c", action="store_true",
                        help="Enter chat mode")
    return parser.parse_args()

def initialize_environment() -> None:
    """
    Initialize the environment settings.

    Currently initializes colorama for cross-platform color support.
    """
    # Initialize colorama for cross-platform color support
    colorama.init()

def handle_modes(args: argparse.Namespace) -> None:
    """
    Handle different operational modes based on the parsed arguments.

    Args:
        args (argparse.Namespace): Parsed command-line arguments.
    """
    if args.test_cache_loading:
        # Test cache loading, optionally with profiling
        test_cache_loading(args.profile)
        return

    if args.list_history is not None:
        # List the last N prompts from the history
        log.list_prompt_history(args.list_history)
        return

    # Initialize file lists
    user_files = args.files
    git_files = None

    if args.git_files:
        # Get filtered git-tracked files
        git_files = gitfiles.get_filtered_git_files()
        if args.files:
            # Make user-specified files relative to the git root
            user_files = set([gitfiles.make_relative_to_git_root(x) for x in args.files])

    # Combine user files and git files
    combined_files = set()
    if user_files:
        combined_files.update(user_files)
    if git_files:
        combined_files.update(git_files)

    if args.index:
        # Index files, forcing reindexing if specified
        index_files(args.git_files, force_reindex=True)
        return

    if args.git_files:
        # Index git files without forcing reindex
        index_files(args.git_files)

    if args.chat or args.prompt is None:
        # Enter chat mode if --chat is specified or no prompt is provided
        egg_chat = chat.EggChat()
        egg_chat.chat_mode(args.model, git_files, list(user_files or []), initial_prompt=args.prompt)
        return

    # Prepare the prompt
    prompt = prepare_prompt(args)
    if not prompt:
        return

    # Log the prompt for history
    log.log_prompt(prompt)

    # Execute the default mode operation
    operations.default_mode(args.model, git_files, list(user_files or []), prompt)

def prepare_prompt(args: argparse.Namespace) -> Optional[str]:
    """
    Prepare the prompt string for processing.

    Args:
        args (argparse.Namespace): Parsed command-line arguments.

    Returns:
        Optional[str]: The prompt string, or None if no prompt was provided.
    """
    if args.prompt:
        # Use the prompt provided via command-line argument
        return args.prompt

    # Open an editor for the user to input the prompt
    return utils.get_prompt_from_editor_with_prefill("")

def main() -> None:
    """
    Main function to execute when the script is run directly.
    """
    # Parse command-line arguments
    args = parse_arguments()
    # Initialize environment (e.g., color support)
    initialize_environment()
    # Handle the operational mode based on arguments
    handle_modes(args)

def test_cache_loading(profile: bool) -> None:
    """
    Test the cache loading functionality, optionally with profiling.

    Args:
        profile (bool): If True, run cache loading with profiling.
    """
    if profile:
        # Profile cache loading
        cProfile.run("from eigengen import indexing\n_ = indexing.read_cache_state()")
    else:
        # Load cache without profiling
        _ = indexing.read_cache_state()

def index_files(use_git_files: bool, force_reindex: bool = False) -> None:
    """
    Index files for future reference.

    Args:
        use_git_files (bool): Whether to include git-tracked files in indexing.
        force_reindex (bool): Whether to force reindexing of files.
    """
    # Get git files if specified, otherwise use an empty list
    git_files = operations.gitfiles.get_filtered_git_files() if use_git_files else []
    # Index the files, forcing reindex if specified
    indexing.index_files(git_files, force_reindex=force_reindex)

if __name__ == "__main__":
    # Entry point of the script
    main()
