"""Interakt (WhatsApp BSP) API client.

Modeled on the Interakt REST API surface area that TapRebook would integrate with:
  * Send a pre-approved template to a phone number
  * Receive delivery/read/reply webhooks
  * Upload a CSV of patients and tag them as a cohort
  * List templates and their Meta approval status

This module ships in two modes:
  * `live`  — uses `urllib.request` to hit INTERAKT_API_BASE (real integration)
  * `mock`  — returns deterministic fake payloads (used by tests & local dev)

The mock mode is the default so the repo runs end-to-end without credentials.
Set INTERAKT_API_KEY in the env to enable live mode.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from taprebook.config import INTERAKT_API_BASE, INTERAKT_API_KEY


@dataclass
class TemplateSendResult:
    """Response from a template send call."""

    message_id: str
    status: str                   # 'accepted' | 'rejected' | 'queued'
    sent_at: str                  # ISO-8601
    raw: dict[str, Any] = field(default_factory=dict)


class InteraktClient:
    """Thin Interakt client with live + mock modes.

    The mock mode lets the repo run end-to-end in CI without a real API key,
    which is what most LLM-triage + BSP-integration demos need.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: str = INTERAKT_API_BASE,
        mock: Optional[bool] = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or INTERAKT_API_KEY
        self.api_base = api_base.rstrip("/")
        # Auto-select mock if no key is set
        self.mock = (not self.api_key) if mock is None else mock
        self.timeout = timeout

    # -----------------------------------------------------------------
    # HTTP plumbing (live mode)
    # -----------------------------------------------------------------
    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.api_base}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Basic {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Interakt API {e.code}: {body}") from e

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------
    def send_template(
        self,
        phone_e164: str,
        template_id: str,
        variables: list[str],
        buttons: Optional[list[dict[str, str]]] = None,
        callback_data: Optional[str] = None,
    ) -> TemplateSendResult:
        """Send a pre-approved WhatsApp template.

        `variables` is the ordered list of body variable values ({{1}}, {{2}}, …).
        `callback_data` round-trips back to us in the webhook so we can join
        the reply to the appointment that triggered it.
        """
        payload = {
            "countryCode": phone_e164[:3] if phone_e164.startswith("+") else "+91",
            "phoneNumber": phone_e164.lstrip("+"),
            "type":        "Template",
            "template": {
                "name":          template_id,
                "languageCode":  "en",
                "bodyValues":    variables,
                "buttonValues":  buttons or [],
            },
            "callbackData":  callback_data or f"appt:{uuid.uuid4()}",
        }

        if self.mock:
            return TemplateSendResult(
                message_id=f"mock_{uuid.uuid4().hex[:10]}",
                status="accepted",
                sent_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
                raw={"mock": True, "payload": payload},
            )

        resp = self._post("/public/message/", payload)
        return TemplateSendResult(
            message_id=resp.get("id", ""),
            status=resp.get("status", "unknown"),
            sent_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
            raw=resp,
        )

    def upload_patients(
        self, rows: list[dict[str, Any]], cohort_tag: str
    ) -> dict[str, Any]:
        """Bulk-upload a patient list and tag as a cohort."""
        payload = {"users": rows, "tags": [cohort_tag]}
        if self.mock:
            return {
                "mock":    True,
                "uploaded": len(rows),
                "tag":      cohort_tag,
            }
        return self._post("/public/track/users/", payload)

    # -----------------------------------------------------------------
    # Webhook parsing
    # -----------------------------------------------------------------
    @staticmethod
    def parse_webhook(payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize an inbound webhook into our internal event shape.

        Interakt sends separate webhook `type`s for sent/delivered/read/reply.
        We flatten them into the fields our template_sends + events tables need.
        """
        event_type_map = {
            "message_sent":      "wa_sent",
            "message_delivered": "wa_delivered",
            "message_read":      "wa_read",
            "message_replied":   "wa_reply",
        }
        wa_type = payload.get("type", "")
        return {
            "event_kind":    event_type_map.get(wa_type, wa_type),
            "message_id":    payload.get("messageId"),
            "phone_e164":    "+" + str(payload.get("phoneNumber", "")).lstrip("+"),
            "template_id":   payload.get("templateName"),
            "callback_data": payload.get("callbackData"),
            "reply_text":    payload.get("message", {}).get("body") if wa_type == "message_replied" else None,
            "received_at":   payload.get("timestamp") or datetime.utcnow().isoformat() + "Z",
        }
