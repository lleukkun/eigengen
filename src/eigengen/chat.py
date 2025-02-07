import os
import sys
from typing import Dict, List, Optional
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.clipboard.pyperclip import PyperclipClipboard

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.shortcuts import print_formatted_text
from pygments.token import Token

import pygments.style

from eigengen import operations, utils, keybindings, meld, providers, prompts
from eigengen.progress import ProgressIndicator
from eigengen.config import EggConfig
from eigengen.providers import PROVIDER_CONFIGS

# New imports for EggRag support
from eigengen.eggrag import EggRag, NoOpEggRag

class CustomStyle(pygments.style.Style):
    default_style = ""
    styles = {
        Token.Keyword: 'ansigreen',
        Token.String: 'ansiyellow',
        Token.Comment: 'ansiblue',
        Token.Name: '',
        # Add more token styles as desired
    }

CHAT_HELP = (
    "Available commands:\n\n"
    "/help                 Display this help message.\n"
    "/exit                 Exit the chat session.\n"
    "/meld [<path1>, ...]  Merge changes from the latest assistant message into\n"
    "                      the specified file paths.\n"
    "                      If no paths are provided, changes will be applied\n"
    "                      to all files referenced in the latest assistant message.\n"
    "/mode                 Mode of the system: general, architect, programmer (default)\n"
    "/model [<model>]      Display current model or switch to a specified model.\n"
    "/quote <path>         Read and quote the contents of a file into the buffer.\n"
    "/reset                Clear all messages.\n"
    "\nKeyboard Shortcuts:\n"
    "Ctrl + J              Submit your message.\n"
    "Ctrl + X, E           Open the prompt in your default editor ($EDITOR).\n"
    "Ctrl + X, Y           Copy the entire conversation to the clipboard.\n"
    "Ctrl + X, Up Arrow    Cycle through response code blocks and quote them in the buffer.\n"
    "\nFeel free to use these commands to manage your chat session effectively!"
)

