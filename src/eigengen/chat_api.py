import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from eigengen import meld, operations, prompts, utils

# Import necessary components from the existing codebase
from eigengen.chat import EggChat
from eigengen.config import EggConfig


def create_app(config: EggConfig) -> FastAPI:
    # Instantiate a global EggChat instance using the active configuration.
    chat_instance = EggChat(config, user_files=None)
    app = FastAPI(debug=True, max_body_size=256 * 1024 * 1024)

    @app.post("/api/send")
    async def send_endpoint(request: Request):
        """
        Processes an incoming chat prompt from the request. This endpoint:
        - Combines the user's prompt with optional file contents.
        - Appends any initial file content if available.
        - Retrieves additional context for enhancing the response.
        - Generates an answer via the chat model.
        Returns a JSON response containing the generated answer.
        """
        data = await request.json()
        original_message = data.get("prompt", "")
        filepaths = data.get("filepaths", [])
        if isinstance(filepaths, list):
            for fp in filepaths:
                try:
                    with open(fp, "r", encoding="utf-8") as file:
                        file_content = file.read()
                    # Wrap the file content in a markdown code block
                    code_block = utils.encode_code_block(file_content)
                    original_message += "\n" + code_block
                except Exception:
                    # Optionally log the error or handle missing file gracefully
                    pass

        if chat_instance.initial_file_content and chat_instance.initial_file_content.strip() != "":
            original_message += "\n" + chat_instance.initial_file_content
            chat_instance.initial_file_content = ""

        retrieved_results = chat_instance.egg_rag.retrieve(
            target_files=chat_instance.target_files if chat_instance.target_files else None
        )
        rag_context = ""
        if retrieved_results:
            rag_context = "\n".join([f"{r[2]}" for r in retrieved_results])

        extended_message = original_message + ("\n\nRetrieved Context:\n" + rag_context if rag_context else "")
        local_messages = chat_instance.messages + [{"role": "user", "content": extended_message}]

        answer = ""

        chunk_iterator = operations.process_request(
            chat_instance.model, local_messages, prompts.get_prompt(chat_instance.mode)
        )
        for chunk in chunk_iterator:
            answer += chunk

        chat_instance.messages.append({"role": "user", "content": original_message})
        chat_instance.messages.append({"role": "assistant", "content": answer})

        resp_data = {"answer": answer}

        return JSONResponse(content=resp_data)

    @app.get("/api/history")
    async def history_endpoint():
        """
        Retrieves the complete chat conversation history.
        Returns a JSON array where each element is an object with "role" and "content" keys.
        """
        return JSONResponse(content=chat_instance.messages)

    @app.post("/api/extract_changes")
    async def extract_changes_endpoint(request: Request):
        """
        Receives a JSON payload with the following
        keys:
        - "assistant_answer": The assistant's response containing the diff instructions.
        """
        data = await request.json()
        assistant_answer = data.get("assistant_answer")
        if not assistant_answer:
            return JSONResponse(status_code=400, content={"error": "The 'assistant_answer' field is required."})

        # Extract the diff instructions from the assistant's response.
        changes = utils.extract_change_descriptions
        if not changes:
            return JSONResponse(status_code=500, content={"error": "Failed to extract diff instructions."})

        return JSONResponse(content={"changes": changes})

    @app.post("/api/meld")
    async def meld_endpoint(request: Request):
        """
        Receives a JSON payload with the fields:
        - "change": The diff instructions to be applied.
        - "filepath": The path to the file whose content will be modified.
        Applies the diff to the existing file content (or an empty string if absent) and produces
        a unified diff preview. Returns a JSON response containing both the diff preview and the new file content.
        """
        data = await request.json()
        change_content = data.get("change")
        filepath = data.get("filepath")
        if not change_content or not filepath:
            return JSONResponse(status_code=400, content={"error": "Both 'change' and 'filepath' are required fields."})

        # Generate the diff preview using the small model.
        original_content = ""
        # check if the file exists using os.path.exists
        if os.path.exists(filepath):
            try:
                with open(filepath) as f:
                    original_content = f.read()
            except Exception:
                return JSONResponse(status_code=500, content={"error": "Failed to read file."})

        new_content = meld.apply_changes(chat_instance.pm, filepath, original_content, change_content)
        diff_output = meld.produce_diff(filepath, original_content, new_content)

        if not diff_output:
            return JSONResponse(status_code=500, content={"error": "Diff generation failed."})

        return JSONResponse(content={"diff": diff_output, "file_content": new_content})

    @app.post("/api/apply")
    async def apply_endpoint(request: Request):
        """
        Receives a JSON payload with the following keys:
        - "file_content": The new content to be saved.
        - "file_path": The target file path.
        Attempts to update the specified file with the provided content.
        Returns a JSON response indicating whether the changes were successfully
        applied or detailing any error encountered.
        """
        data = await request.json()
        file_content = data.get("file_content")
        file_path = data.get("file_path")
        if not file_content or not file_path:
            return JSONResponse(
                status_code=400, content={"error": "Both 'file_content' and 'file_path' are required fields."}
            )

        # Apply the changes to the file.
        try:
            with open(file_path, "w") as f:
                f.write(file_content)
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"Failed to apply changes: {e}"})

        return JSONResponse(content={"message": "Changes applied successfully."})

    @app.get("/api/project_context")
    async def project_context():
        """
        Verifies whether the server is running within a Git repository.
        If a Git repository is detected, retrieves the list of tracked files using 'git ls-files'
        and returns them within a JSON object under the key "file_paths".
        If not, returns a JSON error message indicating that the server is not operating inside a Git repository.
        """
        if chat_instance.git_root:
            file_paths = utils.get_git_files()
            return JSONResponse(content={"file_paths": file_paths})
        else:
            return JSONResponse(status_code=400, content={"error": "Not running in a Git repository."})

    return app
