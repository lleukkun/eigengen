import logging
import os

logger = logging.getLogger(__name__)


def get_prompt(role: str) -> str:
    # we look for prompts from:
    #  ~/.eigengen/{role}.txt
    # if the file is not found, we use the default prompt
    try:
        with open(os.path.expanduser(f"~/.eigengen/{role}.txt")) as f:
            return f.read()
    except FileNotFoundError:
        # No prompt file found; use the default prompt
        return PROMPTS[role]
    except Exception as e:
        logger.error("Error reading prompt file for role '%s': %s", role, e)
        return PROMPTS[role]


PROMPTS = {
    "general": """
""",
    "programmer": """
Follow the coding style of any existing source code and make changes accordingly. Pay
attention to best practices. Strive for elegance in your code.

Write your response as a series of edits in <egg_edit></egg_edit> tags like below:

<egg_edit filename="dirpath/filename.py">
Clear description of the additions and changes and instructions where in the file to make them.

```python
# Source code changes here
```
</egg_edit>
""",
    "meld": """
You are given original content of the file in <egg_file filename="dirpath/filename"></egg_file>
tags and a set of changes in <egg_edit></egg_edit> tags.

You must provide a merged version of the file that incorporates the proposed changes.
Do not change anything in the suggested changes. You must respond with the full
file contents without any encoding or additional markup.
Your response format should be as follows:
```plaintext
# Original file content here
```
"""
}
