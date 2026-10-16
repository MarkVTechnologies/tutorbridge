"""
Payment gateway adapters (PAY-01). Paystack is primary; Flutterwave is a
switchable fallback (admin setting `active_gateway`). The "fake" gateway is
for local development and the public demo only; refused unless DEBUG or DEMO_MODE is on.

Each adapter exposes the same interface and normalises webhooks to:
    {"event": "charge.success" | "transfer.success" | "transfer.failed", "reference": str, "id": str}
"""
import hashlib
import hmac
import json
from dataclasses import dataclass

import requests
from django.conf import settings

from core import config


class GatewayError(Exception):
    pass


class InvalidPayload(GatewayError):
    """The webhook body itself is malformed (permanent: retrying won't help)."""


@dataclass
class SavedCardInfo:
    """A reusable card token returned by the gateway after a successful card payment. Never a card number."""

    authorization_code: str
    signature: str
    brand: str
    last4: str
    exp_month: str
    exp_year: str
    email: str


@dataclass
class Verification:
    status: str  # success | failed | pending
    amount_kobo: int
    currency: str
    fee_kobo: int = 0
    channel: str = ""
    raw: dict = None


class Paystack:
    name = "paystack"
    base = "https://api.paystack.co"

    def _h(self):
        return {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"}

    def _req(self, method, path, **kw):
        resp = requests.request(method, self.base + path, headers=self._h(), timeout=30, **kw)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or not data.get("status"):
            raise GatewayError(data.get("message") or f"Paystack HTTP {resp.status_code}")
        return data["data"]

    def initialize(self, *, email, amount_kobo, reference, callback_url, metadata=None):
        data = self._req("POST", "/transaction/initialize", json={
            "email": email, "amount": amount_kobo, "reference": reference, "callback_url": callback_url,
            "currency": "NGN", "metadata": metadata or {}, "channels": ["card", "bank", "ussd", "bank_transfer"],
        })
        return data["authorization_url"]

    def verify(self, reference):
        d = self._req("GET", f"/transaction/verify/{reference}")
        status = {"success": "success", "failed": "failed", "abandoned": "failed", "reversed": "failed"}.get(d.get("status"), "pending")
        return Verification(status, int(d.get("amount", 0)), d.get("currency", ""), int(d.get("fees") or 0), d.get("channel", ""), d)

    def check_signature(self, raw_body: bytes, headers) -> bool:
        sig = headers.get("X-Paystack-Signature", "")
        expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), raw_body, hashlib.sha512).hexdigest()
        return bool(sig) and hmac.compare_digest(sig, expected)

    def normalise_webhook(self, payload):
        event, data = payload.get("event", ""), payload.get("data", {})
        mapped = {"charge.success": "charge.success", "transfer.success": "transfer.success",
                  "transfer.failed": "transfer.failed", "transfer.reversed": "transfer.failed"}.get(event, event)
        return {"event": mapped, "reference": data.get("reference", ""), "id": str(data.get("id", ""))}

    def list_banks(self):
        return [{"name": b["name"], "code": b["code"]} for b in self._req("GET", "/bank?country=nigeria&perPage=100")]

    def resolve_account(self, account_number, bank_code):
        return self._req("GET", f"/bank/resolve?account_number={account_number}&bank_code={bank_code}")["account_name"]

    def create_recipient(self, *, name, account_number, bank_code):
        d = self._req("POST", "/transferrecipient", json={
            "type": "nuban", "name": name, "account_number": account_number, "bank_code": bank_code, "currency": "NGN"})
        return d["recipient_code"]

    def transfer(self, *, amount_kobo, recipient_code, account_number, bank_code, reference, reason):
        d = self._req("POST", "/transfer", json={
            "source": "balance", "amount": amount_kobo, "recipient": recipient_code, "reference": reference, "reason": reason})
        return d.get("status", "pending")

    def verify_transfer(self, reference):
        return self._req("GET", f"/transfer/verify/{reference}").get("status", "pending")

    def saved_card(self, raw):
        auth = (raw or {}).get("authorization") or {}
        if not auth.get("reusable") or auth.get("channel") != "card" or not auth.get("authorization_code"):
            return None
        return SavedCardInfo(auth["authorization_code"], auth.get("signature", ""), (auth.get("card_type") or auth.get("brand") or "").strip().title(),
                             auth.get("last4", ""), str(auth.get("exp_month", "")), str(auth.get("exp_year", "")),
                             ((raw or {}).get("customer") or {}).get("email", ""))

    def charge_authorization(self, *, email, amount_kobo, authorization_code, reference, metadata=None):
        d = self._req("POST", "/transaction/charge_authorization", json={
            "email": email, "amount": amount_kobo, "authorization_code": authorization_code, "reference": reference,
            "currency": "NGN", "metadata": metadata or {}})
        return {"success": "success", "failed": "failed"}.get(d.get("status"), "pending")


