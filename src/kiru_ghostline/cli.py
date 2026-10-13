"""Ghostline CLI: probe, watch, report, diff, check.

Batteries run where the agent lives -- your laptop, your VPC, your CI --
so API keys and inference spend stay with you.
"""

import argparse
import json
import sys

from . import __version__


class GhostlineArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 on usage errors."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def cmd_probe(args):
    from .runner import resolve_target, run_batteries

    target = resolve_target(args.target)
    report = run_batteries(target, slugs=args.disorders, max_calls=args.max_calls)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if not report.signals else 2


def cmd_watch(args):
    from .watch import watch_stream

    watch_stream(args.target)
    return 0


def cmd_report(args):
    from .findings import Finding

    finding = Finding(
        observed_behavior=args.behavior,
        catalog_version=args.catalog_version,
        model=args.model or "",
        scaffolding=args.scaffolding or None,
    )
    if args.upload:
        print("upload: kiru API client not yet implemented (kiru#509).")
        print("finding that would be uploaded:")
    print(finding.to_json())
    return 0


def cmd_diff(args):
    print("diff: version diffing not yet implemented (kiru#509).")
    return 1


def cmd_check(args):
    from pathlib import Path

    from .checker import run_check

    if args.symptom == "-":
        symptom = sys.stdin.read()
    else:
        symptom = args.symptom

    catalog_path = Path(args.catalog) if args.catalog else None

    fail_on = None
    if args.fail_on:
        fail_on = [c.strip() for c in args.fail_on.split(",") if c.strip()]

    return run_check(
        symptom=symptom,
        catalog_path=catalog_path,
        top_n=args.top,
        threshold=args.threshold,
        output_format=args.format,
        fail_on=fail_on,
        quiet=getattr(args, "quiet", False),
    )


def _add_common_args(
    parser: argparse.ArgumentParser, suppress_default: bool = False
) -> None:
    """Add common arguments to a parser.

    Args:
        parser: The parser to add arguments to.
        suppress_default: If True, use SUPPRESS for defaults to avoid
            overwriting values set by the main parser.
    """
    default = argparse.SUPPRESS if suppress_default else None
    parser.add_argument(
        "--catalog",
        metavar="PATH",
        default=default,
        help="Path to custom catalog.json (default: vendored).",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False if not suppress_default else argparse.SUPPRESS,
        help="Suppress detailed output.",
    )


def build_parser():
    parser = GhostlineArgumentParser(
        prog="ghostline",
        description="Behavioral diagnostics for AI agents.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    _add_common_args(parser)

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("probe", help="Run disorder probe batteries.")
    _add_common_args(p, suppress_default=True)
    p.add_argument("--target", required=True, help="Target spec ('echo' for demo).")
    p.add_argument("--disorders", nargs="*", help="Battery slugs (default: all).")
    p.add_argument("--max-calls", type=int, default=200, help="Model-call budget.")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("watch", help="Monitor a live agent for drift.")
    _add_common_args(p, suppress_default=True)
    p.add_argument("--target", required=True, help="Agent event stream to watch.")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("report", help="Document a finding for kiru upload.")
    _add_common_args(p, suppress_default=True)
    p.add_argument("--behavior", required=True, help="What was observed.")
    p.add_argument("--model", default="", help="Model under test.")
    p.add_argument("--scaffolding", default="", help="Scaffolding/framework.")
    p.add_argument(
        "--catalog-version", default="dem-x/dev", help="Disorder catalog version."
    )
    p.add_argument("--upload", action="store_true", help="Upload to kiru (opt-in).")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("diff", help="Diff battery results across versions.")
    _add_common_args(p, suppress_default=True)
    p.add_argument("--from", dest="from_ref", required=True)
    p.add_argument("--to", dest="to_ref", required=True)
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser(
        "check", help="Check a symptom against the DEM-X catalog (offline)."
    )
    _add_common_args(p, suppress_default=True)
    p.add_argument(
        "symptom",
        help="Symptom description to check, or '-' to read from stdin.",
    )
    p.add_argument(
        "--top", type=int, default=3, help="Number of top results (default: 3)."
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Match score threshold (default: 0.5).",
    )
    p.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    p.add_argument(
        "--fail-on",
        metavar="CODES",
        help="Exit 2 only if these disorder codes match (comma-separated).",
    )
    p.set_defaults(func=cmd_check)

    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        if e.code == 2:
            return 1
        return e.code if e.code else 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
