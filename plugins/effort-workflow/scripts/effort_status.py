#!/usr/bin/env python3

import argparse
from state_manager import load_state

def list_efforts(args: argparse.Namespace):
    state = load_state()
    focus = state.get("focus")
    active = state.get("active", [])
    backlog = state.get("backlog", [])
    
    # Simple list mode (default) - Shows Active projects
    if not args.all and not args.backlog and not args.tasks:
        print("\n🚀 Active Efforts")
        if not active:
            print("  (none)")
        for name in active:
            prefix = "👉" if name == focus else "  "
            print(f"{prefix} {name}")
        return

    # Backlog mode
    if args.backlog or args.all:
        print("\n📦 Backlog")
        if not backlog:
            print("  (none)")
        for name in backlog:
            prefix = "👉" if name == focus else "  "
            print(f"{prefix} {name}")
            
    # Tasks mode (stub for now, as requested)
    if args.tasks:
        print("\n📝 Tasks view not yet implemented")


def add_commands(subparser, common=None):
    common = common or []
    
    status = subparser.add_parser('list', description='List efforts', parents=[common] if common else [])
    status.add_argument("--all", "-a", action="store_true", help="Show active and backlog")
    status.add_argument("--backlog", "-b", action="store_true", help="Show backlog only")
    status.add_argument("--tasks", "-t", action="store_true", help="Show tasks (future)")
    status.set_defaults(func=list_efforts)
