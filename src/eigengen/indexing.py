import os
import shutil
import hashlib
import re
import msgpack
import gc
from typing import List, Dict, Set, Optional
from collections import defaultdict

CACHE_DIR = ".eigengen_cache"

def md5sum(filepath: str) -> str:
    return hashlib.md5(filepath.encode()).hexdigest()

def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(filepath: str) -> str:
    md5 = md5sum(filepath)
    dir_part = md5[:2]
    return os.path.join(CACHE_DIR, dir_part, md5)

def should_index_file(filepath: str) -> bool:
    cache_path = get_cache_path(filepath)
    if not os.path.exists(cache_path):
        return True
    return os.path.getmtime(filepath) > os.path.getmtime(cache_path)

def is_regular_known_file(filepath: str) -> bool:
    if get_file_language(filepath) == 'unknown':
        return False
    if not os.path.exists(filepath):
        return False

    if not os.path.isfile(filepath):
        return False

    return True

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
    with open(filepath, 'r', errors='ignore') as f:
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
        # Flatten tuples if any
        flat_matches = []
        for match in matches:
            if isinstance(match, tuple):
                flat_matches.extend([m for m in match if m])
            else:
                flat_matches.append(match)
        result[category] = list(set(flat_matches))  # Remove duplicates

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

def tokenize_symbol_names(content: str) -> List[str]:
    matches = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', content, re.MULTILINE)
    return matches

class EggCacheEntry:
    def __init__(self, real_path: str = '', provides: Dict[str, int] = None, uses: Dict[str, int] = None, total_usecount: int = 0, total_refcount: int = 0):
        self.real_path = real_path
        self.provides = provides if provides is not None else defaultdict(int)
        self.uses = uses if uses is not None else defaultdict(int)
        self.total_usecount = total_usecount
        self.total_refcount = total_refcount

    def to_dict(self) -> Dict:
        return {
            'real_path': self.real_path,
            'provides': self.provides,
            'uses': self.uses,
            'total_usecount': self.total_usecount,
            'total_refcount': self.total_refcount
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            real_path=data.get('real_path', ''),
            provides=data.get('provides', {}),
            uses=data.get('uses', {}),
            total_usecount=data.get('total_usecount', 0),
            total_refcount=data.get('total_refcount', 0)
        )

class EggCache:
    def __init__(self):
        self.entries: Dict[str, EggCacheEntry] = {}
        self.all_symbols_filepath: Dict[str, str] = {}
        self.all_symbols_refcounts: Dict[str, int] = defaultdict(int)

def read_cache_state() -> EggCache:
    cache = EggCache()
    gc.disable()
    for _, _, filenames, dir_fd in os.fwalk(CACHE_DIR):
        for filename in filenames:
            fd = os.open(filename, os.O_RDONLY, mode=0o644, dir_fd=dir_fd)
            with os.fdopen(fd, 'rb') as f:
                obj = msgpack.unpack(f)
                entry = EggCacheEntry.from_dict(obj)
                cache.entries[entry.real_path] = entry
                for key in entry.provides:
                    cache.all_symbols_filepath[key] = entry.real_path
                for key, value in entry.uses.items():
                    if key in cache.all_symbols_refcounts:
                        cache.all_symbols_refcounts[key] += value

    gc.enable()
    return cache

def write_cache_state(state: EggCache, updated_filepaths: Optional[Set[str]] = None, clear_cache: bool = False) -> None:
    if clear_cache:
        # Remove existing cache files
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
        ensure_cache_dir()

    if updated_filepaths is None:
        # Write all entries
        entries_to_write = state.entries.values()
    else:
        # Write only entries for updated_filepaths
        entries_to_write = [state.entries[filepath] for filepath in updated_filepaths if filepath in state.entries]

    for entry in entries_to_write:
        buf = msgpack.packb(entry.to_dict())
        cache_path = get_cache_path(entry.real_path)
        dir_path = os.path.dirname(cache_path)
        os.makedirs(dir_path, exist_ok=True)
        with open(cache_path, "wb") as f:
            f.write(buf)

