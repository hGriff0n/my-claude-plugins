#!/usr/bin/env python3

import argparse
from state_manager import set_status, set_focus

def activate_effort(args: argparse.Namespace, backlog=False):
    status = "backlog" if backlog else "active"
    set_status(args.name, status)

    # If activating, also set focus
    if not backlog:
        set_focus(args.name)


def add_commands(subparser, common=None):
    common = common or []
    
    promote = subparser.add_parser('promote', description='Activate an effort', parents=[common] if common else [])
    promote.set_defaults(func=lambda args: activate_effort(args))

    relegate = subparser.add_parser('relegate', description='Move to backlog', parents=[common] if common else [])
    relegate.set_defaults(func=lambda args: activate_effort(args, backlog=True))
