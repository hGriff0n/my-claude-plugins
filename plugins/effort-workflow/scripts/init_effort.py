#!/usr/bin/env python3
import argparse
import shutil
from pathlib import Path
from state_manager import set_focus, set_status
from utils import get_effort_dir


def add_commands(subparser, common = None):
    common = common or []

    new = subparser.add_parser('new', description='Create a new effort', parents=[common])
    new.set_defaults(func=new_effort)


def new_effort(args: argparse.Namespace):
    effort_dir = get_effort_dir(args.name)

    # We do not early return if the path exists because it's possible the path may not be properly configured as an effort
    if not effort_dir.exists():
        effort_dir.mkdir(parents=True, exist_ok=True)

    # If there is a file at that place, we will assume it is the README.md
    elif not effort_dir.is_dir():
        shutil.move(effort_dir, '/tmp.md')
        effort_dir.mkdir(parents=True, exist_ok=True)
        shutil.move('/tmp.md', effort_dir / 'README.md')

    # Make sure that the folder has all of the required files and other metadsetup    
    dashboard_file = effort_dir / 'README.md'
    if not dashboard_file.exists():
        shutil.copy(Path('~/clawd/skills/effort-workflow/assets/readme.template.md').expanduser(), dashboard_file)
    
    # Update the internal state tracking
    set_status(args.name, 'active')
    set_focus(args.name)
