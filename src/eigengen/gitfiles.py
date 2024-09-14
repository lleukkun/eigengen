import os
import subprocess
import fnmatch

def find_eigengen_ignore():
    current_dir = os.getcwd()
    while current_dir != os.path.dirname(current_dir):  # Stop at root directory
        ignore_file = os.path.join(current_dir, '.eigengen_ignore')
        if os.path.exists(ignore_file):
            return ignore_file
        current_dir = os.path.dirname(current_dir)
    return None

def read_ignore_patterns(ignore_file):
    if not ignore_file:
        return []
    with open(ignore_file, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

def get_git_files():
    try:
        result = subprocess.run(['git', 'ls-files'], capture_output=True, text=True, check=True)
        return result.stdout.splitlines()
    except subprocess.CalledProcessError:
        raise RuntimeError("Failed to run 'git ls-files'. Make sure you're in a git repository.")
    except FileNotFoundError:
        raise RuntimeError("Git is not installed or not in the system PATH.")

def filter_files(files, ignore_patterns):
    if not ignore_patterns:
        return files
    return [f for f in files if not any(fnmatch.fnmatch(f, pattern) for pattern in ignore_patterns)]

def get_filtered_git_files():
    ignore_file = find_eigengen_ignore()
    ignore_patterns = read_ignore_patterns(ignore_file)
    git_files = get_git_files()
    return filter_files(git_files, ignore_patterns)
