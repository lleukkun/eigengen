from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Import necessary components from the existing codebase
from eigengen.chat import EggChat
from eigengen import operations, prompts, utils, meld
from eigengen.config import EggConfig

def create_app(config: EggConfig) -> FastAPI:
    # Instantiate a global EggChat instance using the active configuration.
    chat_instance = EggChat(config, user_files=None)
    app = FastAPI(debug=True, max_body_size=256*1024*1024)

    @app.post("/api/send")
    async def send_endpoint(request: Request):
        """
        Process a chat prompt and return a JSON object.
        """
        data = await request.json()
        original_message = data.get("prompt", "")

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
            chat_instance.model_tuple.large,
            local_messages,
            prompts.get_prompt(chat_instance.mode)
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
        Return the chat history as a JSON array with objects { "role": ..., "content": ... }.
        """
        return JSONResponse(content=chat_instance.messages)

    @app.post("/api/meld")
    async def meld_endpoint(request: Request):
        """
        Accept a JSON payload with "code_block" and "code_filepath" fields.
        Returns a unified diff preview of the changes.
        """
        data = await request.json()
        code_block = data.get("code_block")
        code_filepath = data.get("code_filepath")
        if not code_block or not code_filepath:
            return JSONResponse(status_code=400, content={"error": "Both 'code_block' and 'code_filepath' are required fields."})

        # Generate the diff preview using the small model.
        diff_output, new_file_content = meld.generate_meld_diff(chat_instance.model_tuple.small, code_filepath, code_block, chat_instance.git_root)
        if not diff_output:
            return JSONResponse(status_code=500, content={"error": "Diff generation failed."})

        return JSONResponse(content={"diff": diff_output, "file_content": new_file_content})

    @app.post("/api/apply")
    async def apply_endpoint(request: Request):
        """
        Accept a JSON payload with "code_block" and "code_filepath" fields.
        Apply the changes to the file.
        """
        data = await request.json()
        file_content = data.get("file_content")
        file_path = data.get("file_path")
        if not file_content or not file_path:
            return JSONResponse(status_code=400, content={"error": "Both 'code_block' and 'code_filepath' are required fields."})

        # Apply the changes to the file.
        try:
            meld.apply_meld_diff(file_path, file_content)
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"Failed to apply changes: {e}"})

        return JSONResponse(content={"message": "Changes applied successfully."})

    @app.get("/api/project_context")
    async def project_context():
        """
        Checks if the server is running in a Git repository.
        If yes, performs 'git ls-files' and returns a JSON object with field "file_paths" containing a list of files.
        Otherwise, returns an error message.
        """
        if chat_instance.git_root:
            file_paths = utils.get_git_files()
            return JSONResponse(content={"file_paths": file_paths})
        else:
            return JSONResponse(status_code=400, content={"error": "Not running in a Git repository."})

    return app

if __name__ == "__main__":
    print("Standalone API mode is disabled. Please run 'eigengen.py' to start the application.")
