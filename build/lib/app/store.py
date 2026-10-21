"""In-memory notes store.

State lives at module level on purpose: it is shared by every request in the process
(and by every test), which later lets us seed an order-dependent flaky test.
On Vercel (serverless) this state does not persist across requests.
"""

_notes: dict[int, dict] = {}
_next_id = 1

# Name of the last simulated operation (see app/external.py). Process-wide state that
# reset() deliberately does NOT clear; the order-dependent flaky test relies on it.
last_operation: str | None = None


def record_operation(name: str) -> None:
    global last_operation
    last_operation = name


def create(title: str, content: str) -> dict:
    global _next_id
    note = {"id": _next_id, "title": title, "content": content}
    _notes[_next_id] = note
    _next_id += 1
    return note


def list_all() -> list[dict]:
    return list(_notes.values())


def get(note_id: int) -> dict | None:
    return _notes.get(note_id)


def update(note_id: int, title: str, content: str) -> dict | None:
    note = _notes.get(note_id)
    if note is None:
        return None
    note["title"] = title
    note["content"] = content
    return note


def delete(note_id: int) -> bool:
    return _notes.pop(note_id, None) is not None


def reset() -> None:
    global _next_id
    _notes.clear()
    _next_id = 1
