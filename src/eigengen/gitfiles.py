import os
import subprocess
import fnmatch

def find_git_root():
    """
    Traverse up the directory tree to find the root of the Git repository.

    Returns:
        str or None: The path to the Git root directory, or None if not found.
    """
    current_dir = os.getcwd()
    while current_dir != os.path.dirname(current_dir):  # Stop at the filesystem root
        if os.path.exists(os.path.join(current_dir, '.git')):
            return current_dir
        current_dir = os.path.dirname(current_dir)
    return None

def find_eigengen_ignore():
    """
    Locate the .eigengen_ignore file in the Git root directory.

    Returns:
        str or None: The path to the ignore file, or None if not found.
    """
    git_root = find_git_root()
    if git_root:
        ignore_file = os.path.join(git_root, '.eigengen_ignore')
        if os.path.exists(ignore_file):
            return ignore_file
    return None

def read_ignore_patterns(ignore_file):
    """
    Read ignore patterns from the .eigengen_ignore file.

    Args:
        ignore_file (str): The path to the ignore file.

    Returns:
        list: A list of ignore patterns.
    """
    if not ignore_file:
        return []
    with open(ignore_file, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

def get_git_files():
    """
    Retrieve all tracked files in the Git repository.

    Returns:
        list: A list of tracked file paths.
    """
    return run_git_command(['git', 'ls-files'])

def get_locally_modified_git_files():
    """
    Get a list of locally modified files, both staged and unstaged.

    Returns:
        list: A filtered list of modified files not matching ignore patterns.
    """
    staged = run_git_command(['git', 'diff', '--cached', '--name-only'])
    unstaged = run_git_command(['git', 'diff', '--name-only'])
    modified_files = set(staged + unstaged)
    return get_filtered_files(list(modified_files))

def run_git_command(command):
    """
    Execute a Git command and capture its output.

    Args:
        command (list): The Git command to run as a list of arguments.

    Returns:
        list: The stdout output of the command split into lines.

    Raises:
        RuntimeError: If the Git command fails or Git is not installed.
    """
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.splitlines()
    except subprocess.CalledProcessError:
        raise RuntimeError(f"Failed to run {' '.join(command)}. Make sure you're in a git repository.")
    except FileNotFoundError:
        raise RuntimeError("Git is not installed or not in the system PATH.")

def filter_files(files, ignore_patterns):
    """
    Filter out files that match any of the ignore patterns.

    Args:
        files (list): The list of file paths to filter.
        ignore_patterns (list): The list of patterns to ignore.

    Returns:
        list: The filtered list of file paths.
    """
    if not ignore_patterns:
        return files
    return [f for f in files if not any(fnmatch.fnmatch(f, pattern) for pattern in ignore_patterns)]

def get_filtered_git_files():
    """
    Get all tracked Git files, excluding those matching ignore patterns.

    Returns:
        list: A filtered list of tracked file paths.
    """
    git_files = get_git_files()
    return get_filtered_files(git_files)

def get_filtered_files(files):
    """
    Filter files based on .eigengen_ignore patterns.

    Args:
        files (list): The list of file paths to filter.

    Returns:
        list: The filtered list of file paths.
    """
    ignore_file = find_eigengen_ignore()
    ignore_patterns = read_ignore_patterns(ignore_file)
    filtered_list = filter_files(files, ignore_patterns)
    return filtered_list

def make_relative_to_git_root(file_path):
    """
    Make a file path relative to the Git root directory.

    Args:
        file_path (str): The original file path.

    Returns:
        str: The file path relative to the Git root, or the original path if root not found.
    """
    git_root = find_git_root()
    if git_root:
        return os.path.relpath(file_path, git_root)
    return file_path
