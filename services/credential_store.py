"""Secure local storage for broker credentials.

Secrets are stored in the Windows Credential Manager through ``keyring``.  They
are never written to the project folder, settings JSON, database, or Git.
"""
from __future__ import annotations

import json


class AngelOneCredentialStore:
    """Store one user's Angel One read-only connection details securely."""

    SERVICE_NAME = "TPS AI Trading Assistant"
    ACCOUNT_NAME = "angel-one-live-data"
    FIELDS = ("api_key", "client_code", "mpin", "totp_secret")

    def __init__(self, backend=None):
        self._backend = backend

    def _get_backend(self):
        if self._backend is not None:
            return self._backend
        try:
            import keyring
        except ImportError as error:
            raise RuntimeError("Secure credential saving is unavailable. Install the project requirements first.") from error
        return keyring

    def save(self, values):
        credentials = {field: str(values.get(field, "")).strip() for field in self.FIELDS}
        if not all(credentials.values()):
            raise ValueError("Enter API Key, Client Code, MPIN, and TOTP secret before saving credentials.")
        self._get_backend().set_password(self.SERVICE_NAME, self.ACCOUNT_NAME, json.dumps(credentials))

    def load(self):
        saved = self._get_backend().get_password(self.SERVICE_NAME, self.ACCOUNT_NAME)
        if not saved:
            return {}
        try:
            values = json.loads(saved)
        except (TypeError, json.JSONDecodeError):
            return {}
        return {field: str(values.get(field, "")) for field in self.FIELDS}

    def clear(self):
        try:
            self._get_backend().delete_password(self.SERVICE_NAME, self.ACCOUNT_NAME)
        except Exception as error:
            # A missing entry is already the desired state; backends may differ.
            if error.__class__.__name__ != "PasswordDeleteError":
                raise
