import dataclasses
import difflib
import io  # Add this import for StringIO
import logging
import os
import re
import subprocess
import tempfile
from typing import Optional

import pygments
import pygments.formatters  # Ensure this import is present
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.lexers.special import TextLexer
from pygments.styles import get_style_by_name

from eigengen.config import EggConfig

logger = logging.getLogger(__name__)


def encode_code_block(code_content: str, file_path: str = "") -> str:
    """
    Encapsulates the code content in a Markdown code block,
    using a variable-length fence to avoid conflicts with backticks in the code content.
    Includes the file path after the opening fence.

    Parameters:
        code_content (str): The code content to be encapsulated.
        file_path (str, optional): The file path to include after the code fence. Defaults to ''.

    Returns:
        str: The code content encapsulated within a Markdown code block.
    """
    # Find all sequences of backticks in the code content
    backtick_sequences = re.findall(r"`+", code_content)
    if backtick_sequences:
        # Determine the maximum length of backtick sequences found
        max_backticks = max(len(seq) for seq in backtick_sequences)
        # Fence length is one more than the maximum found, with a minimum of 3
        fence_length = max(max_backticks + 1, 3)
    else:
        # Default fence length if no backticks are found
        fence_length = 3

    # Create the fence using the calculated fence length
    fence = "`" * fence_length
    opening_fence = f"{fence}{file_path}"
    closing_fence = fence

    # Return the code content encapsulated within the fences
    return f"{opening_fence}\n{code_content}\n{closing_fence}"


@dataclasses.dataclass
class CodeBlock:
    fence: str
    lang: str
    path: str
    content: str
    start_index: int
    end_index: int


def extract_code_blocks(response: str) -> list[CodeBlock]:
    """
    Extracts code blocks from a response string.

    Parameters:
        response (str): The response string containing code blocks in Markdown format.

    Returns:
        List[Tuple[str, str, str, str, int, int]]: A list of tuples containing information about each code block.
            Each tuple contains:
                - fence (str): The code fence used (e.g., backticks or tildes).
                - actual_lang (str): The language identifier specified after the opening fence.
                - actual_path (str): The file path specified after the language identifier.
                - code (str): The extracted code content.
                - start_index (int): The start index of the code block in the response string.
                - end_index (int): The end index of the code block in the response string.
    """
    code_blocks: list[CodeBlock] = []

    # Regular expression pattern to match code blocks with variable-length fences and indentation
    code_block_pattern = re.compile(
        r"^(?P<indent>[ \t]*)"  # Leading indentation (spaces or tabs)
        r"(?P<fence>`{3,}|~{3,})"  # Opening code fence (at least 3 backticks or tildes)
        r"[ \t]*(?P<lang_path>\S+)?"  # Optional language identifier and/or file path
        r"[ \t]*\n"  # Optional trailing spaces and a newline
        r"(?P<code>.*?)"  # Code content (non-greedy)
        r"\n"  # Newline before the closing fence
        r"(?P=indent)"  # Matching leading indentation
        r"(?P=fence)"  # Closing code fence matching the opening fence
        r"[ \t]*\n?",  # Optional trailing spaces and an optional newline
        re.DOTALL | re.MULTILINE,
    )

    # Find all code blocks in the response string
    for match in code_block_pattern.finditer(response):
        fence = match.group("fence")
        lang_path = match.group("lang_path") or ""
        code = match.group("code")
        start_index = match.start()
        end_index = match.end()

        # Split the language and path if both are provided
        actual_lang = ""
        actual_path = ""
        if lang_path:
            lang_parts = lang_path.split(";")
            actual_lang = lang_parts[0]
            if len(lang_parts) > 1:
                actual_path = lang_parts[1]

        # Append the extracted code block information to the list
        code_blocks.append(CodeBlock(fence, actual_lang, actual_path, code, start_index, end_index))

    return code_blocks


def generate_unified_diff(original_content: str, new_content: str, fromfile: str, tofile: str) -> str:
    """
    Generate a unified diff between original and new content.

    Args:
        original_content (str): The original file contents.
        new_content (str): The new file contents.
        fromfile (str): The file label for the original content.
        tofile (str): The file label for the new content.

    Returns:
        str: The unified diff as a string with a trailing newline.
    """
    original_lines = original_content.splitlines()
    new_lines = new_content.splitlines()
    diff_lines = difflib.unified_diff(original_lines, new_lines, fromfile=fromfile, tofile=tofile, lineterm="")
    diff_text = "\n".join(diff_lines) + "\n"
    return diff_text


def get_prompt_from_editor_with_prefill(config: EggConfig, prefill_content: str) -> Optional[str]:
    """
    Opens a temporary file with prefilled content in the user's default editor and returns the edited content.

    Parameters:
        prefill_content (str): The initial content to prefill in the editor.

    Returns:
        Optional[str]: The content after editing, or None if an error occurs.
    """
    prompt_content = ""
    # Create a temporary file with the prefill content
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as temp_file:
        temp_file_path = temp_file.name
        temp_file.write(prefill_content)

    try:
        # Get the user's preferred editor from the configuration, prioritizing config over environment variables
        editor = get_editor_command(config)
        command = editor + " " + temp_file_path
        # Open the editor with the temporary file
        subprocess.run(command, shell=True, check=True)

        # Read the content after editing
        with open(temp_file_path, "r") as file:
            prompt_content = file.read()

        return prompt_content
    finally:
        # Remove the temporary file to clean up
        os.remove(temp_file_path)


