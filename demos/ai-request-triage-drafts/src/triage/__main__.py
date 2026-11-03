"""Command line. Mock mode is the default and does not use the network."""

import argparse
import os
from pathlib import Path

import uvicorn

from triage.api import create_app
from triage.pipeline import run_inbox


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Turn incoming requests into draft replies.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Read an inbox and write drafts plus a review log.")
    run.add_argument("--inbox", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--policy", type=Path, required=True)
    run.add_argument("--redact", action="store_true", help="Hide names, emails and phones in the review log.")
    serve = sub.add_parser("serve", help="HTTP endpoint for Zapier or Power Automate.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.command == "run":
        rows = run_inbox(args.inbox, args.out, args.policy, redact=args.redact)
        print(f"Wrote {len(rows)} draft(s) to {args.out}")
        return
    os.environ.setdefault("TRIAGE_OUT", "out")
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
