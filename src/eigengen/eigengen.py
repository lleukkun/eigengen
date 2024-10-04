from typing import Optional
import argparse
import cProfile

import colorama

from eigengen.providers import MODEL_CONFIGS
from eigengen import operations, log, indexing, gitfiles, chat, utils


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser("eigengen")
    parser.add_argument("--model", "-m", choices=list(MODEL_CONFIGS.keys()),
                        default="claude-sonnet", help="Choose Model")
    parser.add_argument("--files", "-f", nargs="+", help="List of files to attach to the request (e.g., -f file1.txt file2.txt)")
    parser.add_argument("--git-files", "-g", action="store_true", help="Include files from git ls-files, filtered by .eigengen_ignore")
    parser.add_argument("--prompt", "-p", help="Prompt string to use")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto",
                        help="Control color output: 'auto' (default), 'always', or 'never'")
    parser.add_argument("--list-history", nargs="?", const=5, type=int, metavar="N",
                        help="List the last N prompts (default 5)")
    parser.add_argument("--index", action="store_true", help="Index the files for future use")
    parser.add_argument("--test-cache-loading", action="store_true", help="Test cache loading")
    parser.add_argument("--profile", action="store_true", help="Profile cache loading")
    # Add the --chat (-c) argument
    parser.add_argument("--chat", "-c", action="store_true", help="Enter chat mode")
    return parser.parse_args()


def initialize_environment() -> None:
    # Initialize colorama for cross-platform color support
    colorama.init()


def handle_modes(args: argparse.Namespace) -> None:
    if args.test_cache_loading:
        test_cache_loading(args.profile)
        return

    if args.list_history is not None:
        log.list_prompt_history(args.list_history)
        return

    user_files = args.files
    git_files = None
    if args.git_files:
        git_files = gitfiles.get_filtered_git_files()
        if args.files:
            user_files = set([gitfiles.make_relative_to_git_root(x) for x in args.files])

    combined_files = set()
    if user_files:
        combined_files.update(user_files)
    if git_files:
        combined_files.update(git_files)

    if args.index:
        index_files(args.git_files, force_reindex=True)
        return

    if args.git_files:
        index_files(args.git_files)

    if args.chat or args.prompt is None:
        egg_chat = chat.EggChat()
        egg_chat.chat_mode(args.model, git_files, list(user_files or []), initial_prompt=args.prompt)
        return

    prompt = prepare_prompt(args)
    if not prompt:
        return

    log.log_prompt(prompt)

    operations.default_mode(args.model, git_files, list(user_files), prompt)


def prepare_prompt(args: argparse.Namespace) -> Optional[str]:
    if args.prompt:
        return args.prompt

    return utils.get_prompt_from_editor_with_prefill("")


def main() -> None:
    args = parse_arguments()
    initialize_environment()
    handle_modes(args)


def test_cache_loading(profile: bool) -> None:
    if profile:
        cProfile.run("from eigengen import indexing\n_ = indexing.read_cache_state()")
    else:
        _ = indexing.read_cache_state()


def index_files(use_git_files: bool, force_reindex:bool = False) -> None:
    git_files = operations.gitfiles.get_filtered_git_files() if use_git_files else []
    indexing.index_files(git_files, force_reindex=force_reindex)


if __name__ == "__main__":
    main()
