#!/usr/bin/env python3
import sys
import argparse

import init_effort
import effort_status
import state_manager
import focus
import activate


def make_parser():
    common_args = argparse.ArgumentParser(add_help=False)
    common_args.add_argument('name', help='Name of the effort')

    parser = argparse.ArgumentParser(description='Manage efforts')
    subparsers = parser.add_subparsers(dest='command')

    for module in [init_effort, effort_status, state_manager, focus, activate]:
        module.add_commands(subparsers, common=common_args)
    # promote = subparsers.add_parser('promote', description='Upgrade an effort from an idea/proposal', parents=[common_args])

    return parser

def main():
    parser = make_parser()
    args = parser.parse_args()

    try:
        args.func(args)
        sys.exit(0)

    except Exception as e:
        print(f"Error initializing effort: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
