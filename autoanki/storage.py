from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import CARDS_PATH

STORE_VERSION = 1
DEFAULT_STACK_NAME = "Default"
MAX_STACK_NAME_LENGTH = 80
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_stack(name: str) -> dict[str, Any]:
    now = _now()
    return {"id": str(uuid.uuid4()), "name": name, "created_at": now, "updated_at": now, "pending": [], "cards": []}


def new_store() -> dict[str, Any]:
    stack = _new_stack(DEFAULT_STACK_NAME)
    return {"version": STORE_VERSION, "active_stack_id": stack["id"], "stacks": [stack]}


def _validate_store(data: Any, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("version") != STORE_VERSION or not isinstance(data.get("stacks"), list):
        raise ValueError(f"{path} must contain an AutoAnki version {STORE_VERSION} stack store")
    stacks = data["stacks"]
    if not stacks:
        raise ValueError(f"{path} must contain at least one stack")
    ids: set[str] = set()
    names: set[str] = set()
    for stack in stacks:
        if not isinstance(stack, dict) or not isinstance(stack.get("id"), str):
            raise ValueError(f"{path} contains an invalid stack")
        name = str(stack.get("name", "")).strip()
        if not name or len(name) > MAX_STACK_NAME_LENGTH or name.casefold() in names or stack["id"] in ids:
            raise ValueError(f"{path} contains invalid or duplicate stack names/IDs")
        if not isinstance(stack.get("pending"), list) or not isinstance(stack.get("cards"), list):
            raise ValueError(f"{path} contains a stack without pending/cards lists")
        ids.add(stack["id"]); names.add(name.casefold())
    if data.get("active_stack_id") not in ids:
        raise ValueError(f"{path} has an invalid active_stack_id")
    return data


def load_store(path: str | Path = CARDS_PATH) -> dict[str, Any]:
    file_path = Path(path)
    with _LOCK:
        if not file_path.exists() or file_path.stat().st_size == 0:
            store = new_store()
            save_store(store, file_path)
            return store
        return _validate_store(json.loads(file_path.read_text(encoding="utf-8-sig")), file_path)


def save_store(store: dict[str, Any], path: str | Path = CARDS_PATH) -> None:
    file_path = Path(path)
    _validate_store(store, file_path)
    with _LOCK:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{file_path.name}.", suffix=".tmp", dir=file_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(store, handle, ensure_ascii=False, indent=2)
                handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp_name, file_path)
        finally:
            if os.path.exists(temp_name): os.unlink(temp_name)


def get_stack(store: dict[str, Any], stack_id: str | None = None, stack_name: str | None = None) -> dict[str, Any]:
    wanted = stack_id or store["active_stack_id"]
    for stack in store["stacks"]:
        if stack["id"] == wanted or (stack_name is not None and stack["name"].casefold() == stack_name.strip().casefold()):
            return stack
    raise ValueError("Stack was not found")


def create_stack(name: str, path: str | Path = CARDS_PATH) -> dict[str, Any]:
    name = name.strip()
    if not name or len(name) > MAX_STACK_NAME_LENGTH: raise ValueError("Stack name must be 1-80 characters")
    with _LOCK:
        store = load_store(path)
        if any(s["name"].casefold() == name.casefold() for s in store["stacks"]): raise ValueError("Stack names must be unique")
        stack = _new_stack(name); store["stacks"].append(stack); store["active_stack_id"] = stack["id"]
        save_store(store, path); return stack


def select_stack(stack_id: str, path: str | Path = CARDS_PATH) -> dict[str, Any]:
    with _LOCK:
        store = load_store(path); stack = get_stack(store, stack_id); store["active_stack_id"] = stack["id"]
        save_store(store, path); return stack


def rename_stack(stack_id: str, name: str, path: str | Path = CARDS_PATH) -> dict[str, Any]:
    name = name.strip()
    if not name or len(name) > MAX_STACK_NAME_LENGTH: raise ValueError("Stack name must be 1-80 characters")
    with _LOCK:
        store = load_store(path); stack = get_stack(store, stack_id)
        if any(s["id"] != stack_id and s["name"].casefold() == name.casefold() for s in store["stacks"]): raise ValueError("Stack names must be unique")
        stack["name"] = name; stack["updated_at"] = _now(); save_store(store, path); return stack


def delete_stack(stack_id: str, confirmation: str, path: str | Path = CARDS_PATH) -> dict[str, Any]:
    with _LOCK:
        store = load_store(path); stack = get_stack(store, stack_id)
        if len(store["stacks"]) == 1: raise ValueError("The final stack cannot be deleted")
        if confirmation != stack["name"]: raise ValueError("Enter the exact stack name to delete it")
        store["stacks"] = [s for s in store["stacks"] if s["id"] != stack_id]
        if store["active_stack_id"] == stack_id: store["active_stack_id"] = store["stacks"][0]["id"]
        save_store(store, path); return stack


def update_stack(stack_id: str, path: str | Path, updater: Any) -> dict[str, Any]:
    with _LOCK:
        store = load_store(path); stack = get_stack(store, stack_id); updater(stack); stack["updated_at"] = _now()
        save_store(store, path); return stack


# Compatibility helpers operate on the active stack's reviewed cards.
def load_cards(path: str | Path = CARDS_PATH, stack_id: str | None = None) -> list[dict[str, Any]]:
    return get_stack(load_store(path), stack_id)["cards"]


def save_cards(cards: list[dict[str, Any]], path: str | Path = CARDS_PATH, stack_id: str | None = None) -> None:
    store = load_store(path); stack = get_stack(store, stack_id); stack["cards"] = cards; stack["updated_at"] = _now(); save_store(store, path)


def append_cards(new_cards: list[dict[str, Any]], path: str | Path = CARDS_PATH, stack_id: str | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        store = load_store(path); stack = get_stack(store, stack_id); stack["cards"].extend(new_cards); stack["updated_at"] = _now(); save_store(store, path)
        return stack["cards"]
