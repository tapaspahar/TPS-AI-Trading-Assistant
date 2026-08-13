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
    setup_url: str = ""
    login_summary: str = ""


BROKERS = {
    "angel_one": BrokerDefinition(
        "angel_one", "Angel One", (
            ("api_key", "API Key", True), ("client_code", "Client Code", False),
            ("mpin", "MPIN", True), ("totp_secret", "TOTP Secret", True),
        ), True, "https://smartapi.angelone.in/",
        "One-time setup: SmartAPI key + Client Code + MPIN + TOTP secret. After secure save, TPS auto-connects on startup.",
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
        "dhan", "Dhan", (
            ("client_id", "Client ID", False), ("pin", "Dhan PIN", True),
            ("totp_secret", "TOTP Secret", True),
        ), True, "https://web.dhan.co/",
        "One-time setup: Dhan Client ID + PIN + TOTP secret. Dhan then issues the required 24-hour API session automatically.",
    ),
    "paytm_money": BrokerDefinition(
        "paytm_money", "Paytm Money", (
            ("api_key", "API Key", True), ("api_secret", "API Secret", True),
            ("request_token", "Request Token (first login)", True),
            ("access_token", "Access Token (auto-saved)", True),
            ("read_access_token", "Read Access Token (auto-saved)", True),
            ("public_access_token", "Public Access Token (auto-saved)", True),
        ), True, "https://developer.paytmmoney.com/",
        "One-time developer-app authorization is required. TPS stores returned session tokens securely and reuses them until expiry.",
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


def broker_credentials_complete(broker_id: str, credentials: dict) -> bool:
    """Return whether a saved profile can connect without asking the user."""
    if broker_id == "paytm_money":
        base = all(str(credentials.get(key, "")).strip() for key in ("api_key", "api_secret"))
        authorization = any(str(credentials.get(key, "")).strip() for key in (
            "request_token", "access_token", "read_access_token",
        ))
        return base and authorization
    definition = broker_definition(broker_id)
    return all(str(credentials.get(field, "")).strip() for field, _label, _secret in definition.fields)


def create_broker_client(broker_id: str, credentials: dict):
    definition = broker_definition(broker_id)
    required_fields = definition.fields
    if broker_id == "paytm_money":
        required_fields = definition.fields[:2]
    missing = [label for key, label, _secret in required_fields if not str(credentials.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Enter {', '.join(missing)}.")
    if broker_id == "angel_one":
        from services.angel_one_client import AngelOneClient

        return AngelOneClient(
            credentials["api_key"], credentials["client_code"],
            credentials["mpin"], credentials["totp_secret"],
        )
    if broker_id == "dhan":
        from services.dhan_client import DhanClient

        return DhanClient(credentials["client_id"], credentials["pin"], credentials["totp_secret"])
    if broker_id == "paytm_money":
        from services.paytm_money_client import PaytmMoneyClient

        if not any(str(credentials.get(key, "")).strip() for key in ("request_token", "access_token", "read_access_token")):
            raise ValueError("Open Paytm Login and paste the Request Token before connecting.")
        return PaytmMoneyClient(
            credentials["api_key"], credentials["api_secret"], credentials.get("request_token", ""),
            credentials.get("access_token", ""), credentials.get("read_access_token", ""),
            credentials.get("public_access_token", ""),
        )
    raise RuntimeError(
        f"{definition.name} credentials can be stored securely, but its TPS market-data adapter is not installed yet. "
        "Each broker uses different instrument tokens, login, candle, quote, option-chain and websocket APIs."
    )
