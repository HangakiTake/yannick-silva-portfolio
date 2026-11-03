"""Accounts-payable invoice pipeline.

The tested path uses a local mail folder, a rules extractor, and an in-memory
QuickBooks client. Microsoft Graph, QuickBooks Online REST, and LLM extractors
are implemented but not exercised against live services.
"""

__version__ = "0.1.0"
