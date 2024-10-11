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
from eigengen.config import EggConfig  # Add this import

def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments provided to the script.

    Returns:
        argparse.Namespace: The parsed command-line arguments.
    """
    parser = argparse.ArgumentParser("eigengen")
    parser.add_argument("--config", "-C", default=None,
                        help="Path to the configuration file (default: ~/.eigengen/config.json)")
    parser.add_argument("--model", "-m", choices=list(MODEL_CONFIGS.keys()),
                        help="Choose Model")
    parser.add_argument("--editor", "-e", help="Choose editor (e.g., nano, vim)")
    parser.add_argument("--color-scheme", choices=['github-dark', 'monokai', 'solarized'],
                        help="Choose color scheme")
    parser.add_argument("--files", "-f", nargs="+",
                        help="List of files to attach to the request (e.g., -f file1.txt file2.txt)")
    parser.add_argument("--git-files", "-g", action="store_true",
                        help="Include files from git ls-files, filtered by .eigengen_ignore")
    parser.add_argument("--prompt", "-p", help="Prompt string to use")
    parser.add_argument("--list-history", nargs="?", const=5, type=int, metavar="N",
                        help="List the last N prompts (default 5)")
    parser.add_argument("--index", "-i", action="store_true",
                        help="Index the files for future use")
    parser.add_argument("--test-cache-loading", action="store_true",
                        help="Test cache loading")
    parser.add_argument("--profile", "-P", action="store_true",
                        help="Profile cache loading")
    # Add the --chat (-c) argument to enter chat mode
    parser.add_argument("--chat", "-c", action="store_true",
                        help="Enter chat mode")
    args = parser.parse_args()

    return args

def initialize_environment() -> None:
    """
    Initialize the environment settings.

    Currently initializes colorama for cross-platform color support.
    """
    # Initialize colorama for cross-platform color support
    colorama.init()

def handle_modes(config: EggConfig) -> None:
    """
    Handle different operational modes based on the configuration.

    Args:
        config (EggConfig): Loaded configuration object with applied command-line arguments.
    """
    if config.args.test_cache_loading:
        # Test cache loading, optionally with profiling
        test_cache_loading(config.profile)
        return

    if config.args.list_history is not None:
        # List the last N prompts from the history
        log.list_prompt_history(config.args.list_history)
        return

    # Initialize file lists
    user_files = config.args.files
    git_files = None

    if config.args.git_files:
        # Get filtered git-tracked files
        git_files = gitfiles.get_filtered_git_files()
        if config.args.files:
            # Make user-specified files relative to the git root
            user_files = set([gitfiles.make_relative_to_git_root(x) for x in config.args.files])

    # Combine user files and git files
    combined_files = set()
    if user_files:
        combined_files.update(user_files)
    if git_files:
        combined_files.update(git_files)

    if config.args.index:
        # Index files, forcing reindexing if specified
        index_files(config.args.git_files, force_reindex=True)
        return

    if config.args.git_files:
        # Index git files without forcing reindex
        index_files(config.args.git_files)

    if config.args.chat or config.args.prompt is None:
        # Enter chat mode if --chat is specified or no prompt is provided
        egg_chat = chat.EggChat(config)  # Pass config to EggChat
        egg_chat.chat_mode(git_files, list(user_files or []), initial_prompt=config.args.prompt)
        return

    # Prepare the prompt
    prompt = prepare_prompt(config)
    if not prompt:
        return

    # Log the prompt for history
    log.log_prompt(prompt)

    # Execute the default mode operation
    operations.default_mode(config.model, git_files, list(user_files or []), prompt)

def prepare_prompt(config: EggConfig) -> Optional[str]:
    """
    Prepare the prompt string for processing, based on the configuration.

    Args:
        config (EggConfig): Loaded configuration object.

    Returns:
        Optional[str]: The prompt string, or None if no prompt was provided.
    """
    if config.args.prompt:
        # Use the prompt provided via command-line argument or config
        return config.args.prompt

    # Open an editor for the user to input the prompt
    return utils.get_prompt_from_editor_with_prefill("")

def main() -> None:
    """
    Main function to execute when the script is run directly.
    """
    # First, parse command-line arguments to get the --config option
    args = parse_arguments()

    # Load configuration from the specified config file or default
    config = EggConfig.load_config(config_path=args.config)

    # Apply command-line arguments to config
    if args.model:
        config.model = args.model
    if args.editor:
        config.editor = args.editor
    if args.color_scheme:
        config.color_scheme = args.color_scheme

    # Store the remaining arguments
    config.args = args

    # Initialize environment (e.g., color support)
    initialize_environment()

    # Handle the operational mode based on updated config
    handle_modes(config)

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
