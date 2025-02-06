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
from eigengen.eggrag import EggRag
from eigengen.embeddings import CodeEmbeddings

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

        # keep a set of file paths that have been introduced to the chat history
        # to avoid spamming the chat with the same file content
        self.files_history: set[str] = set()

        # Initialize EggRag instance to store file embeddings.
        # The EggRag database will be located at ~/.eigengen/rag.db.
        rag_db_path = os.path.expanduser("~/.eigengen/rag.db")
        os.makedirs(os.path.dirname(rag_db_path), exist_ok=True)
        embedding_dim = 1024  # Adjust the embedding dimension if needed.
        embeddings_provider = CodeEmbeddings()
        self.egg_rag = EggRag(self.model_tuple.summary, rag_db_path, embedding_dim, embeddings_provider)

        # Process user provided files: concatenate them for chat display and add each to EggRag.
        self.file_content = ""
        if user_files:
            for fname in user_files:
                if fname in self.files_history:
                    continue
                self.files_history.add(fname)
                abs_path = os.path.abspath(fname)

                result = utils.process_file_for_rag(abs_path, self.egg_rag, for_chat=True)
                if result:
                    self.file_content += "\n" + result

        self.kbm = keybindings.ChatKeyBindingsManager(self.quoting_state, self.messages)

    def chat_mode(
        self,
        initial_prompt: Optional[str] = None
    ) -> None:
        """
        Initiates the chat mode, handling user inputs and interactions with the LLM.

        Args:
            initial_prompt (Optional[str], optional): Pre-filled prompt content. Defaults to None.
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
                    # Input is a command
                    if (self.handle_command(prompt_input)):
                        continue

                if prompt_input.strip() == '':
                    continue

                # Prepare the original user message. If file content is present,
                # append it and then clear for one-time use.
                original_message = prompt_input
                if self.file_content and self.file_content.strip() != "":
                    original_message += "\n" + self.file_content
                    self.file_content = ""

                # Build a retrieval query from the conversation including the new message.
                query_messages = [{"role": "user", "content": original_message}]
                retrieval_chunks = operations.process_request(self.model_tuple.summary, query_messages, prompts.get_prompt("summarize_query"))
                retrieval_query = "".join(retrieval_chunks)

                # Retrieve additional context from EggRag (using top 5 matches).

                retrieved_results = self.egg_rag.retrieve(retrieval_query, top_n=10, path_prefix=self.git_root)
                rag_context = ""
                if retrieved_results:
                    context_blocks = []
                    for file_path, _, content in retrieved_results:
                        # rebase the file path to the current working directory
                        file_path = os.path.relpath(file_path, start=self.git_root)
                        if file_path in self.files_history:
                            continue
                        self.files_history.add(file_path)
                        print(f"Retrieved file: {file_path}")
                        block = f"In file: {file_path}\nContent:\n{content}\n---"
                        context_blocks.append(block)
                    rag_context = "\n".join(context_blocks)

                # Create an extended message for the provider by appending the retrieved context.
                if rag_context:
                    extended_message = original_message + "\n\nRetrieved Context:\n" + rag_context
                else:
                    extended_message = original_message

                # Create a temporary message list that includes the extended user message.
                local_messages = self.messages + [{"role": "user", "content": extended_message}]

                answer = ""
                # Use a progress indicator when processing the request.
                with ProgressIndicator() as _:
                    chunk_iterator = operations.process_request(
                        self.model_tuple.large,
                        local_messages,
                        prompts.get_prompt(self.mode)
                    )
                    for chunk in chunk_iterator:
                        answer += chunk

                # Print assistant response header with timestamp.
                timestamp = datetime.now().strftime('%I:%M:%S %p')
                print_formatted_text(
                    FormattedText([("class:assistant", f"\n[{timestamp}][Assistant] >")]),
                    style=style
                )

                formatted_response = utils.get_formatted_response_with_syntax_highlighting(
                    self.config.color_scheme, answer
                )

                # Output via pager.
                utils.pipe_output_via_pager(formatted_response)
                print("")  # Add an empty line for separation

                # Store the original message (without the retrieved context) in the conversation history.
                self.messages.append({"role": "user", "content": original_message})
                self.messages.append({"role": "assistant", "content": answer})

            except KeyboardInterrupt:
                # Handle Ctrl+C to cancel the current input
                self.pre_fill = ""
                continue
            except EOFError:
                # Handle Ctrl+D to exit
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

        for filepath in paths:
            meld.meld_changes(self.model_tuple.small, filepath, last_assistant_message)

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
