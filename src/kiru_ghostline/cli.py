"""Ghostline CLI: probe, watch, report, diff.

Batteries run where the agent lives — your laptop, your VPC, your CI —
so API keys and inference spend stay with you.
"""

import argparse
import json
import sys

from . import __version__


def cmd_probe(args):
    from .runner import resolve_target, run_batteries

    target = resolve_target(args.target)
    report = run_batteries(target, slugs=args.disorders, max_calls=args.max_calls)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if not report.signals else 2  # exit 2 when a signal is detected


def cmd_watch(args):
    from .watch import watch_stream

    watch_stream(args.target)
    return 0


def cmd_report(args):
    from .findings import Finding

    finding = Finding(
        observed_behavior=args.behavior,
        model=args.model or "",
        scaffolding=args.scaffolding or "",
    )
    if args.upload:
        print("upload: kiru API client not yet implemented (kiru#509).")
        print("finding that would be uploaded:")
    print(finding.to_json())
    return 0


def cmd_diff(args):
    print("diff: version diffing not yet implemented (kiru#509).")
    return 1


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ghostline",
        description="Behavioral diagnostics for AI agents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("probe", help="Run disorder probe batteries.")
    p.add_argument("--target", required=True, help="Target spec ('echo' for demo).")
    p.add_argument("--disorders", nargs="*", help="Battery slugs (default: all).")
    p.add_argument("--max-calls", type=int, default=200, help="Model-call budget.")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("watch", help="Monitor a live agent for drift.")
    p.add_argument("--target", required=True, help="Agent event stream to watch.")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("report", help="Document a finding for kiru upload.")
    p.add_argument("--behavior", required=True, help="What was observed.")
    p.add_argument("--model", default="", help="Model under test.")
    p.add_argument("--scaffolding", default="", help="Scaffolding/framework.")
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
