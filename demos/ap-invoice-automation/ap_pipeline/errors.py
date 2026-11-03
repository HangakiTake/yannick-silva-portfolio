"""Errors that callers can distinguish from bugs in the pipeline."""


class PipelineError(Exception):
    """A controlled failure: missing credentials, a refused host, or a bad response."""


class CredentialsNotConfigured(PipelineError):
    """A live adapter was selected but its credentials are not in the environment."""


class ProductionGuardError(PipelineError):
    """The QuickBooks host is production and QBO_ALLOW_PRODUCTION is not set."""
