import os

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from app import _version, store

app = FastAPI(title="Notes API")


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = ""


class Note(NoteIn):
    id: int


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict:
    return {"version": os.environ.get("GIT_SHA") or _version.GIT_SHA}


@app.post("/notes", status_code=201, response_model=Note)
def create_note(body: NoteIn) -> dict:
    return store.create(body.title, body.content)


@app.get("/notes", response_model=list[Note])
def list_notes() -> list[dict]:
    return store.list_all()


@app.get("/notes/{note_id}", response_model=Note)
def get_note(note_id: int) -> dict:
    note = store.get(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.put("/notes/{note_id}", response_model=Note)
def update_note(note_id: int, body: NoteIn) -> dict:
    note = store.update(note_id, body.title, body.content)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int) -> Response:
    if not store.delete(note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return Response(status_code=204)
