from __future__ import annotations

import os

import requests


class VerifyError(RuntimeError):
    pass


def _credentials() -> tuple[str, str, str]:
    sid = str(os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
    token = str(os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
    service = str(os.getenv("TWILIO_VERIFY_SERVICE_SID") or "").strip()
    return sid, token, service


def is_configured() -> bool:
    return all(_credentials())


def _post(path: str, data: dict[str, str]) -> dict:
    sid, token, service = _credentials()
    if not (sid and token and service):
        raise VerifyError("Member login is not configured yet.")
    response = requests.post(
        f"https://verify.twilio.com/v2/Services/{service}/{path}",
        data=data,
        auth=(sid, token),
        timeout=20,
    )
    try:
        body = response.json()
    except Exception:
        body = {}
    if response.status_code >= 400:
        raise VerifyError(str(body.get("message") or f"Verification service returned HTTP {response.status_code}."))
    return body


def start(phone: str, channel: str) -> None:
    _post("Verifications", {"To": phone, "Channel": channel})


def check(phone: str, code: str) -> bool:
    body = _post("VerificationCheck", {"To": phone, "Code": code})
    return str(body.get("status")) == "approved"
