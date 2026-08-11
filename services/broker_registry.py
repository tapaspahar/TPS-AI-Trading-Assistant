"""Broker profiles and read-only market-data adapter factory.

Credentials are not interchangeable between brokers. A broker becomes usable
only after its adapter implements TPS's common candle, quote and option-chain
contract.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerDefinition:
    broker_id: str
    name: str
    fields: tuple[tuple[str, str, bool], ...]
    adapter_available: bool = False


BROKERS = {
    "angel_one": BrokerDefinition(
        "angel_one", "Angel One", (
            ("api_key", "API Key", True), ("client_code", "Client Code", False),
            ("mpin", "MPIN", True), ("totp_secret", "TOTP Secret", True),
        ), True,
    ),
    "zerodha": BrokerDefinition(
        "zerodha", "Zerodha Kite", (
            ("api_key", "API Key", True), ("api_secret", "API Secret", True),
            ("request_token", "Request Token", True),
        ),
    ),
    "upstox": BrokerDefinition(
        "upstox", "Upstox", (
            ("api_key", "API Key", True), ("api_secret", "API Secret", True),
            ("access_token", "Access Token", True),
        ),
    ),
    "dhan": BrokerDefinition(
        "dhan", "Dhan", (("client_id", "Client ID", False), ("access_token", "Access Token", True)),
    ),
    "fyers": BrokerDefinition(
        "fyers", "Fyers", (
            ("client_id", "Client ID", False), ("secret_key", "Secret Key", True),
            ("access_token", "Access Token", True),
        ),
    ),
    "shoonya": BrokerDefinition(
        "shoonya", "Shoonya", (
            ("user_id", "User ID", False), ("password", "Password", True),
            ("vendor_code", "Vendor Code", False), ("api_secret", "API Secret", True),
            ("imei", "IMEI", False), ("totp_secret", "TOTP Secret", True),
        ),
    ),
    "other": BrokerDefinition(
        "other", "Other API Broker", (
            ("broker_name", "Broker Name", False), ("api_key", "API Key", True),
            ("client_id", "Client / User ID", False), ("api_secret", "API Secret", True),
            ("access_token", "Access Token", True),
        ),
    ),
}


def broker_definition(broker_id: str) -> BrokerDefinition:
    return BROKERS.get(str(broker_id).lower(), BROKERS["angel_one"])


def create_broker_client(broker_id: str, credentials: dict):
    definition = broker_definition(broker_id)
    missing = [label for key, label, _secret in definition.fields if not str(credentials.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Enter {', '.join(missing)}.")
    if broker_id == "angel_one":
        from services.angel_one_client import AngelOneClient

        return AngelOneClient(
            credentials["api_key"], credentials["client_code"],
            credentials["mpin"], credentials["totp_secret"],
        )
    raise RuntimeError(
        f"{definition.name} credentials can be stored securely, but its TPS market-data adapter is not installed yet. "
        "Each broker uses different instrument tokens, login, candle, quote, option-chain and websocket APIs."
    )
