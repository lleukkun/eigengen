from typing import Any, Dict, List, Optional, Tuple, Union
import requests
import json
import argparse
import os
import sys
import time
import random
import difflib
import colorama
import tempfile
import re
import subprocess

from anthropic import Anthropic
from groq import Groq
from openai import OpenAI
import google.generativeai as google_genai

from eigengen.prompts import PROMPTS, wrap_file
from eigengen.providers import create_provider, Provider

def extract_filename(tag: str) -> Optional[str]:
    pattern = r'<eigengen_file\s+name="([^"]*)">'
    match = re.search(pattern, tag)
    if match:
        return match.group(1)
    return None

def extract_file_content(output: str) -> Dict[str, str]:
    files: Dict[str, str] = {}
    file_content: List[str] = []
    file_started: bool = False
    file_name: Optional[str] = None
    for line in output.splitlines():
        if not file_started and line.strip().startswith("<eigengen_file name="):
            file_started = True
            file_name = extract_filename(line.strip())
        elif file_started:
            if line == "</eigengen_file>":
                # file is complete
                if file_name is not None:
                    files[file_name] = "\n".join(file_content) + "\n"
                file_content = []
                file_started = False
                file_name = None
            else:
                # Strip trailing whitespace from each line
                file_content.append(line.rstrip())
    return files

def generate_diff(original_content: str, new_content: str, file_name: str, use_color: bool = True) -> str:
    original_lines = original_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(original_lines, new_lines, fromfile=f"a/{file_name}", tofile=f"b/{file_name}")

    if not use_color:
        return ''.join(diff)

    colored_diff: List[str] = []
    for line in diff:
        if line.startswith('---') or line.startswith('+++'):
            colored_diff.append(colorama.Fore.CYAN + line + colorama.Fore.RESET)
        elif line.startswith('@@'):
            colored_diff.append(colorama.Fore.CYAN + line + colorama.Fore.RESET)
        elif line.startswith('-'):
            colored_diff.append(colorama.Fore.RED + line + colorama.Fore.RESET)
        elif line.startswith('+'):
            colored_diff.append(colorama.Fore.GREEN + line + colorama.Fore.RESET)
        else:
            colored_diff.append(line)

    return ''.join(colored_diff)

def is_output_to_terminal() -> bool:
    return sys.stdout.isatty()

def apply_patch(diff: str) -> None:
    with tempfile.NamedTemporaryFile(delete=False, mode='w') as temp_diff_file:
        temp_diff_file.write(diff)
        temp_diff_file_path = temp_diff_file.name

    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, temp_diff_file_path], check=True)

    apply = input("Do you want to apply the changes? (Y/n): ").strip().lower()
    if apply == 'y' or apply == '':
        try:
            subprocess.run(['patch', '-p1', '-i', temp_diff_file_path], check=True)
            print("Changes applied successfully.")
        except subprocess.CalledProcessError:
            print("Failed to apply changes. Please check the patch file and try again.")
    else:
        print("Changes not applied.")

    os.remove(temp_diff_file_path)

def process_request(provider: str, model: str, files: Optional[List[str]], prompt: str, diff_mode: bool) -> Tuple[str, Dict[str, str]]:
    client: Optional[Union[Anthropic, Groq, OpenAI]] = None
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        client = Anthropic(api_key=api_key)
    elif provider == "groq":
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set")
        client = Groq(api_key=api_key)
    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        client = OpenAI(api_key=api_key)
    elif provider == "google":
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        google_genai.configure(api_key=api_key)

    provider_instance: Provider = create_provider(provider, model, client)

    system: str = PROMPTS["system"]
    system += PROMPTS["diff"] if diff_mode else PROMPTS["non_diff"]

    messages: List[Dict[str, str]] = []
    original_files: Dict[str, str] = {}

    if files is not None:
        for fname in files:
            try:
                original_content: str = ""
                if fname == "-":
                    original_content = sys.stdin.read()
                    original_files["-"] = original_content
                else:
                    with open(fname, "r") as f:
                        original_content = f.read()
                        original_files[fname] = original_content

                messages += [{"role": "user", "content": wrap_file(fname, original_content)},
                             {"role": "assistant", "content": "ok"}]
            except Exception as e:
                raise IOError(f"Error reading from file: {fname}") from e

    messages += [{"role": "user", "content": prompt}]

    final_answer: str = provider_instance.make_request(system, messages)
    new_files: Dict[str, str] = extract_file_content(final_answer) if diff_mode else {}

    return final_answer, new_files

def main() -> None:
    parser = argparse.ArgumentParser("eigengen")
    parser.add_argument("--model", "-m", choices=["claude-sonnet",
                                                  "claude-haiku",
                                                  "llama3.1",
                                                  "codestral",
                                                  "mistral-nemo",
                                                  "phi3.5",
                                                  "gemma2",
                                                  "groq",
                                                  "gpt4",
                                                  "o1-preview",
                                                  "o1-mini"],
                        default="claude-sonnet", help="Choose Model")
    parser.add_argument("--files", "-f", nargs="+", help="List of files to attach to the request (e.g., -f file1.txt file2.txt)")
    parser.add_argument("--prompt", "-p", help="Prompt string to use")
    parser.add_argument("--diff", "-d", action="store_true", help="Enable diff output mode")
    parser.add_argument("--interactive", "-i", action="store_true", help="Enable interactive mode")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto",
                        help="Control color output: 'auto' (default), 'always', or 'never'")
    parser.add_argument("--debug", action="store_true", help="enable debug output")
    args = parser.parse_args()
    # Initialize colorama for cross-platform color support
    colorama.init()

    model_map: Dict[str, str] = {
        "claude-sonnet": "anthropic;claude-3-5-sonnet-20240620",
        "claude-haiku": "anthropic;claude-3-haiku-20240307",
        "llama3.1": "ollama;llama3.1:latest",
        "codestral": "ollama;codestral:latest",
        "mistral-nemo": "ollama;mistral-nemo:latest",
        "phi3.5": "ollama;phi3.5:latest",
        "gemma2": "ollama;gemma2:27b",
        "groq": "groq;llama-3.1-70b-versatile",
        "gpt4": "openai;gpt-4o-2024-08-06",
        "o1-preview": "openai;o1-preview",
        "o1-mini": "openai;o1-mini"
    }
    model: str = model_map.get(args.model, "ollama;llama3.1:latest")

    provider, model = model.split(";")

    try:
        final_answer, new_files = process_request(provider, model, args.files, args.prompt, args.diff)

        if args.debug:
            print(final_answer)

        if not args.diff:
            print(final_answer)
        else:
            diff: str = ""
            if args.files and new_files:
                use_color: bool = False
                if not args.interactive:
                    use_color = (args.color == "always") or (args.color == "auto" and is_output_to_terminal())
                for fname in new_files.keys():
                    original_content: str = ""
                    if fname in args.files:
                        with open(fname, "r") as f:
                            original_content = f.read()
                    diff += generate_diff(original_content, new_files[fname], fname, use_color)
                print(diff)
                if args.interactive:
                    apply_patch(diff)
            else:
                print("Error: Unable to generate diff. Make sure both original and new file contents are available.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()

