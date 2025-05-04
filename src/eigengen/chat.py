import os
import sys
from datetime import datetime
from typing import Optional

import pygments.style
from prompt_toolkit import PromptSession
from prompt_toolkit.clipboard.pyperclip import PyperclipClipboard
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.styles import Style
from pygments.token import Token

from eigengen import keybindings, meld, prompts, providers, utils
from eigengen.config import EggConfig

# New imports for EggRag support
from eigengen.eggrag import EggRag, NoOpEggRag
from eigengen.progress import ProgressIndicator

# disable T201 for this file
# ruff: noqa: T201

# New constant for time format
TIME_FORMAT = "%I:%M:%S %p"


class CustomStyle(pygments.style.Style):
    """
    CustomStyle provides a custom Pygments style for syntax highlighting within the chat interface.

    It defines a mapping from Pygments token types (e.g. Keyword, String, Comment) to ANSI color
    codes, which is used to enhance the readability of both user and assistant outputs.
    """
    default_style = ""
    styles = {
        Token.Keyword: "ansigreen",
        Token.String: "ansiyellow",
        Token.Comment: "ansiblue",
        Token.Name: "",
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
    "/mode                 Mode of the system: general, programmer (default)\n"
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
    EggChat manages interactive and non-interactive chat sessions with a language model (LLM).

    It assembles context from user-provided files and configures the operational mode, supporting both
    continuous interactive sessions (via chat_mode) and single-prompt requests (via auto_chat).

    Attributes:
        config (EggConfig): Configuration settings including model, prompt, and chat options.
        pm: The provider manager instance responsible for handling model requests.
        mode (str): Operational mode, either "general" or "programmer".
        quoting_state (dict): State object for managing code block quoting (cycling, indexing, etc.).
        messages (List[Dict[str, str]]): History of conversation messages.
        pre_fill (str): Prefilled text for upcoming prompts.
        git_root (Optional[str]): Path to the root of a Git repository, if detected.
        files_history (set[str]): Set of file paths that have already been processed.
        egg_rag (EggRag or NoOpEggRag): Instance for retrieval augmented generation, if enabled.
        target_files (List[str]): List of file paths used to construct the initial context.
        initial_file_content (str): Aggregated and formatted contents from target files.
        kbm: ChatKeyBindingsManager responsible for custom keybindings during chat sessions.
    """
    def __init__(self, config: EggConfig, user_files: Optional[list[str]]):
        """
        Initialize an EggChat session with configuration settings and optional file context.

        Args:
            config (EggConfig): The configuration object with model and chat parameters.
            user_files (Optional[List[str]]): Optional list of file paths to include as initial context.

        Side Effects:
            Processes user files to aggregate context, initializes the provider manager, detects a Git repository,
            and sets up retrieval augmentation if enabled.
        """
        self.config = config  # Store the passed configuration
        self.pm = providers.ProviderManager(config.model_spec_str, config)
        if config.args.general:
            self.mode = "general"
        elif config.args.tutor:
            self.mode = "tutor"
        else:
            self.mode = "programmer"

        self.quoting_state = {"current_index": -1, "code_blocks": None, "cycle_iterator": None}
        self.messages: list[tuple[str, str]] = []
        self.pre_fill = ""

        # Find the Git repository root (if available)
        self.git_root = utils.find_git_root()
        self.files_history: set[str] = set()
        if self.config.args.high:
            self.reasoning_effort = providers.ReasoningAmount.HIGH
        elif self.config.args.low:
            self.reasoning_effort = providers.ReasoningAmount.LOW
        else:
            self.reasoning_effort = providers.ReasoningAmount.MEDIUM

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

                # Read file content and encode it as a Markdown code block using a cwd-relative path.
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    rel_path = os.path.relpath(abs_path, os.getcwd())
                    content = utils.encode_code_block(content, rel_path)
                    self.initial_file_content += "\n" + content
                self.target_files.append(abs_path)

        self.kbm = keybindings.ChatKeyBindingsManager(self.quoting_state, self.messages)

    def _prepare_full_message(self, user_message: str) -> str:
        """
        Prepare the complete message by appending file context and retrieval augmented context.

        The method appends any pre-loaded initial file content to the user's message and then adds
        additional context obtained via retrieval augmentation (if target files are available). After use,
        the initial file content is cleared to avoid duplication in future messages.

        Args:
            user_message (str): The base message from the user.

        Returns:
            str: The full message including appended file content and retrieved context.
        """
        full_message = user_message
        if self.initial_file_content and self.initial_file_content.strip():
            full_message += "\n" + self.initial_file_content
            self.initial_file_content = ""
        if self.target_files:
            retrieved_results = self.egg_rag.retrieve(target_files=self.target_files)
            if retrieved_results:
                rag_context = "\n".join(r[2] for r in retrieved_results)
                full_message += "\n\nRetrieved Context:\n" + rag_context
        return full_message

    def _get_answer(self, user_message: str, use_progress: bool = False) -> str:
        """
        Construct the full prompt and dispatch a request to the LLM to obtain a streaming response.

        It builds the complete message (by including file and RAG context), appends it to the conversation
        history, and iteratively collects chunks from the model’s response. Optionally, a progress indicator
        is displayed while waiting for the response.

        Args:
            user_message (str): The original user message.
            use_progress (bool): If True, displays a progress indicator during the request.

        Returns:
            str: The aggregated response from the assistant.
        """
        full_message = self._prepare_full_message(user_message)
        message_list = self.messages + [("user", full_message)]
        answer_chunks = []
        with ProgressIndicator(use_progress) as _:
            for chunk in self.pm.process_request(
                providers.ModelType.LARGE,
                self.reasoning_effort,
                prompts.get_prompt(self.mode),
                message_list,
            ):
                answer_chunks.append(chunk)
        return "".join(answer_chunks)

    def chat_mode(self, initial_prompt: Optional[str] = None) -> None:
        """
        Run an interactive chat session with continuous message prompting.

        In this mode, the user is continuously prompted for input and commands (prefixed with '/')
        are processed. Regular messages are sent to the LLM after augmenting with any necessary context,
        and responses are displayed with syntax highlighting. Keyboard shortcuts are enabled for a
        more efficient interactive experience.

        Args:
            initial_prompt (Optional[str]): An optional initial text to pre-fill the input prompt.

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
                style = Style.from_dict({"user": "ansicyan", "assistant": "ansigreen"})

                def custom_prompt():
                    return [("class:user", f"\n[{datetime.now().strftime(TIME_FORMAT)}][User] >\n")]

                prompt_input = session.prompt(
                    custom_prompt,
                    style=style,
                    multiline=True,
                    enable_history_search=True,
                    refresh_interval=5,
                    default=self.pre_fill or "",
                )
                self.pre_fill = ""  # Reset pre-fill after use

                if prompt_input.startswith("/"):
                    if self.handle_command(prompt_input):
                        continue

                if prompt_input.strip() == "":
                    continue

                original_message = prompt_input
                answer = self._get_answer(original_message, use_progress=True)

                timestamp = datetime.now().strftime(TIME_FORMAT)
                print_formatted_text(FormattedText([("class:assistant", f"\n[{timestamp}][Assistant] >")]), style=style)
                formatted_response = utils.get_formatted_response_with_syntax_highlighting(
                    self.config.color_scheme, answer
                )
                utils.pipe_output_via_pager(formatted_response)
                print("")

                self.messages.append(("user", original_message))
                self.messages.append(("assistant", answer))

            except KeyboardInterrupt:
                self.pre_fill = ""
                continue
            except EOFError:
                break

    def auto_chat(self, initial_prompt: str, diff_mode: bool = False, interactive: bool = False) -> None:
        """
        Execute a non-interactive single prompt and display the assistant's response.

        When diff_mode is enabled, the method extracts change descriptions from the assistant's output,
        applies these changes to the corresponding files, generates diffs, and then displays them.
        Otherwise, the full response is formatted and paged to the user.

        Args:
            initial_prompt (str): The prompt text to be sent to the LLM.
            diff_mode (bool): Flag indicating whether to output diffs between file contents and proposed changes.

        Returns:
            None
        """
        style = Style.from_dict({"assistant": "ansigreen"})

        # Use the provided prompt and append any initial file context
        answer = self._get_answer(initial_prompt, use_progress=interactive)
        self.messages.append(("user", initial_prompt))
        self.messages.append(("assistant", answer))
        if diff_mode:
            if interactive:
                self.handle_meld()
                return
            else:
                changes = utils.extract_change_descriptions(answer)
                diff_found = False
                for file_path, change_list in changes.items():
                    if file_path:
                        # Prefer file path relative to the current working directory if it exists.
                        full_path = os.path.abspath(file_path)

                        try:
                            with open(full_path, "r", encoding="utf-8") as f:
                                original_content = f.read()
                        except Exception:
                            original_content = ""
                        new_content = meld.apply_changes(self.pm, full_path, original_content, "\n".join(change_list),
                                                         use_progress=interactive)
                        diff_text = meld.produce_diff(full_path, original_content, new_content)
                        print(diff_text)
                        diff_found = True
                if not diff_found:
                    print("No changes with file paths found in the response. No diff to show.")
                return
        else:
            timestamp = datetime.now().strftime(TIME_FORMAT)
            print_formatted_text(FormattedText([("class:assistant", f"\n[{timestamp}][Assistant] >")]), style=style)
            formatted_response = utils.get_formatted_response_with_syntax_highlighting(self.config.color_scheme, answer)
            utils.pipe_output_via_pager(formatted_response)
            print("")

    def handle_command(self, prompt_input: str) -> bool:
        """
        Process a chat command (prefixed with '/') and dispatch it to the corresponding handler.

        The function extracts the command and any accompanying arguments from the user input. If the
        command is not recognized, a default unknown command handler is invoked.

        Args:
            prompt_input (str): The full command string entered by the user.

        Returns:
            bool: True if the command was processed successfully; otherwise, defaults to True.
        """
        command, *args = prompt_input.strip().split(maxsplit=1)

        def _unknown_command(**_) -> bool:
            print(f"Unknown command {command}")
            return True

        handler = {
            "/help": self.handle_help,
            "/quote": self.handle_quote,
            "/reset": self.handle_reset,
            "/meld": self.handle_meld,
            "/mode": self.handle_mode,
            "/exit": self.handle_exit,
        }.get(command, _unknown_command)

        return handler(*args) if args else handler()

    def handle_help(self) -> bool:
        """
        Process the '/help' command, displaying available chat commands and keyboard shortcuts.

        Returns:
            bool: Always returns True after displaying the help message.
        """
        print(CHAT_HELP)
        return True

    def handle_quote(self, file_to_quote: str) -> bool:
        """
        Process the '/quote' command by reading a given file and pre-formatting its contents as a quote.

        Each line in the file is prefixed with '> ' to denote quoted text. The pre-formatted content is then
        loaded into the prompt for further editing or message submission.

        Args:
            file_to_quote (str): The file path of the file to be quoted.

        Returns:
            bool: True after processing the command.
        """
        if not file_to_quote.strip():
            print("Usage: /quote <file_path>")
            return True
        if os.path.isfile(file_to_quote):
            with open(file_to_quote, "r", encoding="utf-8") as f:
                content = f.read()
            quoted_content = "\n".join(f"> {line}" for line in content.splitlines())
            self.pre_fill = quoted_content  # Pre-fill the next prompt with the quoted content
        else:
            print(f"File '{file_to_quote}' not found.\n")
        return True

    def handle_reset(self) -> bool:
        """
        Process the '/reset' command by clearing the conversation history and file processing history.

        Returns:
            bool: True after successfully clearing all stored messages and files history.
        """
        self.messages = []
        self.files_history = set()
        print("Chat messages cleared.\n")
        return True

    def handle_meld(self) -> bool:
        """
        Process the '/meld' command to merge changes from the last assistant message into the appropriate files.

        It extracts file-specific changes (typically formatted as code blocks with file paths) and applies these
        changes to update the corresponding files.

        Returns:
            bool: True after attempting the file merging process.
        """
        last_assistant_message = next(
            (msg[1] for msg in reversed(self.messages) if msg[0] == "assistant"), ""
        )

        changes = utils.extract_change_descriptions(last_assistant_message)
        if not changes or len(changes) == 0:
            print("No changes found in the last assistant message.")
            return True

        for file_path, change_list in changes.items():
            aggregated_changes = "\n".join(change_list)
            meld.meld_changes(
                self.pm,
                file_path,
                aggregated_changes,
                self.git_root if self.git_root else "./",
            )

        return True

    def handle_mode(self, *args: str) -> bool:
        """
        Process the '/mode' command for displaying or switching the operational mode.

        If invoked without arguments, the current mode is displayed. If an argument is provided,
        it attempts to change the mode to either "general" or "programmer".

        Args:
            *args: Additional arguments provided with the command.

        Returns:
            bool: True after processing the mode command.
        """
        if not args:
            print(f"Current mode: {self.mode}")
        else:
            new_mode = args[0].strip()
            if new_mode in ["general", "programmer"]:
                self.mode = new_mode
                print(f"Mode switched to: {new_mode}")
            else:
                print(f"Unsupported mode: {new_mode}")
                print("Supported modes are: general, programmer")
        return True

    def handle_exit(self) -> bool:
        """
        Process the '/exit' command to terminate the chat session immediately.

        This method calls sys.exit(0), so control will typically not return here.

        Returns:
            bool: True (note: this return value is never reached due to process termination).
        """
        sys.exit(0)
