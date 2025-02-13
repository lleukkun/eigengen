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
from eigengen.providers import MODEL_CONFIGS

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
)

class EggChat:
    """
    EggChat encapsulates the interactive and non-interactive chat sessions with the LLM.

    This class handles setting up context from user files and operating modes.
    It supports interactive mode (chat_mode) with command handling as well as single-prompt mode (auto_chat).

    Attributes:
        config (EggConfig): Configuration settings including model and chat options.
        model (Model): Model used for processing requests.
        mode (str): The current operational mode (general, architect, programmer).
        quoting_state (dict): Contains state for cycling and quoting code blocks.
        messages (List[Dict[str, str]]): Conversation history.
        pre_fill (str): Prefilled text for the next prompt.
        git_root (Optional[str]): Root path of the Git repository (if any).
        files_history (set[str]): Set of file paths already processed.
        egg_rag: Instance for Retrieval Augmented Generation (or NoOp).
        target_files (List[str]): List of target file paths for context.
        initial_file_content (str): Content read from target files.
        kbm (ChatKeyBindingsManager): Manager for custom keybindings.
    """
    def __init__(self, config: EggConfig, user_files: Optional[List[str]]):
        """
        Initialize a new EggChat session.

        Args:
            config (EggConfig): The configuration object with settings.
            user_files (Optional[List[str]]): List of file paths to include as context.
        """
        self.config = config  # Store the passed config
        self.model = providers.create_model(config.model, config)
        self.mode = config.args.chat_mode
        self.quoting_state = {"current_index": -1, "code_blocks": None, "cycle_iterator": None}
        self.messages: List[Dict[str, str]] = []
        self.pre_fill = ""

        # Find the Git repository root (if available)
        self.git_root = utils.find_git_root()
        self.files_history: set[str] = set()

        # Initialize retrieval augmentation if enabled
        if config.args.rag:
            self.egg_rag = EggRag()
        else:
            self.egg_rag = NoOpEggRag()

        # Process user-provided files for context construction.
        self.target_files = []
        self.initial_file_content = ""
        if user_files:
            for fname in user_files:
                abs_path = os.path.abspath(fname)
                if abs_path in self.files_history:
                    continue
                self.files_history.add(abs_path)

                # Read the file content and encode it as a Markdown code block.
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if self.git_root:
                        rel_path = os.path.relpath(abs_path, self.git_root)
                        content = utils.encode_code_block(content, rel_path)
                    else:
                        content = utils.encode_code_block(content, fname)
                    self.initial_file_content += "\n" + content
                self.target_files.append(abs_path)

        self.kbm = keybindings.ChatKeyBindingsManager(self.quoting_state, self.messages)

    def chat_mode(
        self,
        initial_prompt: Optional[str] = None
    ) -> None:
        """
        Initiates interactive chat mode.

        Continuously prompts the user for input via a terminal session, processes commands
        (starting with '/'), augments context from files and RAG, and displays the LLM response.

        Args:
            initial_prompt (Optional[str]): An optional prefilled prompt to show in the input.

        Returns:
            None
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
                if self.initial_file_content and self.initial_file_content.strip() != "":
                    original_message += "\n" + self.initial_file_content
                    self.initial_file_content = ""

                retrieved_results = self.egg_rag.retrieve(
                    target_files=self.target_files if self.target_files else None
                )
                rag_context = ""
                if retrieved_results:
                    rag_context = "\n".join([f"{r[2]}" for r in retrieved_results])

                extended_message = original_message
                if rag_context:
                    extended_message = original_message + "\n\nRetrieved Context:\n" + rag_context

                local_messages = self.messages + [{"role": "user", "content": extended_message}]

                answer = ""
                with ProgressIndicator() as _:
                    chunk_iterator = operations.process_request(
                        self.model,
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

    def auto_chat(self, initial_prompt: str, diff_mode: bool = False) -> None:
        """
        Executes a single prompt non-interactively and prints the LLM response.
        When diff_mode is enabled, diff output is generated comparing file content
        against the code blocks in the assistant's message.

        Args:
            initial_prompt (str): The prompt text provided by the user.
            diff_mode (bool): If True, only the diff output is printed to stdout.

        Returns:
            None
        """
        style = Style.from_dict({
            "assistant": "ansigreen"
        })

        # Use the provided prompt and append any initial file context
        original_message = initial_prompt
        if self.initial_file_content and self.initial_file_content.strip() != "":
            original_message += "\n" + self.initial_file_content
            self.initial_file_content = ""

        # Retrieve additional context if available
        retrieved_results = self.egg_rag.retrieve(
            target_files=self.target_files if self.target_files else None
        )
        rag_context = ""
        if retrieved_results:
            rag_context = "\n".join([f"{r[2]}" for r in retrieved_results])

        extended_message = original_message
        if rag_context:
            extended_message = original_message + "\n\nRetrieved Context:\n" + rag_context

        local_messages = self.messages + [{"role": "user", "content": extended_message}]

        answer = ""
        with ProgressIndicator() as _:
            chunk_iterator = operations.process_request(
                self.model,
                local_messages,
                prompts.get_prompt(self.mode)
            )
            for chunk in chunk_iterator:
                answer += chunk

        if diff_mode:
            code_blocks = utils.extract_code_blocks(answer)
            diff_found = False
            for fence, lang, file_path, code, _, _ in code_blocks:
                if file_path:
                    # Adjust path based on git_root if available
                    if self.git_root and not os.path.isabs(file_path):
                        full_path = os.path.abspath(os.path.join(self.git_root, file_path))
                    else:
                        full_path = os.path.abspath(file_path)

                    try:
                        with open(full_path, "r") as f:
                            original_content = f.read()
                    except Exception:
                        original_content = ""

                    diff_text = utils.generate_unified_diff(
                        original_content,
                        code,
                        fromfile=f"a/{file_path}",
                        tofile=f"b/{file_path}"
                    )
                    print(diff_text)
                    diff_found = True
            if not diff_found:
                print("No code blocks with file paths found in the response. No diff to show.")
            return
        else:
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

    def handle_command(self, prompt_input: str) -> bool:
        """
        Processes a command input starting with '/' and routes it to the appropriate handler.

        Args:
            prompt_input (str): The full command string entered by the user.

        Returns:
            bool: True if the command was handled successfully.
        """
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
        """Handle the '/help' command by displaying available commands."""
        print(CHAT_HELP)
        return True

    def handle_quote(self, file_to_quote: str) -> bool:
        """Handle the '/quote' command by reading and quoting the specified file."""
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
        """Handle the '/reset' command by clearing all conversation messages and file history."""
        self.messages = []
        self.files_history = set()
        print("Chat messages cleared.\n")
        return True

    def handle_meld(self) -> bool:
        """Handle the '/meld' command by merging aggregated changes from the last assistant message into files."""
        last_assistant_message = next(
            (msg["content"] for msg in reversed(self.messages) if msg["role"] == "assistant"), ""
        )

        code_blocks = utils.extract_code_blocks(last_assistant_message)
        if not code_blocks:
            print("No code blocks found in the last assistant message.")
            return True

        patches_by_file = {}
        for block in code_blocks:
            _, _, block_path, block_content, _, _ = block
            if block_path:
                patches_by_file.setdefault(block_path, []).append(block_content)

        if not patches_by_file:
            print("No code blocks with valid file paths found.")
            return True

        for file_path, patches in patches_by_file.items():
            aggregated_patch = "\n".join(patches)
            meld.meld_changes(
                file_path,
                aggregated_patch,
                self.git_root,
                unified_diff=True if self.model.model_name.lower().startswith("gemini") else False
            )

        return True

    def handle_model(self, *args) -> bool:
        """Handle the '/model' command for switching or displaying the current model."""

        def print_supported_models():
            print("Supported models:")
            supported_models = list(MODEL_CONFIGS.keys())
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
            if new_model in MODEL_CONFIGS:
                self.config.model = new_model
                print(f"Model switched to: {new_model}")
            else:
                print(f"Unsupported model: {new_model}\n")
                print_supported_models()
            return True

    def handle_mode(self, *args) -> bool:
        """Handle the '/mode' command for switching or displaying the current operating mode."""
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
        """Handle the '/exit' command by terminating the chat session."""
        sys.exit(0)
        return True  # This line will not be reached, but added for consistency
