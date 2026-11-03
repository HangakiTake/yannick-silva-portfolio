import argparse
import json
from pathlib import Path

from .audit import run_audit
from .guide import render_guide
from .llm import make_llm
from .report import render_shortlist
from .runner import run_inquiries
from .workflow import build_workflow


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="workday_audit")
    sub = parser.add_subparsers(dest="cmd", required=True)

    audit = sub.add_parser("audit")
    audit.add_argument("notes")
    audit.add_argument("--out", type=Path, required=True)

    inquiries = sub.add_parser("inquiries")
    inquiries.add_argument("file", type=Path)
    inquiries.add_argument("--out", type=Path, required=True)

    workflow = sub.add_parser("workflow")
    workflow.add_argument("--out", type=Path, required=True)

    guide = sub.add_parser("guide")
    guide.add_argument("notes", type=Path)
    guide.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.cmd == "audit":
        text = Path(args.notes).read_text(encoding="utf-8")
        result = run_audit(text)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "shortlist.html").write_text(
            render_shortlist(result["ranked"], result["extraction"].questions, result["redaction"].counts),
            encoding="utf-8",
        )
        result["ranked"].drop(columns=["evidence"], errors="ignore").to_csv(args.out / "shortlist.csv", index=False)
        (args.out / "redaction-counts.json").write_text(
            json.dumps(result["redaction"].counts, indent=2), encoding="utf-8"
        )
        print(f"tasks {len(result['ranked'])} top {result['ranked'].iloc[0]['id']}")
        return
    if args.cmd == "inquiries":
        emails = json.loads(args.file.read_text(encoding="utf-8"))
        llm, status = make_llm("mock")
        result = run_inquiries(emails, llm)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "inquiries.json").write_text(
            json.dumps(result["results"], indent=2), encoding="utf-8"
        )
        print(f"{status} {len(result['results'])} drafts, sent {len(result['sent'])}")
        return
    if args.cmd == "workflow":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(build_workflow(), indent=2), encoding="utf-8")
        print(args.out)
        return
    if args.cmd == "guide":
        text = args.notes.read_text(encoding="utf-8")
        result = run_audit(text)
        top = result["ranked"].iloc[0].to_dict()
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "guide.html").write_text(render_guide(top, "html"), encoding="utf-8")
        (args.out / "guide.md").write_text(render_guide(top, "md"), encoding="utf-8")
        print(top["id"])


if __name__ == "__main__":
    main()
