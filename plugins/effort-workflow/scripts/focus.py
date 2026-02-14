#!/usr/bin/env python3

import argparse
from state_manager import set_focus, get_focus

def add_commands(subparser, common = None):
    common = common or []

    focus_get = subparser.add_parser('focus-get', description='print the current focused project')
    focus_get.set_defaults(func=lambda args: print(get_focus()))

    focus_cmd = subparser.add_parser('focus', description='Focus on an effort', parents=[common] if common else [])
    focus_cmd.add_argument('--unfocus', action='store_true', default=False)
    focus_cmd.set_defaults(func=lambda args: set_focus(args.name, unfocus=args.unfocus))