def index_files(filepaths: List[str]) -> None:
    ensure_cache_dir()

    # Check if cache exists and is not empty
    cache_exists = os.path.exists(CACHE_DIR) and any(os.scandir(CACHE_DIR))

    # Identify files that need reindexing
    requires_indexing = [
        path for path in filepaths
        if is_regular_known_file(path) and should_index_file(path)
    ]

    # Decide whether to perform a full reindex
    full_reindex = False
    if not cache_exists:
        full_reindex = True
    elif len(requires_indexing) > 100:
        full_reindex = True

    if full_reindex:
        print("Performing full reindex...")
        # Start with an empty cache
        new_state = EggCache()
        entries = {}

        # First pass: Collect all provided symbols
        files_to_index = [
            path for path in filepaths
            if is_regular_known_file(path)
        ]

        for filepath in files_to_index:
            # Parse the file
            parsed_data = parse_file(filepath)
            entry = EggCacheEntry(
                real_path=filepath,
                provides=defaultdict(int),
                uses=defaultdict(int),
                total_usecount=0,
                total_refcount=0
            )

            # Update provided symbols
            for category, items in parsed_data.items():
                for item in items:
                    entry.provides[item] = 0

            entries[filepath] = entry

        # Build all_symbols_filepath from all entries
        for filepath, entry in entries.items():
            for symbol in entry.provides:
                new_state.all_symbols_filepath[symbol] = filepath

        # Second pass: Update uses based on provided symbols
        for filepath, entry in entries.items():
            with open(filepath, 'r', errors='ignore') as f:
                content = f.read()
                tokens = tokenize_symbol_names(content)
                for token in tokens:
                    if token in entry.provides:
                        continue  # Skip own provided symbols
                    if token not in new_state.all_symbols_filepath:
                        continue  # Skip symbols not provided by local files
                    entry.total_usecount += 1
                    entry.uses[token] += 1
                    new_state.all_symbols_refcounts[token] += 1

        new_state.entries = entries

        # Compute total_refcount for providers
        for entry in new_state.entries.values():
            entry.total_refcount = sum(
                new_state.all_symbols_refcounts.get(sym, 0)
                for sym in entry.provides
            )

        # Write the new cache state and clear existing cache files
        write_cache_state(new_state, clear_cache=True)
    else:
        if not requires_indexing:
            print("No files require reindexing.")
            return

        print("Performing incremental update...")
        # Incremental update mode
        old_state = read_cache_state()

        changed_files = set(requires_indexing)
        provides_changed = set()

        # First, process 'provides' for files in 'requires_indexing'
        for filepath in requires_indexing:
            if not is_regular_known_file(filepath):
                continue

            # Load old entry if it exists
            old_entry = old_state.entries.get(filepath, EggCacheEntry(real_path=filepath))

            # Parse the new file content
            parsed_data = parse_file(filepath)
            new_entry = EggCacheEntry(
                real_path=filepath,
                provides=defaultdict(int),
                uses=defaultdict(int),
                total_usecount=0,
                total_refcount=0
            )

            # Update provided symbols
            new_entry.provides = {symbol: 0 for symbols in parsed_data.values() for symbol in symbols}

            # Compute deltas for provides
            provides_added = set(new_entry.provides) - set(old_entry.provides)
            provides_removed = set(old_entry.provides) - set(new_entry.provides)
            provides_changed.update(provides_added)
            provides_changed.update(provides_removed)

            # Update all_symbols_filepath (providers)
            for symbol in provides_added:
                old_state.all_symbols_filepath[symbol] = filepath
            for symbol in provides_removed:
                if old_state.all_symbols_filepath.get(symbol) == filepath:
                    del old_state.all_symbols_filepath[symbol]

            # Temporarily store the new_entry
            old_state.entries[filepath] = new_entry

        # Now, find files that 'use' symbols whose 'provides' status changed
        for filepath, entry in old_state.entries.items():
            if filepath in changed_files:
                continue
            if any(symbol in provides_changed for symbol in entry.uses):
                changed_files.add(filepath)

        # Reindex 'provides' and 'uses' for 'changed_files'
        for filepath in changed_files:
            if not is_regular_known_file(filepath):
                continue

            # Parse the file
            parsed_data = parse_file(filepath)
            entry = old_state.entries.get(filepath, EggCacheEntry(real_path=filepath))
            entry.provides = {symbol: 0 for symbols in parsed_data.values() for symbol in symbols}

            # Update all_symbols_filepath
            for symbol in entry.provides:
                old_state.all_symbols_filepath[symbol] = filepath

        # Rebuild all_symbols_refcounts and update uses
        old_state.all_symbols_refcounts = {}
        for filepath, entry in old_state.entries.items():
            # Reparse uses only if file is in 'changed_files'
            if filepath not in changed_files:
                continue

            # Reset uses and total_usecount
            entry.uses = {}
            entry.total_usecount = 0

            with open(filepath, 'r', errors='ignore') as f:
                content = f.read()
                tokens = tokenize_symbol_names(content)
                for token in tokens:
                    if token in entry.provides:
                        continue  # Skip own provided symbols
                    if token not in old_state.all_symbols_filepath:
                        continue  # Skip symbols not provided by local files
                    entry.total_usecount += 1
                    entry.uses[token] += 1

        # Rebuild all_symbols_refcounts from 'uses' of all entries
        old_state.all_symbols_refcounts = {}
        for entry in old_state.entries.values():
            for symbol, count in entry.uses.items():
                old_state.all_symbols_refcounts[symbol] = old_state.all_symbols_refcounts.get(symbol, 0) + count

        # Compute total_refcount for providers
        for entry in old_state.entries.values():
            entry.total_refcount = sum(
                old_state.all_symbols_refcounts.get(sym, 0)
                for sym in entry.provides
            )

        # Write only the updated entries to the cache
        write_cache_state(old_state, updated_filepaths=changed_files)

def get_file_summary(filepath: str) -> Dict:
    cache_path = get_cache_path(filepath)
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return msgpack.unpack(f)
    return {}

def get_summaries(filepaths: List[str]) -> Dict[str, Dict]:
    return {filepath: get_file_summary(filepath) for filepath in filepaths}

def get_default_context(filepaths: List[str], top_n: int = 3) -> List[str]:
    summaries = get_summaries(filepaths)
    sorted_files = sorted(summaries.items(), key=lambda x: x[1].get('total_usecount', 0) * x[1].get('total_refcount', 0), reverse=True)
    output = [filepath for filepath, _ in sorted_files[:top_n]]
    return output
