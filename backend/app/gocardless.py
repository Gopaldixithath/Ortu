from __future__ import annotations

import os
from typing import Any

import requests


class GoCardlessError(RuntimeError):
    pass


def _base_url() -> str:
    environment = str(os.getenv("GOCARDLESS_ENVIRONMENT") or "sandbox").strip().lower()
    return "https://api.gocardless.com" if environment == "live" else "https://api-sandbox.gocardless.com"


def is_configured() -> bool:
    return bool(str(os.getenv("GOCARDLESS_ACCESS_TOKEN") or "").strip())


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    token = str(os.getenv("GOCARDLESS_ACCESS_TOKEN") or "").strip()
    if not token:
        raise GoCardlessError("GoCardless checkout is not configured yet.")
    response = requests.request(
        method,
        f"{_base_url()}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "GoCardless-Version": "2015-07-06",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )
    if response.status_code >= 400:
        try:
            error = response.json().get("error", {})
            detail = error.get("message")
            field_errors = "; ".join(
                f"{item.get('field') or item.get('request_pointer') or 'request'}: {item['message']}"
                for item in (error.get("errors") or [])
                if item.get("message")
            )
            if field_errors:
                detail = f"{detail or 'Validation failed'} — {field_errors}"
        except Exception:
            detail = None
        raise GoCardlessError(detail or f"GoCardless returned HTTP {response.status_code}.")
    return response.json()


def create_mandate_checkout(*, first_name: str, last_name: str, email: str, redirect_uri: str, exit_uri: str) -> dict[str, str]:
    request_doc = _request("POST", "/billing_requests", {"billing_requests": {"mandate_request": {"scheme": "bacs"}}})
    request_id = str(request_doc["billing_requests"]["id"])
    flow_doc = _request(
        "POST",
        "/billing_request_flows",
        {
            "billing_request_flows": {
                "redirect_uri": redirect_uri,
                "exit_uri": exit_uri,
                "prefilled_customer": {"given_name": first_name, "family_name": last_name, "email": email},
                "links": {"billing_request": request_id},
            }
        },
    )
    flow = flow_doc["billing_request_flows"]
    return {"billing_request_id": request_id, "billing_flow_id": str(flow["id"]), "authorisation_url": str(flow["authorisation_url"])}


def fulfil_membership(*, billing_request_id: str, amount_pence: int, plan_name: str, billing_kind: str) -> dict[str, str]:
    request_doc = _request("GET", f"/billing_requests/{billing_request_id}")
    request_value = request_doc["billing_requests"]
    if request_value.get("status") != "fulfilled":
        raise GoCardlessError("The Direct Debit authorisation has not completed.")
    mandate_id = str((request_value.get("mandate_request") or {}).get("links", {}).get("mandate") or "")
    if not mandate_id:
        raise GoCardlessError("GoCardless did not return a mandate.")
    common = {"amount": int(amount_pence), "currency": "GBP", "links": {"mandate": mandate_id}}
    if billing_kind == "recurring":
        doc = _request("POST", "/subscriptions", {"subscriptions": {**common, "name": plan_name, "interval_unit": "monthly", "retry_if_possible": True}})
        return {"mandate_id": mandate_id, "subscription_id": str(doc["subscriptions"]["id"])}
    doc = _request("POST", "/payments", {"payments": {**common, "description": plan_name}})
    return {"mandate_id": mandate_id, "payment_id": str(doc["payments"]["id"])}
