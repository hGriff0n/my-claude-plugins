#!/usr/bin/env python3

import json
from pathlib import Path
from utils import get_effort_dir

STATE_FILE = Path.home() / ".cache" / "efforts" / "efforts.json"
EFFORT_BASE_DIR = get_effort_dir()

# TODO: me - This needs to be improved to handle more schemas
def new_state():
    return {"focus": None, "active": [], "backlog": []}

def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return new_state()

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

def get_focus():
    return load_state().get("focus", None)

def set_focus(name, unfocus=False):
    state = load_state()
    # Validate effort exists
    effort_dir = EFFORT_BASE_DIR / name
    if not effort_dir.exists():
        raise Exception(f"Error: Effort '{name}' does not exist.")
    
    if unfocus:
        state.pop('focus', None)
    else:
        state["focus"] = name
        print(effort_dir)

    save_state(state)

def set_status(name, status):
    """Set status to 'active' or 'backlog'"""
    if status == 'focus':
        raise Exception('Invalid status argument')

    state = load_state()
    
    # Don't need to do anything if we're already in the proper state
    if name in state.get(status, []):
        return
    
    # Remove it from lists it was previously in (skip 'focus' since it's a string)
    for k in ['active', 'backlog']:
        if name in state.get(k, []):
            state[k].remove(name)

    if status not in state:
        state[status] = [name]
    else:
        state[status].append(name)
    
    save_state(state)

def scan_pkm(args=None):
    state = new_state()
    for file in EFFORT_BASE_DIR.iterdir():
        if file.name in ['__ideas', 'dashboard.base']:
            continue

        if file.name == '__backlog':
            state['backlog'].extend(f.name for f in file.iterdir())
        elif file.is_dir() and (file / 'README.md').exists():
            state['active'].append(file.name)
        else:
            state['backlog'].append(file.name)
    save_state(state)
    print(json.dumps(state, indent=2))


def add_commands(subparser, common=None):
    common = common or []

    scan = subparser.add_parser('scan', description='Reconstruct internal state')
    scan.set_defaults(func=scan_pkm)