def get_editor_command(config: EggConfig) -> str:
    """
    Determine the text editor command to use.
    Priority:
    1. Config file
    2. EDITOR environment variable
    3. Defaults to 'nano'
    """
    if config.editor:
        return config.editor

    env_editor = os.getenv("EDITOR")
    if env_editor:
        return env_editor
    else:
        return "nano"


def get_formatted_response_with_syntax_highlighting(color_scheme: str, response: str) -> str:
    """
    Returns the response with syntax-highlighted code blocks as a formatted string,
    utilizing the extract_code_blocks function to parse code blocks.
    """
    output = io.StringIO()
    last_end = 0

    # Extract code blocks along with their positions and fences
    code_blocks = extract_code_blocks(response)

    # Get the Pygments style based on the color scheme
    try:
        pygments_style = get_style_by_name(color_scheme)
    except Exception:
        logger.warning(f"Unknown color scheme '{color_scheme}'. Falling back to 'github-dark'.")
        pygments_style = get_style_by_name("monokai")

    # Create a formatter with the specified style
    formatter = pygments.formatters.TerminalFormatter(style=pygments_style)

    for block in code_blocks:
        # Append text before the code block
        output.write(response[last_end:block.start_index])

        # Reconstruct the opening fence with optional language and path
        lang_path = ";".join(filter(None, [block.lang, block.path]))
        output.write(f"{block.fence}{lang_path}\n")

        # Determine the lexer to use for syntax highlighting
        if block.lang:
            try:
                lexer = get_lexer_by_name(block.lang.lower())
            except Exception:
                lexer = guess_lexer(block.content)
        else:
            try:
                lexer = guess_lexer(block.content)
            except Exception:
                lexer = TextLexer()

        # Syntax-highlight the code content, output as ANSI text
        formatted_code = pygments.highlight(block.content, lexer, formatter)

        output.write(formatted_code)

        # Append the closing fence
        output.write(f"\n{block.fence}\n")

        last_end = block.end_index

    # Append any remaining text after the last code block
    output.write(response[last_end:])

    return output.getvalue()


def is_running_in_powershell():
    """Detects if the script is running inside PowerShell."""
    return "PSModulePath" in os.environ


def pipe_output_via_pager(output_str: str) -> None:
    """
    Pipes the given string to a pager like 'less', retaining colors.
    """
    # Get the pager command from the environment, defaulting to 'less' on linux and macos
    # On Windows, 'more' is used as 'less' is not available by default

    # test if the OS is Windows
    pager_command = None
    encoding = "utf-8"
    if os.name == "nt":
        pager_command = os.environ.get("PAGER", "more")
        if is_running_in_powershell():
            encoding = "utf-16"
    else:
        pager_command = os.environ.get("PAGER", "less -R -E -X")

    with subprocess.Popen(pager_command, shell=True, stdin=subprocess.PIPE) as pager:
        if pager.stdin is not None:
            pager.stdin.write(output_str.encode(encoding))
            pager.stdin.close()
        pager.wait()


def get_git_files(pattern: Optional[str] = None) -> list[str]:
    """
    Returns list of Git-tracked files in the current repository.
    If a pattern is provided, it will be used to limit the files. For example, passing "*.py"
    will return only Python files.
    """
    try:
        # If a pattern is specified, add '--' then the pattern to the command so that it is interpreted correctly.
        if pattern:
            result = subprocess.run(["git", "ls-files", "-z", "--", pattern], capture_output=True, check=True)
        else:
            result = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True)
        return result.stdout.decode("utf-8").split("\x00")[:-1]
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"Git error: {str(e)}")
        return []


def get_all_files(git_root: str) -> list[str]:
    """
    Returns a list of all tracked and untracked files in the repository.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "-c", "--others", "--exclude-standard"],
            capture_output=True,
            check=True,
            text=True,
            cwd=git_root,
        )
        return result.stdout.split("\x00")[:-1]
    except subprocess.CalledProcessError as e:
        logger.error(f"Git error: {e}")
        return []


def find_git_root() -> Optional[str]:
    """
    Returns the path to the root of the current Git repository.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
            text=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def extract_change_descriptions(text: str) -> dict[str, list[str]]:
    # Regular expression pattern to match change descriptions that are
    # enclosed in <egg_output filename="dirpath/filename">...</egg_output> tags.
    change_desc_pattern = re.compile(
        r"<egg_output filename=\"(?P<filename>[^\"]+)\">(?P<description>.*?)</egg_output>",
        re.DOTALL,
    )
    descriptions: dict[str, list[str]] = {}
    for match in change_desc_pattern.finditer(text):
        filename = match.group("filename")
        description = match.group("description").strip()
        if filename not in descriptions:
            descriptions[filename] = []
        descriptions[filename].append(description)

    return descriptions