class Flutterwave:
    name = "flutterwave"
    base = "https://api.flutterwave.com/v3"

    def _h(self):
        return {"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}", "Content-Type": "application/json"}

    def _req(self, method, path, **kw):
        resp = requests.request(method, self.base + path, headers=self._h(), timeout=30, **kw)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or data.get("status") != "success":
            raise GatewayError(data.get("message") or f"Flutterwave HTTP {resp.status_code}")
        return data["data"]

    def initialize(self, *, email, amount_kobo, reference, callback_url, metadata=None):
        data = self._req("POST", "/payments", json={
            "tx_ref": reference, "amount": amount_kobo / 100, "currency": "NGN", "redirect_url": callback_url,
            "customer": {"email": email}, "meta": metadata or {}, "payment_options": "card,banktransfer,ussd",
        })
        return data["link"]

    def verify(self, reference):
        d = self._req("GET", f"/transactions/verify_by_reference?tx_ref={reference}")
        status = {"successful": "success", "failed": "failed"}.get(d.get("status"), "pending")
        return Verification(status, round(float(d.get("amount", 0)) * 100), d.get("currency", ""),
                            round(float(d.get("app_fee") or 0) * 100), d.get("payment_type", ""), d)

    def check_signature(self, raw_body: bytes, headers) -> bool:
        sig = headers.get("Verif-Hash", "")
        return bool(sig) and bool(settings.FLUTTERWAVE_WEBHOOK_HASH) and hmac.compare_digest(sig, settings.FLUTTERWAVE_WEBHOOK_HASH)

    def normalise_webhook(self, payload):
        data = payload.get("data", {})
        event = payload.get("event", "")
        if event == "charge.completed":
            return {"event": "charge.success" if data.get("status") == "successful" else "charge.failed",
                    "reference": data.get("tx_ref", ""), "id": str(data.get("id", ""))}
        if event == "transfer.completed":
            return {"event": "transfer.success" if data.get("status") == "SUCCESSFUL" else "transfer.failed",
                    "reference": data.get("reference", ""), "id": str(data.get("id", ""))}
        return {"event": event, "reference": data.get("reference", ""), "id": str(data.get("id", ""))}

    def list_banks(self):
        return [{"name": b["name"], "code": b["code"]} for b in self._req("GET", "/banks/NG")]

    def resolve_account(self, account_number, bank_code):
        return self._req("POST", "/accounts/resolve", json={"account_number": account_number, "account_bank": bank_code})["account_name"]

    def create_recipient(self, *, name, account_number, bank_code):
        return ""  # Flutterwave transfers take account details directly

    def transfer(self, *, amount_kobo, recipient_code, account_number, bank_code, reference, reason):
        d = self._req("POST", "/transfers", json={
            "account_bank": bank_code, "account_number": account_number, "amount": amount_kobo / 100,
            "currency": "NGN", "reference": reference, "narration": reason})
        return d.get("status", "NEW").lower()

    def verify_transfer(self, reference):
        d = self._req("GET", f"/transfers?reference={reference}")
        return (d[0]["status"].lower() if d else "pending")

    def saved_card(self, raw):
        card = (raw or {}).get("card") or {}
        if not card.get("token"):
            return None
        month, _, year = str(card.get("expiry", "")).partition("/")
        return SavedCardInfo(card["token"], f"{card.get('first_6digits', '')}{card.get('last_4digits', '')}{card.get('expiry', '')}",
                             (card.get("type") or "").title(), card.get("last_4digits", ""), month, year,
                             ((raw or {}).get("customer") or {}).get("email", ""))

    def charge_authorization(self, *, email, amount_kobo, authorization_code, reference, metadata=None):
        d = self._req("POST", "/tokenized-charges", json={
            "token": authorization_code, "email": email, "amount": amount_kobo / 100, "currency": "NGN", "tx_ref": reference, "meta": metadata or {}})
        return {"successful": "success", "failed": "failed"}.get(d.get("status"), "pending")