class EggChat:
    def __init__(self,
                 config: EggConfig,
                 user_files: Optional[List[str]]):
        self.config = config  # Store the passed config
        self.model_tuple = providers.create_model_tuple(config.model)
        self.mode = config.args.chat_mode
        self.quoting_state = {
            "current_index": -1,
            "code_blocks": None,
            "cycle_iterator": None
        }
        self.messages: List[Dict[str, str]] = []
        self.pre_fill = ""

        # find current git root if any
        self.git_root = utils.find_git_root()
        self.files_history: set[str] = set()

        # NEW: Use RAG only if enabled; otherwise, use a no-op object.
        if config.args.rag:
            self.egg_rag = EggRag()
        else:
            self.egg_rag = NoOpEggRag()

        # NEW: Process user provided files as target files for context-construction.
        self.target_files = []
        self.initial_file_content = ""
        if user_files:
            for fname in user_files:
                abs_path = os.path.abspath(fname)
                if abs_path in self.files_history:
                    continue
                self.files_history.add(abs_path)
                print(f"Processing file: {abs_path}")
                # read the file content
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    print("adding to prefill")
                    self.initial_file_content += "\n" + utils.encode_code_block(content, fname)
                self.target_files.append(abs_path)

        self.kbm = keybindings.ChatKeyBindingsManager(self.quoting_state, self.messages)

    def chat_mode(
        self,
        initial_prompt: Optional[str] = None
    ) -> None:
        """
        Initiates the chat mode, handling user inputs and interactions with the LLM.
        """
        session = PromptSession(key_bindings=self.kbm.get_kb(), clipboard=PyperclipClipboard())
        print(
            "Entering Chat Mode. Type '/help' for available commands.\n"
            "Type your messages below.\n(Type '/exit' to quit.)"
        )

        self.pre_fill = initial_prompt

        while True:
            try:
                style = Style.from_dict({
                    "user": "ansicyan",
                    "assistant": "ansigreen"
                })

                def custom_prompt():
                    return [("class:user", f"\n[{datetime.now().strftime('%I:%M:%S %p')}][User] >\n")]

                prompt_input = session.prompt(
                    custom_prompt,
                    style=style,
                    multiline=True,
                    enable_history_search=True,
                    refresh_interval=5,
                    default=self.pre_fill or ""
                )
                self.pre_fill = ""  # Reset pre_fill after use

                if prompt_input.startswith("/"):
                    if (self.handle_command(prompt_input)):
                        continue

                if prompt_input.strip() == '':
                    continue

                original_message = prompt_input
                # If any pre-filled content exists from target files, append it
                if self.initial_file_content and self.initial_file_content.strip() != "":
                    original_message += "\n" + self.initial_file_content
                    self.initial_file_content = ""

                # Retrieve additional context.
                # NEW: If target files are provided, pass them into egg_rag.retrieve so it will use the new token-based context system.
                retrieved_results = self.egg_rag.retrieve(
                    target_files=self.target_files if self.target_files else None
                )
                rag_context = ""
                if retrieved_results:
                    rag_context = "\n".join([f"{r[2]}" for r in retrieved_results])

                # Append retrieved (aggregated) context if available.
                extended_message = ""
                if rag_context:
                    extended_message = original_message + "\n\nRetrieved Context:\n" + rag_context
                else:
                    extended_message = original_message

                local_messages = self.messages + [{"role": "user", "content": extended_message}]

                answer = ""
                with ProgressIndicator() as _:
                    chunk_iterator = operations.process_request(
                        self.model_tuple.large,
                        local_messages,
                        prompts.get_prompt(self.mode)
                    )
                    for chunk in chunk_iterator:
                        answer += chunk

                timestamp = datetime.now().strftime('%I:%M:%S %p')
                print_formatted_text(
                    FormattedText([("class:assistant", f"\n[{timestamp}][Assistant] >")]),
                    style=style
                )

                formatted_response = utils.get_formatted_response_with_syntax_highlighting(
                    self.config.color_scheme, answer
                )

                utils.pipe_output_via_pager(formatted_response)
                print("")

                self.messages.append({"role": "user", "content": original_message})
                self.messages.append({"role": "assistant", "content": answer})

            except KeyboardInterrupt:
                self.pre_fill = ""
                continue
            except EOFError:
                break

    def handle_command(self, prompt_input: str) -> bool:
        command, *args = prompt_input.strip().split(maxsplit=1)

        def _unknown_command() -> bool:
            print(f"Unknown command {command}")
            return True

        handler = {
            '/help': self.handle_help,
            '/quote': self.handle_quote,
            '/reset': self.handle_reset,
            '/meld': self.handle_meld,
            '/model': self.handle_model,
            '/mode': self.handle_mode,
            '/exit': self.handle_exit
        }.get(command, _unknown_command)

        return handler(*args) if args else handler()

    def handle_help(self) -> bool:
        """Handle the /help command."""
        print(CHAT_HELP)
        return True

    def handle_quote(self, file_to_quote: str) -> bool:
        """Handle the /quote command."""
        if os.path.exists(file_to_quote):
            with open(file_to_quote, 'r') as f:
                content = f.read()
            # Prefix each line with '> '
            quoted_content = '\n'.join(f'> {line}' for line in content.splitlines())
            self.pre_fill = quoted_content  # Pre-fill the next prompt with quoted content
        else:
            print(f"File '{file_to_quote}' not found.\n")
        return True

    def handle_reset(self) -> bool:
        """Handle the /reset command."""
        self.messages = []
        self.files_history = set()
        print("Chat messages cleared.\n")
        return True

    def handle_meld(self, paths_input: Optional[str] = None) -> bool:
        """Handle the /meld command."""
        last_assistant_message = next(
            (msg["content"] for msg in reversed(self.messages) if msg["role"] == "assistant"), ""
        )

        if not paths_input:
            # No paths provided, extract file paths from the last assistant message's code blocks
            code_blocks = utils.extract_code_blocks(last_assistant_message)
            paths = {path for _, _, path, _, _, _ in code_blocks if path}
            if not paths:
                print("No file paths found in the latest assistant message.\n")
                return True
        else:
            paths = set(paths_input.split())

        for f in paths:
            # If we have a git root and the file is not an absolute path, assume that
            # the assistant message provided a path relative to the git root.
            if self.git_root and not os.path.isabs(f):
                full_path = os.path.normpath(os.path.join(self.git_root, f))
                # Convert full path into a path relative to the current working directory.
                adjusted = os.path.relpath(full_path, os.getcwd())
            else:
                adjusted = f
            # Pass the git_root into meld_changes so that the code block matching
            # in meld.py can compute absolute paths consistently.
            meld.meld_changes(self.model_tuple.small, adjusted, last_assistant_message, git_root=self.git_root)
            # Reindex using the adjusted file path.
            abs_filepath = os.path.abspath(adjusted)
            utils.process_file_for_rag(abs_filepath, self.egg_rag, for_chat=False)
            print(f"Reindexed file: {adjusted}")

        return True

    def handle_model(self, *args) -> bool:
        """Handle the /model command."""

        def print_supported_models():
            print("Supported models:")
            supported_models = list(PROVIDER_CONFIGS.keys())
            for m in supported_models:
                print(f" - {m}")

        if not args:
            # No argument provided; display current model and supported models
            print(f"Current model: {self.config.model}\n")
            print_supported_models()
            return True
        else:
            # Argument provided; attempt to switch model
            new_model = args[0].strip()
            if new_model in PROVIDER_CONFIGS:
                self.config.model = new_model
                print(f"Model switched to: {new_model}")
            else:
                print(f"Unsupported model: {new_model}\n")
                print_supported_models()
            return True

    def handle_mode(self, *args) -> bool:
        """Handle the /mode command."""
        if not args:
            print(f"Current mode: {self.mode}")
        else:
            new_mode = args[0].strip()
            if new_mode in ["general", "architect", "programmer"]:
                self.mode = new_mode
                print(f"Mode switched to: {new_mode}")
            else:
                print(f"Unsupported mode: {new_mode}")
                print("Supported modes are: general, architect, programmer")
        return True

    def handle_exit(self) -> bool:
        """Handle the /exit command."""
        sys.exit(0)
        return True  # This line will not be reached, but added for consistency
