from typing import Dict, Tuple
import re

def extract_file_content(output: str) -> Dict[str, str]:
    files: Dict[str, str] = {}
    index = 0
    output_length = len(output)

    while index < output_length:
        # Search for the next code block starting from the current index
        fence_pattern = r'^([ \t]*)###([^\n]*)\n'
        fence_regex = re.compile(fence_pattern, re.MULTILINE)
        fence_match = fence_regex.search(output, index)

        if not fence_match:
            break  # No more code blocks found

        index = fence_match.start()

        try:
            code_block_content, file_path, next_index = decode_code_block(output, index)
            index = next_index  # Move index to the end of the current code block

            if file_path:
                # Strip trailing whitespace from each line
                code_content_lines = [line.rstrip() for line in code_block_content.splitlines()]
                # Remove trailing empty lines and ensure the file ends with a newline character
                while code_content_lines and code_content_lines[-1] == '':
                    code_content_lines.pop()
                code_content = "\n".join(code_content_lines).rstrip() + "\n"
                files[file_path] = code_content
            else:
                # If filename is empty, skip this code block
                index = next_index
        except ValueError:
            # If decoding fails, skip past the current fence to avoid an infinite loop
            index = fence_match.end()

    return files


def encode_code_block(code_content, file_path=''):
    """
    Encapsulates the code content in a Markdown code block,
    using three backticks and including the file path after the backticks in both fences.
    """
    fence = f"```{file_path}"
    return f"{fence}\n{code_content}\n{fence}"


def decode_code_block(markdown_text: str, start_index: int = 0) -> Tuple[str, str, int]:
    """
    Decodes a Markdown code block starting from start_index.
    Returns a tuple of (code_block_content, file_path, index_after_code_block_end).
    """
    # Find the opening fence and file path
    fence_pattern = r'^([ \t]*)###([^\n]*)\n'
    fence_regex = re.compile(fence_pattern, re.MULTILINE)
    fence_match = fence_regex.match(markdown_text, start_index)
    if not fence_match:
        raise ValueError("No code block found at the specified start_index.")

    indent = fence_match.group(1)  # Capture any indentation (spaces or tabs)
    fence_content = fence_match.group(2).rstrip()
    code_start = fence_match.end()

    # Prepare the closing fence, which must be identical to the opening fence (including filename)
    closing_fence_pattern = (
        r'^' + re.escape(indent) + r'###' + re.escape(fence_content) + r'\s*(\n|$)'
    )
    closing_fence_regex = re.compile(closing_fence_pattern, re.MULTILINE)

    # Search for the closing fence
    closing_fence_match = closing_fence_regex.search(markdown_text, code_start)
    if not closing_fence_match:
        raise ValueError("Closing fence not found for the code block.")

    code_end = closing_fence_match.start()
    code_block_content = markdown_text[code_start:code_end]

    # Index after the closing fence
    index_after_code_block_end = closing_fence_match.end()

    file_path = fence_content.strip()

    return code_block_content, file_path, index_after_code_block_end
