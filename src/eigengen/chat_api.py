from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os

# Import necessary components from the existing codebase
from eigengen.chat import EggChat
from eigengen.progress import ProgressIndicator
from eigengen import operations, prompts, utils
from eigengen.config import EggConfig

def create_app(config: EggConfig) -> FastAPI:
    # Instantiate a global EggChat instance using the active configuration.
    chat_instance = EggChat(config, user_files=None)
    app = FastAPI()

    @app.post("/api/send")
    async def send_endpoint(request: Request):
        """
        Process a chat prompt and return a JSON object.
        """
        data = await request.json()
        original_message = data.get("prompt", "")
        diff_mode = data.get("diff_mode", False)

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

    return app

if __name__ == "__main__":
    print("Standalone API mode is disabled. Please run 'eigengen.py' to start the application.")

