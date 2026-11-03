"""Shared fixtures for the offline demo."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ap_pipeline.adapters.extract_rules import RulesExtractor
from ap_pipeline.adapters.mail_local import LocalFolderMailSource
from ap_pipeline.adapters.qbo_mock import MockQBOClient
from ap_pipeline.master_data import JobDirectory, VendorDirectory, load_open_jobs, load_vendors
from ap_pipeline.pipeline import PipelineConfig, run_pipeline
from ap_pipeline.runlog import RunLog
from ap_pipeline.state import StateStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


@pytest.fixture
def vendors() -> VendorDirectory:
    return VendorDirectory(load_vendors(FIXTURES / "vendors.json"))


@pytest.fixture
def jobs() -> JobDirectory:
    return JobDirectory(load_open_jobs(FIXTURES / "open_jobs.json"))


@pytest.fixture
def manifest() -> dict:
    return json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def copy_mail(tmp_path: Path) -> Path:
    destination = tmp_path / "mail"
    shutil.copytree(FIXTURES / "mail", destination)
    return destination


def run_demo(mail_root: Path, work: Path, *, qbo=None, dry_run: bool = False, vendors, jobs, name: str = "run"):
    client = qbo if qbo is not None else MockQBOClient()
    summary = run_pipeline(
        mail=LocalFolderMailSource(mail_root),
        extractor=RulesExtractor(),
        qbo=client,
        vendors=vendors,
        jobs=jobs,
        state=StateStore(work / f"{name}-state.json"),
        run_log=RunLog(work / f"{name}-logs"),
        config=PipelineConfig(dry_run=dry_run),
    )
    return summary, client
