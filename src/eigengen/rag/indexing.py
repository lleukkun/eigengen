import os
import re


def get_file_language(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    language_map = {
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cc": "cpp",
        ".hh": "cpp",
        ".py": "python",
        ".rs": "rust",
        ".js": "javascript",
        ".ts": "typescript",
        ".java": "java",
        ".zig": "zig",
        ".pl": "perl",
        ".php": "php",
        ".vb": "visualbasic",
        ".go": "go",
        ".sql": "sql",
        ".f": "fortran",
        ".f90": "fortran",
        ".f95": "fortran",
        ".m": "matlab",
        ".r": "r",
        ".rb": "ruby",
        ".kt": "kotlin",
        ".swift": "swift",
    }
    return language_map.get(ext, "unknown")


def parse_file(filepath: str) -> dict[str, list[str]]:
    with open(filepath, "r", errors="ignore") as f:
        content = f.read()

    language = get_file_language(filepath)
    patterns = get_language_patterns(language)

    result = {"classes": [], "methods": [], "macros": [], "templates": [], "structs": [], "functions": []}

    for category, pattern in patterns.items():
        matches = re.findall(pattern, content, re.MULTILINE)
        # Flatten tuples if any
        flat_matches = []
        for match in matches:
            if isinstance(match, tuple):
                flat_matches.extend([m for m in match if m])
            else:
                flat_matches.append(match)
        result[category] = list(set(flat_matches))  # Remove duplicates

    return result


def get_language_patterns(language: str) -> dict[str, str]:
    patterns = {
        "c": {
            "methods": r"^\s*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*\{",
            "macros": r"^\s*#define\s+(\w+)",
            "structs": r"^\s*struct\s+(\w+)\s*\{",
        },
        "cpp": {
            "classes": r"^\s*class\s+(\w+)",
            "methods": r"^\s*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*(?:const)?\s*(?:override)?\s*\{",
            "macros": r"^\s*#define\s+(\w+)",
            "templates": r"^\s*template\s*<[^>]*>\s*(?:class|struct|typename)\s+(\w+)",
            "structs": r"^\s*struct\s+(\w+)\s*\{",
        },
        "python": {
            "classes": r"^\s*class\s+(\w+)",
            "methods": r"^\s*def\s+(\w+)\s*\(",
        },
        "rust": {
            "methods": r"^\s*(?:pub\s+)?fn\s+(\w+)",
            "macros": r"^\s*macro_rules!\s+(\w+)",
            "structs": r"^\s*(?:pub\s+)?struct\s+(\w+)",
        },
        "javascript": {
            "classes": r"^\s*class\s+(\w+)",
            "methods": r"^\s*(?:async\s+)?(?:function\s+(\w+)|(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>)",
        },
        "typescript": {
            "classes": r"^\s*(?:export\s+)?class\s+(\w+)",
            "methods": r"^\s*(?:public|private|protected)?\s*(?:async\s+)?(?:(\w+)\s*\([^)]*\)|(\w+)\s*:\s*(?:async\s+)?\([^)]*\)\s*=>)",  # noqa: E501
            "templates": r"^\s*interface\s+(\w+)<[^>]*>",
        },
        "java": {
            "classes": r"^\s*(?:public|private|protected)?\s*(?:abstract)?\s*class\s+(\w+)",
            "methods": r"^\s*(?:public|private|protected)?\s*(?:static)?\s*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*(?:throws\s+\w+(?:,\s*\w+)*)?\s*\{",  # noqa: E501
            "templates": r"^\s*(?:public|private|protected)?\s*interface\s+(\w+)<[^>]*>",
        },
        "zig": {
            "functions": r"^\s*(?:pub\s+)?fn\s+(\w+)",
            "structs": r"^\s*(?:pub\s+)?struct\s+(\w+)",
        },
        "perl": {
            "functions": r"^\s*sub\s+(\w+)",
        },
        "php": {
            "classes": r"^\s*class\s+(\w+)",
            "methods": r"^\s*(?:public|private|protected)?\s*function\s+(\w+)",
        },
        "visualbasic": {
            "classes": r"^\s*(?:Public\s+|Private\s+)?Class\s+(\w+)",
            "methods": r"^\s*(?:Public\s+|Private\s+)?(?:Function|Sub)\s+(\w+)",
        },
        "go": {
            "functions": r"^\s*func\s+(\w+)",
            "structs": r"^\s*type\s+(\w+)\s+struct",
        },
        "sql": {
            "functions": r"^\s*CREATE\s+FUNCTION\s+(\w+)",
            "procedures": r"^\s*CREATE\s+PROCEDURE\s+(\w+)",
        },
        "fortran": {
            "functions": r"^\s*(?:RECURSIVE\s+)?FUNCTION\s+(\w+)",
            "subroutines": r"^\s*(?:RECURSIVE\s+)?SUBROUTINE\s+(\w+)",
        },
        "matlab": {
            "functions": r"^\s*function\s+(?:\[?[^\]]*\]?\s*=\s*)?(\w+)",
        },
        "r": {
            "functions": r"^\s*(\w+)\s*<-\s*function",
        },
        "ruby": {
            "classes": r"^\s*class\s+(\w+)",
            "methods": r"^\s*def\s+(\w+)",
        },
        "kotlin": {
            "classes": r"^\s*(?:abstract\s+)?class\s+(\w+)",
            "functions": r"^\s*fun\s+(\w+)",
        },
        "swift": {
            "classes": r"^\s*(?:public\s+|private\s+|fileprivate\s+|internal\s+)?class\s+(\w+)",
            "functions": r"^\s*(?:public\s+|private\s+|fileprivate\s+|internal\s+)?func\s+(\w+)",
            "structs": r"^\s*(?:public\s+|private\s+|fileprivate\s+|internal\s+)?struct\s+(\w+)",
        },
    }
    return patterns.get(language, {})


def tokenize_symbol_names(content: str) -> list[str]:
    matches = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", content, re.MULTILINE)
    return matches
