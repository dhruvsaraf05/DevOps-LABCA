"""Stable tests for the Notes API. These must pass in every run, in any order."""

import pytest

from app import _version


def make_note(client, title="first", content="hello"):
    return client.post("/notes", json={"title": title, "content": content})


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_defaults_to_dev(client, monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.setattr(_version, "GIT_SHA", "dev")
    assert client.get("/version").json() == {"version": "dev"}


def test_version_prefers_env_var(client, monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc1234")
    assert client.get("/version").json() == {"version": "abc1234"}


def test_create_note_returns_created_note(client):
    response = make_note(client, "shopping", "milk")
    assert response.status_code == 201
    assert response.json() == {"id": 1, "title": "shopping", "content": "milk"}


def test_create_note_content_is_optional(client):
    response = client.post("/notes", json={"title": "no body"})
    assert response.status_code == 201
    assert response.json()["content"] == ""


@pytest.mark.parametrize("payload", [{}, {"title": ""}, {"content": "x"}])
def test_create_note_rejects_invalid_payload(client, payload):
    assert client.post("/notes", json=payload).status_code == 422


def test_list_notes_empty(client):
    response = client.get("/notes")
    assert response.status_code == 200
    assert response.json() == []


def test_list_notes_returns_all_created(client):
    make_note(client, "a")
    make_note(client, "b")
    titles = [n["title"] for n in client.get("/notes").json()]
    assert titles == ["a", "b"]


def test_get_note(client):
    note_id = make_note(client, "findme").json()["id"]
    response = client.get(f"/notes/{note_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "findme"


def test_get_missing_note_is_404(client):
    assert client.get("/notes/999").status_code == 404


def test_update_note(client):
    note_id = make_note(client, "old", "old body").json()["id"]
    response = client.put(f"/notes/{note_id}", json={"title": "new", "content": "new body"})
    assert response.status_code == 200
    assert response.json() == {"id": note_id, "title": "new", "content": "new body"}
    assert client.get(f"/notes/{note_id}").json()["title"] == "new"


def test_update_missing_note_is_404(client):
    response = client.put("/notes/999", json={"title": "x"})
    assert response.status_code == 404


def test_delete_note(client):
    note_id = make_note(client).json()["id"]
    assert client.delete(f"/notes/{note_id}").status_code == 204
    assert client.get(f"/notes/{note_id}").status_code == 404


def test_delete_missing_note_is_404(client):
    assert client.delete("/notes/999").status_code == 404


def test_note_ids_increment(client):
    first = make_note(client, "one").json()["id"]
    second = make_note(client, "two").json()["id"]
    assert second == first + 1
