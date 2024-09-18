import os
import hashlib
import time
from typing import List, Dict

from eigengen import operations, providers, prompts

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

def index_file(model: str, filepath: str) -> None:
    with open(filepath, 'r') as f:
        content = f.read()

    messages = [
        {"role": "user", "content": f"<eigengen_file name=\"{filepath}\">\n{content}\n</eigengen_file>"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "Index the given file according to your instructions"}
    ]

    summary, _ = operations.process_request(model, messages, "indexing")

    cache_path = get_cache_path(filepath)
    with open(cache_path, 'w') as f:
        f.write(summary)

def index_files(model: str, filepaths: List[str]) -> None:
    ensure_cache_dir()
    for filepath in filepaths:
        if should_index_file(filepath):
            index_file(model, filepath)

def get_file_summary(filepath: str) -> str:
    cache_path = get_cache_path(filepath)
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            return f.read()
    return ""

def get_summaries(filepaths: List[str]) -> Dict[str, str]:
    return {filepath: get_file_summary(filepath) for filepath in filepaths}
