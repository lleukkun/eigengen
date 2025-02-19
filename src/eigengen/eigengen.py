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
from eigengen.providers import PROVIDER_ALIASES

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
    parser.add_argument("--provider", choices=list(PROVIDER_ALIASES.keys()), help="Choose Model")
    parser.add_argument("--editor", help="Choose editor (e.g., nano, vim)")
    parser.add_argument("--color-scheme", choices=["github-dark", "monokai", "solarized"], help="Choose color scheme")
    parser.add_argument(
        "-f", "--files", nargs="+", help="List of files to attach to the request (e.g., -f file1.txt file2.txt)"
    )
    parser.add_argument("--prompt", help="Prompt string to use")
    parser.add_argument("--diff", action="store_true", help="Show diff output (used with -p and without --chat)")
    parser.add_argument(
        "--list-history", nargs="?", const=5, type=int, metavar="N", help="List the last N prompts (default 5)"
    )
    parser.add_argument("--chat", action="store_true", help="Enter chat mode")
    parser.add_argument(
        "--chat-mode",
        default="programmer",
        choices=["general", "architect", "programmer"],
        help="Choose operating mode",
    )
    parser.add_argument("--rag", action="store_true", help="Enable Retrieval Augmented Generation functionality")
    parser.add_argument(
        "--run-api",
        nargs="?",
        const="127.0.0.1:8000",
        metavar="ip:port",
        help="Start API server at ip:port address (default: 127.0.0.1:8000)",
    )

    args = parser.parse_args()
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
    if args.provider:
        config.provider = args.provider
    if args.editor:
        config.editor = args.editor
    if args.color_scheme:
        config.color_scheme = args.color_scheme

    # Store the remaining arguments
    config.args = args

    # If --run-api is specified, start the API server using FastHTML's serve() and exit.
    if args.run_api is not None:
        try:
            ip, port = args.run_api.split(":")
            port = int(port)
        except Exception as e:
            logging.error(f"Error parsing --run-api value '{args.run_api}': {e}")
            sys.exit(1)
        import uvicorn

        from eigengen.chat_api import create_app

        uvicorn.run(create_app(config=config), host=ip, port=port)
        return

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
