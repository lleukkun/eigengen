"""
eigengen.py: Entry point script for the Eigengen application.

This script handles command-line arguments and initiates different modes of operation,
such as indexing files, entering chat mode, listing history, and processing prompts.
"""

import argparse
import logging
import sys
from typing import Optional

from eigengen import chat, log, utils
from eigengen.config import EggConfig
from eigengen.model_specs import MODEL_SPEC_STRINGS

# Set up logging for the application.
logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments provided to the script.

    Returns:
        argparse.Namespace: The parsed command-line arguments.
    """
    parser = argparse.ArgumentParser("eigengen")
    parser.add_argument(
        "--config", default=None, help="Path to the configuration file (default: ~/.eigengen/config.json)"
    )
    parser.add_argument("--model", choices=MODEL_SPEC_STRINGS,
                        help="Model specifier")
    parser.add_argument("--editor", help="Choose editor (e.g., nano, vim)")
    parser.add_argument("--color-scheme", choices=["github-dark", "monokai", "solarized"], help="Choose color scheme")
    parser.add_argument(
        "-f", "--files", nargs="+", help="List of files to attach to the request (e.g., -f file1.txt file2.txt)"
    )
    parser.add_argument("--prompt", help="Prompt string to use")
    parser.add_argument("--diff", action="store_true", help="Show diff output (used with -p)")
    parser.add_argument(
        "--list-history", nargs="?", const=5, type=int, metavar="N", help="List the last N prompts (default 5)"
    )
    parser.add_argument("--general", action="store_true", help="Use general chat mode")
    parser.add_argument("--programmer", action="store_true", help="Use programmer chat mode")
    parser.add_argument("--rag", action="store_true", help="Enable Retrieval Augmented Generation functionality")
    parser.add_argument("--high", action="store_true", help="Use high reasoning effort for chat (requires LLM support)")

    args = parser.parse_args()
    # only one of --general and --programmer can be specified
    if args.general and args.programmer:
        parser.error("Only one of --general and --programmer can be specified")
    return args


def handle_modes(config: EggConfig) -> None:
    """
    Handle different operational modes based on the configuration.

    Args:
        config (EggConfig): Loaded configuration object with applied command-line arguments.
    """
    if config.args.list_history is not None:
        log.list_prompt_history(config.args.list_history)
        return

    user_files = config.args.files

    # If a prompt is provided on the command line and --chat is not specified,
    # use the auto mode via chat.py rather than the default mode.
    if config.args.prompt and not config.args.chat:
        egg_chat = chat.EggChat(config, list(user_files or []))
        if config.args.diff:
            egg_chat.auto_chat(config.args.prompt, diff_mode=True)
        else:
            egg_chat.auto_chat(config.args.prompt, diff_mode=False)
        return

    # Otherwise, enter interactive chat mode.
    egg_chat = chat.EggChat(config, list(user_files or []))
    egg_chat.chat_mode(initial_prompt=config.args.prompt)


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
    logger.info("Starting Eigengen application.")

    # Load configuration from the specified config file or default
    config = EggConfig.load_config(config_path=args.config)

    # Apply command-line arguments to config
    if args.model:
        config.model_spec_str = args.model
    if args.editor:
        config.editor = args.editor
    if args.color_scheme:
        config.color_scheme = args.color_scheme

    if not config.model_spec_str or config.model_spec_str == "":
        config.model_spec_str = MODEL_SPEC_STRINGS[0]

    # Store the remaining arguments
    config.args = args

    # Glob wildcard file patterns on Windows only

    if sys.platform == "win32" and config.args.files:
        import glob

        expanded_files = []
        for pattern in config.args.files:
            matches = glob.glob(pattern)
            # If globbing yielded any files, use them; otherwise keep original pattern.
            if matches:
                expanded_files.extend(matches)
            else:
                expanded_files.append(pattern)
        config.args.files = expanded_files

    # Handle the operational mode based on updated config
    handle_modes(config)


if __name__ == "__main__":
    # Entry point of the script
    main()
