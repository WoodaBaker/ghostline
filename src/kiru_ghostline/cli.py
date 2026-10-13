"""Ghostline CLI: probe, watch, report, diff.

Batteries run where the agent lives — your laptop, your VPC, your CI —
so API keys and inference spend stay with you.
"""

import argparse
import sys

from . import __version__


def cmd_probe(args):
    """Run disorder probe batteries against a target agent."""
    print("probe: battery registry not yet implemented (see kiru#509).")
    print(f"  target={args.target} disorders={args.disorders or 'all'}")
    return 1


def cmd_watch(args):
    """Continuously monitor a live agent for drift/disorder signatures."""
    print("watch: continuous monitoring not yet implemented (see kiru#509).")
    return 1


def cmd_report(args):
    """Document a finding in the kiru upload-ready format."""
    print("report: finding format not yet implemented (see kiru#509).")
    return 1


def cmd_diff(args):
    """Re-run batteries across versions; track pass-rate drift."""
    print("diff: version diffing not yet implemented (see kiru#509).")
    return 1


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ghostline",
        description="Behavioral diagnostics for AI agents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("probe", help="Run disorder probe batteries.")
    p.add_argument("--target", required=True, help="Agent endpoint or model id to probe.")
    p.add_argument("--disorders", nargs="*", help="Disorder slugs to probe (default: all).")
    p.add_argument("--max-calls", type=int, default=200, help="Model-call budget for this run.")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("watch", help="Monitor a live agent for drift.")
    p.add_argument("--target", required=True, help="Agent event stream to watch.")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("report", help="Document a finding for kiru upload.")
    p.add_argument("--upload", action="store_true", help="Upload to kiru (opt-in).")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("diff", help="Diff battery results across versions.")
    p.add_argument("--from", dest="from_ref", required=True)
    p.add_argument("--to", dest="to_ref", required=True)
    p.set_defaults(func=cmd_diff)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