class FakeGateway:
    """Local development only: simulates checkout, verification and transfers."""

    name = "fake"

    def __init__(self):
        if not (settings.DEBUG or settings.DEMO_MODE):
            raise GatewayError("Fake gateway is disabled outside DEBUG/DEMO_MODE")

    def initialize(self, *, email, amount_kobo, reference, callback_url, metadata=None):
        return f"{settings.SITE_URL}/dev/fake-checkout?reference={reference}&amount={amount_kobo}"

    def verify(self, reference):
        from payments.models import Payment

        p = Payment.objects.filter(reference=reference).first()
        paid = bool(p and (p.raw_verification or {}).get("fake_paid"))
        return Verification("success" if paid else "pending", p.amount_kobo if p else 0, "NGN", 0, "card", {"fake": True})

    def check_signature(self, raw_body, headers):
        expected = hmac.new(settings.SECRET_KEY.encode(), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(headers.get("X-Fake-Signature", ""), expected)

    @staticmethod
    def sign(body: bytes):
        return hmac.new(settings.SECRET_KEY.encode(), body, hashlib.sha512).hexdigest()

    def normalise_webhook(self, payload):
        return {"event": payload.get("event"), "reference": payload.get("reference", ""), "id": payload.get("id", "")}

    def list_banks(self):
        return [{"name": "Access Bank", "code": "044"}, {"name": "GTBank", "code": "058"}, {"name": "First Bank", "code": "011"},
                {"name": "Zenith Bank", "code": "057"}, {"name": "UBA", "code": "033"}, {"name": "Opay", "code": "999992"}]

    def resolve_account(self, account_number, bank_code):
        # Account numbers ending in 0000 simulate a name mismatch; others echo the expected holder (see add_bank_account).
        return "TEST ACCOUNT" if account_number.endswith("0000") else None

    def create_recipient(self, *, name, account_number, bank_code):
        return f"RCP_fake_{account_number[-4:]}"

    def transfer(self, *, amount_kobo, recipient_code, account_number, bank_code, reference, reason):
        return "pending"

    def verify_transfer(self, reference):
        return "success"

    def saved_card(self, raw):
        if not (raw or {}).get("fake"):
            return None
        return SavedCardInfo("AUTH_fake", "SIG_fake_4081", "Visa", "4081", "12", "2030", "")

    def charge_authorization(self, *, email, amount_kobo, authorization_code, reference, metadata=None):
        from payments.models import Payment

        # Cards whose token ends in "_declined" simulate a decline.
        if authorization_code.endswith("_declined"):
            return "failed"
        p = Payment.objects.get(reference=reference)
        p.raw_verification = {**(p.raw_verification or {}), "fake_paid": True}
        p.save(update_fields=["raw_verification"])
        return "success"


GATEWAYS = {"paystack": Paystack, "flutterwave": Flutterwave, "fake": FakeGateway}


def get_gateway(name=None):
    name = name or (settings.PAYMENT_GATEWAY if settings.PAYMENT_GATEWAY == "fake" else config.get("active_gateway"))
    if name not in GATEWAYS:
        raise GatewayError(f"Unknown gateway {name}")
    return GATEWAYS[name]()


def parse_json(raw_body):
    try:
        return json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise InvalidPayload("Invalid JSON body") from e
