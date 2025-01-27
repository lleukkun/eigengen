"""
eigengen.py: Entry point script for the Eigengen application.

This script handles command-line arguments and initiates different modes of operation,
such as indexing files, entering chat mode, listing history, and processing prompts.
"""

from typing import Optional
import argparse

from eigengen.providers import MODEL_CONFIGS
from eigengen import operations, log, chat, utils
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
    parser.add_argument("--prompt", "-p", help="Prompt string to use")
    parser.add_argument("--list-history", nargs="?", const=5, type=int, metavar="N",
                        help="List the last N prompts (default 5)")
    parser.add_argument("--profile", "-P", action="store_true",
                        help="Profile cache loading")
    # Add the --chat (-c) argument to enter chat mode
    parser.add_argument("--chat", "-c", action="store_true",
                        help="Enter chat mode")
    parser.add_argument("--chat-mode", "-M", default="programmer", choices=["general", "architect", "programmer"],
                        help="Choose operating mode")

    args = parser.parse_args()

    return args

def handle_modes(config: EggConfig) -> None:
    """
    Handle different operational modes based on the configuration.

    Args:
        config (EggConfig): Loaded configuration object with applied command-line arguments.
    """
    if config.args.list_history is not None:
        # List the last N prompts from the history
        log.list_prompt_history(config.args.list_history)
        return

    # Initialize file lists
    user_files = config.args.files

    # Combine user files and git files
    combined_files = set()
    if user_files:
        combined_files.update(user_files)

    if config.args.chat or config.args.prompt is None:
        # Enter chat mode if --chat is specified or no prompt is provided
        egg_chat = chat.EggChat(config, list(user_files or []))
        egg_chat.chat_mode(initial_prompt=config.args.prompt)
        return

    # Prepare the prompt
    prompt = prepare_prompt(config)
    if not prompt:
        return

    # Log the prompt for history
    log.log_prompt(prompt)

    # Execute the default mode operation
    operations.default_mode(config.model, list(user_files or []), prompt)

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
    return utils.get_prompt_from_editor_with_prefill(config, "")

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

    # Handle the operational mode based on updated config
    handle_modes(config)


if __name__ == "__main__":
    # Entry point of the script
    main()
