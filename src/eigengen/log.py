from typing import List, Dict
from datetime import datetime
import os
import json


def log_request_response(model: str, messages: List[Dict[str, str]], mode: str, final_answer: str, new_files: Dict[str, str]) -> None:
    log_dir = os.path.expanduser("~/.eigengen")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "log.jsonl")

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "current_dir": os.getcwd(),
        "request": {
            "model": model,
            "messages": messages,
            "mode": mode
        },
        "response": {
            "final_answer": final_answer,
            "new_files": new_files
        }
    }

    try:
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Warning: Failed to log request/response: {str(e)}", file=sys.stderr)

def log_prompt(prompt: str) -> None:
    log_dir = os.path.expanduser("~/.eigengen")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "prompt_history.jsonl")

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "prompt": prompt
    }

    try:
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Warning: Failed to log prompt: {str(e)}", file=sys.stderr)

def list_prompt_history(n: int) -> None:
    log_file = os.path.expanduser("~/.eigengen/prompt_history.jsonl")
    if not os.path.exists(log_file):
        print("No prompt history found.")
        return

    with open(log_file, "r") as f:
        lines = f.readlines()

    prompts = [json.loads(line) for line in reversed(lines)]
    for i, entry in enumerate(prompts[:n], 1):
        timestamp = datetime.fromisoformat(entry["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{i}. [{timestamp}] {entry['prompt']}")

