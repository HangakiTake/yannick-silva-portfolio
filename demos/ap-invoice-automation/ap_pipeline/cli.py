"""Command line for the offline demo and the accuracy report."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ap_pipeline.adapters.extract_llm import UNTESTED_NOTICE as LLM_NOTICE
from ap_pipeline.adapters.extract_llm import LlmExtractor
from ap_pipeline.adapters.extract_rules import RulesExtractor
from ap_pipeline.adapters.mail_graph import UNTESTED_NOTICE as GRAPH_NOTICE
from ap_pipeline.adapters.mail_graph import GraphMailSource
from ap_pipeline.adapters.mail_local import LocalFolderMailSource
from ap_pipeline.adapters.qbo_mock import MockQBOClient
from ap_pipeline.adapters.qbo_rest import UNTESTED_NOTICE as QBO_NOTICE
from ap_pipeline.adapters.qbo_rest import QboRestClient
from ap_pipeline.errors import PipelineError
from ap_pipeline.eval_accuracy import write_reports
from ap_pipeline.master_data import JobDirectory, VendorDirectory, load_open_jobs, load_vendors
from ap_pipeline.pipeline import PipelineConfig, run_pipeline
from ap_pipeline.runlog import RunLog
from ap_pipeline.state import StateStore

_DEMO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Accounts-payable invoice demo")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Process the inbox once")
    run.add_argument("--mail", choices=["local", "graph"], default="local")
    run.add_argument("--mail-root", type=Path, help="Local mail root (inbox, filed folders, outbox)")
    run.add_argument("--extractor", choices=["rules", "llm"], default="rules")
    run.add_argument("--llm-provider", choices=["openai", "anthropic"], default="openai")
    run.add_argument("--qbo", choices=["mock", "rest"], default="mock")
    run.add_argument("--dry-run", action="store_true", help="Draft vendor replies instead of sending them")
    run.add_argument("--state", type=Path, required=True)
    run.add_argument("--log-dir", type=Path, required=True)
    run.add_argument("--vendors", type=Path, default=_DEMO_ROOT / "fixtures" / "vendors.json")
    run.add_argument("--open-jobs", type=Path, default=_DEMO_ROOT / "fixtures" / "open_jobs.json")
    run.add_argument("--expense-account-id", default=os.environ.get("QBO_EXPENSE_ACCOUNT_ID", "80"))

    evaluate = sub.add_parser("eval", help="Score the rules extractor and record LLM status")
    evaluate.add_argument("--manifest", type=Path, default=_DEMO_ROOT / "fixtures" / "manifest.json")
    evaluate.add_argument("--out-dir", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "eval":
            rules, llm = write_reports(args.manifest, args.out_dir)
            print(
                f"rules accuracy {rules['correct']}/{rules['total']} "
                f"({rules['accuracy']:.4f}) status={rules['status']}"
            )
            print(f"llm status={llm['status']}: {llm['reason']}")
            return 0
        return _run(args)
    except PipelineError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _run(args) -> int:
    if args.mail == "graph":
        print(GRAPH_NOTICE, file=sys.stderr)
        mail = GraphMailSource(
            tenant_id=os.environ.get("GRAPH_TENANT_ID", ""),
            client_id=os.environ.get("GRAPH_CLIENT_ID", ""),
            client_secret=os.environ.get("GRAPH_CLIENT_SECRET", ""),
            mailbox=os.environ.get("GRAPH_MAILBOX", ""),
        )
        mail_name = "graph"
    else:
        if args.mail_root is None:
            print("Local mail requires --mail-root", file=sys.stderr)
            return 1
        mail = LocalFolderMailSource(args.mail_root)
        mail_name = "local"

    if args.extractor == "llm":
        print(LLM_NOTICE, file=sys.stderr)
        provider = args.llm_provider
        if provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
        extractor = LlmExtractor(provider=provider, api_key=api_key, model=model)
        extractor_name = "llm"
    else:
        extractor = RulesExtractor()
        extractor_name = "rules"

    if args.qbo == "rest":
        print(QBO_NOTICE, file=sys.stderr)
        if args.dry_run:
            print(
                "Dry-run drafts vendor replies and does not create bills, move mail, or mark messages done.",
                file=sys.stderr,
            )
        cache = os.environ.get("QBO_TOKEN_CACHE")
        qbo = QboRestClient(
            client_id=os.environ.get("QBO_CLIENT_ID", ""),
            client_secret=os.environ.get("QBO_CLIENT_SECRET", ""),
            refresh_token=os.environ.get("QBO_REFRESH_TOKEN", ""),
            realm_id=os.environ.get("QBO_REALM_ID", ""),
            expense_account_id=args.expense_account_id,
            base_url=os.environ.get("QBO_BASE_URL", "https://sandbox-quickbooks.api.intuit.com"),
            token_cache=Path(cache) if cache else None,
            allow_production=os.environ.get("QBO_ALLOW_PRODUCTION") == "yes",
        )
        qbo_name = "rest"
    else:
        qbo = MockQBOClient()
        qbo_name = "mock"

    vendors = VendorDirectory(load_vendors(args.vendors))
    jobs = JobDirectory(load_open_jobs(args.open_jobs))
    summary = run_pipeline(
        mail=mail,
        extractor=extractor,
        qbo=qbo,
        vendors=vendors,
        jobs=jobs,
        state=StateStore(args.state),
        run_log=RunLog(args.log_dir),
        config=PipelineConfig(
            dry_run=args.dry_run,
            expense_account_id=args.expense_account_id,
            extractor_name=extractor_name,
            qbo_name=qbo_name,
            mail_name=mail_name,
        ),
    )
    print(
        f"messages={len(summary.records)} bills_created={summary.bills_created} "
        f"mail={summary.mail} extractor={summary.extractor} qbo={summary.qbo}"
    )
    errors = [record for record in summary.records if record.decision == "error"]
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
