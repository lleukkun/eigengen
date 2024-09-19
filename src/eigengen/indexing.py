import os
import hashlib
import re
import json
from typing import List, Dict, Tuple, Set

CACHE_DIR = ".eigengen_cache"

def md5sum(filepath: str) -> str:
    return hashlib.md5(filepath.encode()).hexdigest()

def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(filepath: str) -> str:
    return os.path.join(CACHE_DIR, md5sum(filepath))

def should_index_file(filepath: str) -> bool:
    cache_path = get_cache_path(filepath)
    if not os.path.exists(cache_path):
        return True
    return os.path.getmtime(filepath) > os.path.getmtime(cache_path)

def get_file_language(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    language_map = {
        '.c': 'c', '.h': 'c',
        '.cpp': 'cpp', '.hpp': 'cpp', '.cc': 'cpp', '.hh': 'cpp',
        '.py': 'python',
        '.rs': 'rust',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.java': 'java',
        '.zig': 'zig',
        '.pl': 'perl',
        '.php': 'php',
        '.vb': 'visualbasic',
        '.go': 'go',
        '.sql': 'sql',
        '.f': 'fortran', '.f90': 'fortran', '.f95': 'fortran',
        '.m': 'matlab',
        '.r': 'r',
        '.rb': 'ruby',
        '.kt': 'kotlin',
        '.swift': 'swift'
    }
    return language_map.get(ext, 'unknown')

def parse_file(filepath: str) -> Dict[str, List[str]]:
    with open(filepath, 'r') as f:
        content = f.read()

    language = get_file_language(filepath)
    patterns = get_language_patterns(language)

    result = {
        'classes': [],
        'methods': [],
        'macros': [],
        'templates': [],
        'structs': [],
        'functions': []
    }

    for category, pattern in patterns.items():
        matches = re.findall(pattern, content, re.MULTILINE)
        result[category] = list(set(matches))  # Remove duplicates

    return result

def get_language_patterns(language: str) -> Dict[str, str]:
    patterns = {
        'c': {
            'methods': r'^\s*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*\{',
            'macros': r'^\s*#define\s+(\w+)',
            'structs': r'^\s*struct\s+(\w+)\s*\{',
        },
        'cpp': {
            'classes': r'^\s*class\s+(\w+)',
            'methods': r'^\s*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*(?:const)?\s*(?:override)?\s*\{',
            'macros': r'^\s*#define\s+(\w+)',
            'templates': r'^\s*template\s*<[^>]*>\s*(?:class|struct|typename)\s+(\w+)',
            'structs': r'^\s*struct\s+(\w+)\s*\{',
        },
        'python': {
            'classes': r'^\s*class\s+(\w+)',
            'methods': r'^\s*def\s+(\w+)\s*\(',
        },
        'rust': {
            'methods': r'^\s*(?:pub\s+)?fn\s+(\w+)',
            'macros': r'^\s*macro_rules!\s+(\w+)',
            'structs': r'^\s*(?:pub\s+)?struct\s+(\w+)',
        },
        'javascript': {
            'classes': r'^\s*class\s+(\w+)',
            'methods': r'^\s*(?:async\s+)?(?:function\s+(\w+)|(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>)',
        },
        'typescript': {
            'classes': r'^\s*(?:export\s+)?class\s+(\w+)',
            'methods': r'^\s*(?:public|private|protected)?\s*(?:async\s+)?(?:(\w+)\s*\([^)]*\)|(\w+)\s*:\s*(?:async\s+)?\([^)]*\)\s*=>)',
            'templates': r'^\s*interface\s+(\w+)<[^>]*>',
        },
        'java': {
            'classes': r'^\s*(?:public|private|protected)?\s*(?:abstract)?\s*class\s+(\w+)',
            'methods': r'^\s*(?:public|private|protected)?\s*(?:static)?\s*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*(?:throws\s+\w+(?:,\s*\w+)*)?\s*\{',
            'templates': r'^\s*(?:public|private|protected)?\s*interface\s+(\w+)<[^>]*>',
        },
        'zig': {
            'functions': r'^\s*(?:pub\s+)?fn\s+(\w+)',
            'structs': r'^\s*(?:pub\s+)?struct\s+(\w+)',
        },
        'perl': {
            'functions': r'^\s*sub\s+(\w+)',
        },
        'php': {
            'classes': r'^\s*class\s+(\w+)',
            'methods': r'^\s*(?:public|private|protected)?\s*function\s+(\w+)',
        },
        'visualbasic': {
            'classes': r'^\s*(?:Public\s+|Private\s+)?Class\s+(\w+)',
            'methods': r'^\s*(?:Public\s+|Private\s+)?(?:Function|Sub)\s+(\w+)',
        },
        'go': {
            'functions': r'^\s*func\s+(\w+)',
            'structs': r'^\s*type\s+(\w+)\s+struct',
        },
        'sql': {
            'functions': r'^\s*CREATE\s+FUNCTION\s+(\w+)',
            'procedures': r'^\s*CREATE\s+PROCEDURE\s+(\w+)',
        },
        'fortran': {
            'functions': r'^\s*(?:RECURSIVE\s+)?FUNCTION\s+(\w+)',
            'subroutines': r'^\s*(?:RECURSIVE\s+)?SUBROUTINE\s+(\w+)',
        },
        'matlab': {
            'functions': r'^\s*function\s+(?:\[?[^\]]*\]?\s*=\s*)?(\w+)',
        },
        'r': {
            'functions': r'^\s*(\w+)\s*<-\s*function',
        },
        'ruby': {
            'classes': r'^\s*class\s+(\w+)',
            'methods': r'^\s*def\s+(\w+)',
        },
        'kotlin': {
            'classes': r'^\s*(?:abstract\s+)?class\s+(\w+)',
            'functions': r'^\s*fun\s+(\w+)',
        },
        'swift': {
            'classes': r'^\s*(?:public\s+|private\s+|fileprivate\s+|internal\s+)?class\s+(\w+)',
            'functions': r'^\s*(?:public\s+|private\s+|fileprivate\s+|internal\s+)?func\s+(\w+)',
            'structs': r'^\s*(?:public\s+|private\s+|fileprivate\s+|internal\s+)?struct\s+(\w+)',
        },
    }
    return patterns.get(language, {})

def index_files(filepaths: List[str]) -> None:
    ensure_cache_dir()

    # First pass: Parse and store what each file provides
    file_provides: Dict[str, Set[str]] = {}
    for filepath in filepaths:
        if should_index_file(filepath):
            parsed_data = parse_file(filepath)
            file_provides[filepath] = set()
            for category, items in parsed_data.items():
                file_provides[filepath].update(items)

    # Second pass: Determine references
    for filepath in filepaths:
        if should_index_file(filepath):
            references = set()
            with open(filepath, 'r') as f:
                content = f.read()

            for other_file, symbols in file_provides.items():
                if other_file != filepath:
                    for symbol in symbols:
                        if symbol in content:
                            references.add(other_file)
                            break

            cache_data = {
                "filename": filepath,
                "provides": list(file_provides[filepath]),
                "references": list(references)
            }

            cache_path = get_cache_path(filepath)
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)

def get_file_summary(filepath: str) -> Dict:
    cache_path = get_cache_path(filepath)
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            return json.load(f)
    return {}

def get_summaries(filepaths: List[str]) -> Dict[str, Dict]:
    return {filepath: get_file_summary(filepath) for filepath in filepaths}
