import os
import subprocess
import fnmatch

def find_git_root():
    current_dir = os.getcwd()
    while current_dir != os.path.dirname(current_dir):  # Stop at root directory
        if os.path.exists(os.path.join(current_dir, '.git')):
            return current_dir
        current_dir = os.path.dirname(current_dir)
    return None

def find_eigengen_ignore():
    git_root = find_git_root()
    if git_root:
        ignore_file = os.path.join(git_root, '.eigengen_ignore')
        if os.path.exists(ignore_file):
            return ignore_file
    return None

def read_ignore_patterns(ignore_file):
    if not ignore_file:
        return []
    with open(ignore_file, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

def get_git_files():
    return run_git_command(['git', 'ls-files'])

def get_locally_modified_git_files():
    staged = run_git_command(['git', 'diff', '--cached', '--name-only'])
    unstaged = run_git_command(['git', 'diff', '--name-only'])
    modified_files = set(staged + unstaged)
    return get_filtered_files(list(modified_files))

def run_git_command(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.splitlines()
    except subprocess.CalledProcessError:
        raise RuntimeError(f"Failed to run {' '.join(command)}. Make sure you're in a git repository.")
    except FileNotFoundError:
        raise RuntimeError("Git is not installed or not in the system PATH.")

def filter_files(files, ignore_patterns):
    if not ignore_patterns:
        return files
    return [f for f in files if not any(fnmatch.fnmatch(f, pattern) for pattern in ignore_patterns)]

def get_filtered_git_files():
    git_files = get_git_files()
    return get_filtered_files(git_files)

def get_filtered_files(files):
    ignore_file = find_eigengen_ignore()
    ignore_patterns = read_ignore_patterns(ignore_file)
    filtered_list = filter_files(files, ignore_patterns)
    return filtered_list

def make_relative_to_git_root(file_path):
    git_root = find_git_root()
    if git_root:
        return os.path.relpath(file_path, git_root)
    return file_path

