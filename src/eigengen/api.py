from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict
import uvicorn
import os

from eigengen import operations, utils, providers

app = FastAPI()

class PromptRequest(BaseModel):
    prompt: str
    files: Optional[List[str]] = None

class DiffRequest(BaseModel):
    prompt: str
    files: List[str]

class ReviewRequest(BaseModel):
    use_git_root: bool
    review_messages: Optional[List[Dict[str, str]]] = None
    messages: Optional[List[Dict[str, str]]] = None
    is_first_round: bool

class FileNamesResponse(BaseModel):
    filenames: List[str]

class PromptResponse(BaseModel):
    response: str

class DiffResponse(BaseModel):
    diff: str

class ReviewResponse(BaseModel):
    review: str
    updated_files: Dict[str, str]
    diff: str

model: str = "claude-sonnet"  # Default model, will be updated from CLI argument

@app.get("/api/v1/filenames", response_model=FileNamesResponse)
async def filenames_endpoint():
    return FileNamesResponse(filenames=app.state.filenames)

@app.post("/api/v1/reload_filenames", response_model=FileNamesResponse)
async def reload_filenames():
    app.state.filelist = operations.get_file_list(app.state.git_files, app.state.extra_files)
    return FileNamesResponse(filenames=app.state.filenames)


@app.post("/api/v1/prompt", response_model=PromptResponse)
async def prompt_endpoint(request: PromptRequest):
    messages = []
    relevant_files = operations.get_context_aware_files(app.state.filenames, request.files)

    for fname in relevant_files:
        if not os.path.exists(fname):
            raise HTTPException(status_code=404, detail=f"File not found: {fname}")
        with open(fname, 'r') as f:
            content = f.read()
        messages.extend([
            {"role": "user", "content": f"<eigengen_file name=\"{fname}\">\n{content}\n</eigengen_file>"},
            {"role": "assistant", "content": "ok"}
        ])
    messages.append({"role": "user", "content": request.prompt})

    output = "".join(operations.process_request(model, messages, "default"))
    return PromptResponse(response=output)

@app.post("/api/v1/diff", response_model=DiffResponse)
async def diff_endpoint(request: DiffRequest, background_tasks: BackgroundTasks):
    messages = []
    relevant_files = operations.get_context_aware_files(app.state.filenames, request.files)

    for fname in relevant_files:
        if not os.path.exists(fname):
            raise HTTPException(status_code=404, detail=f"File not found: {fname}")
        with open(fname, 'r') as f:
            content = f.read()
        messages.extend([
            {"role": "user", "content": f"<eigengen_file name=\"{fname}\">\n{content}\n</eigengen_file>"},
            {"role": "assistant", "content": "ok"}
        ])
    messages.append({"role": "user", "content": request.prompt})

    output = "".join(operations.process_request(model, messages, "diff"))
    new_files = utils.extract_file_content(output)

    diff = ""
    for fname, new_content in new_files.items():
        if os.path.exists(fname):
            with open(fname, 'r') as f:
                original_content = f.read()
        else:
            original_content = ""
        diff += operations.generate_diff(original_content, new_content, fname, use_color=False)

    # Automatically apply the patch in the background
    background_tasks.add_task(operations.apply_patch, diff, auto_apply=True)

    return DiffResponse(diff=diff)

@app.post("/api/v1/code_review", response_model=ReviewResponse)
async def code_review_endpoint(request: ReviewRequest):
    final_answer, new_files, diff, _ = operations.do_code_review_round(
        model,
        request.use_git_root,
        request.messages or list({}),
        request.review_messages or list({}),
        request.is_first_round
    )

    return ReviewResponse(review=final_answer, updated_files=new_files, diff=diff)

def start_api(selected_model: str, filenames: List[str], host: str = "localhost", port: int = 10366):
    app.state.model = selected_model
    app.state.filenames = filenames

    uvicorn.run(app, host=host, port=port)

