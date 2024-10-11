from typing import Dict, List, Tuple, Optional
import re
import tempfile
import subprocess
import os
from eigengen.config import EggConfig  # Add this import

def encode_code_block(code_content, file_path=''):
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
    backtick_sequences = re.findall(r'`+', code_content)
    if backtick_sequences:
        # Determine the maximum length of backtick sequences found
        max_backticks = max(len(seq) for seq in backtick_sequences)
        # Fence length is one more than the maximum found, with a minimum of 3
        fence_length = max(max_backticks + 1, 3)
    else:
        # Default fence length if no backticks are found
        fence_length = 3

    # Create the fence using the calculated fence length
    fence = '`' * fence_length
    opening_fence = f"{fence}{file_path}"
    closing_fence = fence

    # Return the code content encapsulated within the fences
    return f"{opening_fence}\n{code_content}\n{closing_fence}"

def extract_code_blocks(response: str) -> List[Tuple[str, str, str, str, int, int]]:
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
    code_blocks = []

    # Regular expression pattern to match code blocks with variable-length fences and indentation
    code_block_pattern = re.compile(
        r'^(?P<indent>[ \t]*)'          # Leading indentation (spaces or tabs)
        r'(?P<fence>`{3,}|~{3,})'       # Opening code fence (at least 3 backticks or tildes)
        r'[ \t]*(?P<lang_path>\S+)?'    # Optional language identifier and/or file path
        r'[ \t]*\n'                     # Optional trailing spaces and a newline
        r'(?P<code>.*?)'                # Code content (non-greedy)
        r'\n'                           # Newline before the closing fence
        r'(?P=indent)'                  # Matching leading indentation
        r'(?P=fence)'                   # Closing code fence matching the opening fence
        r'[ \t]*\n?',                   # Optional trailing spaces and an optional newline
        re.DOTALL | re.MULTILINE
    )

    # Find all code blocks in the response string
    for match in code_block_pattern.finditer(response):
        fence = match.group('fence')
        lang_path = match.group('lang_path') or ""
        code = match.group('code')
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
        code_blocks.append((fence, actual_lang, actual_path, code, start_index, end_index))

    return code_blocks

def get_prompt_from_editor_with_prefill(prefill_content: str) -> Optional[str]:
    """
    Opens a temporary file with prefilled content in the user's default editor and returns the edited content.

    Parameters:
        prefill_content (str): The initial content to prefill in the editor.

    Returns:
        Optional[str]: The content after editing, or None if an error occurs.
    """
    prompt_content = ""
    # Create a temporary file with the prefill content
    with tempfile.NamedTemporaryFile(mode='w+', suffix=".txt", delete=False) as temp_file:
        temp_file_path = temp_file.name
        temp_file.write(prefill_content)

    try:
        # Get the user's preferred editor from the configuration, prioritizing config over environment variables
        editor = get_editor_command()
        command = editor + " " + temp_file_path
        # Open the editor with the temporary file
        subprocess.run(command, shell=True, check=True)

        # Read the content after editing
        with open(temp_file_path, 'r') as file:
            prompt_content = file.read()

        return prompt_content
    finally:
        # Remove the temporary file to clean up
        os.remove(temp_file_path)

def get_editor_command() -> str:
    """
    Determine the text editor command to use.
    Priority:
    1. Config file
    2. EDITOR environment variable
    3. Defaults to 'nano'
    """
    config = EggConfig.load_config()
    if config.editor:
        return config.editor
    elif os.getenv("EDITOR"):
        return os.getenv("EDITOR")
    else:
        return "nano"
