"""Secure local storage for broker credentials.

Secrets are stored in the Windows Credential Manager through ``keyring``.  They
are never written to the project folder, settings JSON, database, or Git.
"""
from __future__ import annotations

import json


class BrokerCredentialStore:
    """Store separate encrypted credential profiles for supported brokers."""

    SERVICE_NAME = "TPS AI Trading Assistant"

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

    @staticmethod
    def _definition(broker_id):
        from services.broker_registry import broker_definition
        return broker_definition(broker_id)

    @staticmethod
    def _account_name(broker_id):
        return "angel-one-live-data" if broker_id == "angel_one" else f"broker-live-data-{broker_id}"

    def save(self, broker_id, values):
        definition = self._definition(broker_id)
        fields = tuple(key for key, _label, _secret in definition.fields)
        credentials = {field: str(values.get(field, "")).strip() for field in fields}
        from services.broker_registry import broker_credentials_complete
        if not broker_credentials_complete(broker_id, credentials):
            if broker_id == "paytm_money":
                raise ValueError("Enter API Key, API Secret and either a Request Token or a saved access token.")
            raise ValueError(f"Enter all {definition.name} credential fields before saving.")
        self._get_backend().set_password(self.SERVICE_NAME, self._account_name(broker_id), json.dumps(credentials))

    def load(self, broker_id):
        definition = self._definition(broker_id)
        fields = tuple(key for key, _label, _secret in definition.fields)
        saved = self._get_backend().get_password(self.SERVICE_NAME, self._account_name(broker_id))
        if not saved:
            return {}
        try:
            values = json.loads(saved)
        except (TypeError, json.JSONDecodeError):
            return {}
        return {field: str(values.get(field, "")) for field in fields}

    def clear(self, broker_id):
        try:
            self._get_backend().delete_password(self.SERVICE_NAME, self._account_name(broker_id))
        except Exception as error:
            # A missing entry is already the desired state; backends may differ.
            if error.__class__.__name__ != "PasswordDeleteError":
                raise


class AngelOneCredentialStore(BrokerCredentialStore):
    """Backward-compatible Angel One profile used by older code and tests."""

    def save(self, values):
        return super().save("angel_one", values)

    def load(self):
        return super().load("angel_one")

    def clear(self):
        return super().clear("angel_one")
