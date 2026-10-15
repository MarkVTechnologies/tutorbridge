"""Gateway adapters, webhook edge cases, reconciliation, payouts and bank accounts."""
import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

import pyotp
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import OTPCode, Role
from bookings.models import EscrowStatus
from core import config
from messaging.models import Notification
from payments import ledger, services
from payments.gateways import Flutterwave, GatewayError, Paystack
from payments.models import AccountKind, BankAccount, Payment, Payout, PayoutItem, ReconciliationRun, WebhookEvent
from tests.factories import deliver, fund_wallet, make_active_booking, make_parent, make_staff, make_tutor, seed, staff_client
from vetting.models import CheckStatus, CheckType, VerificationCheck


def http(status=200, body=None):
    r = mock.Mock()
    r.status_code = status
    r.content = b"x"
    r.json.return_value = body or {}
    return r


@override_settings(PAYSTACK_SECRET_KEY="sk_test_123")
class PaystackAdapterTests(TestCase):
    def test_initialize_sends_kobo_and_returns_url(self):
        with mock.patch("payments.gateways.requests.request", return_value=http(200, {"status": True, "data": {"authorization_url": "https://checkout.paystack.com/x"}})) as req:
            url = Paystack().initialize(email="a@b.c", amount_kobo=1_000_000, reference="TB_1", callback_url="https://x/cb")
        self.assertEqual(url, "https://checkout.paystack.com/x")
        body = req.call_args.kwargs["json"]
        self.assertEqual(body["amount"], 1_000_000)
        self.assertEqual(body["currency"], "NGN")
        self.assertEqual(req.call_args.kwargs["headers"]["Authorization"], "Bearer sk_test_123")

    def test_verify_maps_status_and_fees(self):
        data = {"status": True, "data": {"status": "success", "amount": 500_000, "currency": "NGN", "fees": 7_500, "channel": "card"}}
        with mock.patch("payments.gateways.requests.request", return_value=http(200, data)):
            v = Paystack().verify("TB_1")
        self.assertEqual((v.status, v.amount_kobo, v.fee_kobo, v.channel), ("success", 500_000, 7_500, "card"))
        with mock.patch("payments.gateways.requests.request", return_value=http(200, {"status": True, "data": {"status": "abandoned"}})):
            self.assertEqual(Paystack().verify("TB_2").status, "failed")
        with mock.patch("payments.gateways.requests.request", return_value=http(200, {"status": True, "data": {"status": "ongoing"}})):
            self.assertEqual(Paystack().verify("TB_3").status, "pending")

    def test_http_error_raises_gateway_error(self):
        with mock.patch("payments.gateways.requests.request", return_value=http(400, {"status": False, "message": "Invalid key"})):
            with self.assertRaisesMessage(GatewayError, "Invalid key"):
                Paystack().verify("x")

    def test_bank_resolve_recipient_and_transfer(self):
        p = Paystack()
        with mock.patch("payments.gateways.requests.request", return_value=http(200, {"status": True, "data": {"account_name": "NGOZI OKAFOR"}})):
            self.assertEqual(p.resolve_account("0123456789", "058"), "NGOZI OKAFOR")
        with mock.patch("payments.gateways.requests.request", return_value=http(200, {"status": True, "data": {"recipient_code": "RCP_1"}})):
            self.assertEqual(p.create_recipient(name="N", account_number="0123456789", bank_code="058"), "RCP_1")
        with mock.patch("payments.gateways.requests.request", return_value=http(200, {"status": True, "data": {"status": "pending"}})) as req:
            self.assertEqual(p.transfer(amount_kobo=100, recipient_code="RCP_1", account_number="", bank_code="058", reference="PO_1", reason="x"), "pending")
        self.assertEqual(req.call_args.kwargs["json"]["source"], "balance")
        with mock.patch("payments.gateways.requests.request", return_value=http(200, {"status": True, "data": [{"name": "GTBank", "code": "058", "id": 1}]})):
            self.assertEqual(p.list_banks(), [{"name": "GTBank", "code": "058"}])

    def test_webhook_normalisation(self):
        p = Paystack()
        self.assertEqual(p.normalise_webhook({"event": "transfer.reversed", "data": {"reference": "PO_1", "id": 9}}), {"event": "transfer.failed", "reference": "PO_1", "id": "9"})
        self.assertEqual(p.normalise_webhook({"event": "charge.success", "data": {"reference": "TB_1", "id": 1}})["event"], "charge.success")


@override_settings(FLUTTERWAVE_SECRET_KEY="FLWSECK_TEST", FLUTTERWAVE_WEBHOOK_HASH="hash123")
class FlutterwaveAdapterTests(TestCase):
    def test_initialize_uses_naira(self):
        with mock.patch("payments.gateways.requests.request", return_value=http(200, {"status": "success", "data": {"link": "https://flw/x"}})) as req:
            self.assertEqual(Flutterwave().initialize(email="a@b.c", amount_kobo=1_050_050, reference="TB_1", callback_url="https://x"), "https://flw/x")
        self.assertEqual(req.call_args.kwargs["json"]["amount"], 10_500.50)

    def test_verify_converts_to_kobo(self):
        data = {"status": "success", "data": {"status": "successful", "amount": 9000.5, "currency": "NGN", "app_fee": 126.01, "payment_type": "card"}}
        with mock.patch("payments.gateways.requests.request", return_value=http(200, data)):
            v = Flutterwave().verify("TB_1")
        self.assertEqual((v.status, v.amount_kobo, v.fee_kobo), ("success", 900_050, 12_601))

    def test_signature_and_events(self):
        f = Flutterwave()
        self.assertTrue(f.check_signature(b"{}", {"Verif-Hash": "hash123"}))
        self.assertFalse(f.check_signature(b"{}", {"Verif-Hash": "nope"}))
        self.assertEqual(f.normalise_webhook({"event": "charge.completed", "data": {"status": "successful", "tx_ref": "TB_1", "id": 3}})["event"], "charge.success")
        self.assertEqual(f.normalise_webhook({"event": "charge.completed", "data": {"status": "failed", "tx_ref": "TB_1"}})["event"], "charge.failed")
        self.assertEqual(f.normalise_webhook({"event": "transfer.completed", "data": {"status": "FAILED", "reference": "PO_1"}})["event"], "transfer.failed")
        self.assertEqual(f.normalise_webhook({"event": "transfer.completed", "data": {"status": "SUCCESSFUL", "reference": "PO_1"}})["event"], "transfer.success")


@override_settings(PAYSTACK_SECRET_KEY="sk_test_123")
class PaystackWebhookTests(TestCase):
    """The real production path: Paystack-signed webhook + server-side verify."""

    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, _ = make_parent()
        self.payment = Payment.objects.create(parent=self.parent, gateway="paystack", reference="TB_test_1", amount_kobo=900_000)

    def _post(self, payload, sign=True):
        body = json.dumps(payload).encode()
        sig = hmac.new(b"sk_test_123", body, hashlib.sha512).hexdigest() if sign else "bad"
        return self.client.post("/api/payments/webhooks/paystack/", body, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=sig)

    def _verify(self, **data):
        base = {"status": "success", "amount": 900_000, "currency": "NGN", "fees": 13_500, "channel": "card"}
        return mock.patch("payments.gateways.requests.request", return_value=http(200, {"status": True, "data": {**base, **data}}))

    def test_signed_webhook_credits_wallet_and_records_fee(self):
        with self._verify():
            r = self._post({"event": "charge.success", "data": {"reference": "TB_test_1", "id": 1}})
        self.assertEqual(r.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCESS)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 900_000)
        self.assertEqual(ledger.balance(ledger.platform(AccountKind.GATEWAY_FEES)), 13_500)
        self.assertTrue(Notification.objects.filter(user=self.parent.user, event="payment_received").exists())

    def test_amount_mismatch_is_not_credited_and_alerts_finance(self):
        fin = make_staff(Role.FINANCE)
        with self._verify(amount=100):
            self._post({"event": "charge.success", "data": {"reference": "TB_test_1", "id": 1}})
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.INITIATED)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 0)
        self.assertTrue(Notification.objects.filter(user=fin, event="finance_alert").exists())

    def test_wrong_currency_is_not_credited(self):
        with self._verify(currency="USD"):
            self._post({"event": "charge.success", "data": {"reference": "TB_test_1", "id": 1}})
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 0)

    def test_failed_verification_marks_failed(self):
        with self._verify(status="failed"):
            self._post({"event": "charge.success", "data": {"reference": "TB_test_1", "id": 1}})
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.FAILED)

    def test_bad_signature_stored_but_ignored(self):
        r = self._post({"event": "charge.success", "data": {"reference": "TB_test_1", "id": 1}}, sign=False)
        self.assertEqual(r.status_code, 401)
        self.assertTrue(WebhookEvent.objects.filter(signature_valid=False).exists())

    def test_invalid_json_rejected(self):
        r = self.client.post("/api/payments/webhooks/paystack/", b"not json", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_gateway_error_during_processing_returns_500_for_retry(self):
        with mock.patch("payments.gateways.requests.request", return_value=http(500, {"status": False, "message": "down"})):
            r = self._post({"event": "charge.success", "data": {"reference": "TB_test_1", "id": 1}})
        self.assertEqual(r.status_code, 500)
        ev = WebhookEvent.objects.get()
        self.assertIsNone(ev.processed_at)
        self.assertIn("down", ev.error)
        # Gateway retries later and succeeds.
        with self._verify():
            self.assertEqual(self._post({"event": "charge.success", "data": {"reference": "TB_test_1", "id": 1}}).status_code, 200)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 900_000)

    def test_unknown_gateway_404(self):
        self.assertEqual(self.client.post("/api/payments/webhooks/nope/", b"{}", content_type="application/json").status_code, 404)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get("/api/payments/webhooks/paystack/").status_code, 405)


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class ReconciliationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, _ = make_parent()

    def test_missed_webhook_recovered(self):
        p = Payment.objects.create(parent=self.parent, gateway="fake", reference="TB_missed", amount_kobo=500_000, raw_verification={"fake_paid": True})
        Payment.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(hours=1))
        run = services.reconcile()
        p.refresh_from_db()
        self.assertEqual(p.status, Payment.Status.SUCCESS)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 500_000)
        self.assertIn("missed webhook", run.mismatches[0]["issue"])

    def test_stale_unpaid_marked_abandoned(self):
        p = Payment.objects.create(parent=self.parent, gateway="fake", reference="TB_old", amount_kobo=500_000)
        Payment.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(days=2))
        services.reconcile()
        p.refresh_from_db()
        self.assertEqual(p.status, Payment.Status.ABANDONED)

    def test_success_without_ledger_entry_flagged(self):
        fin = make_staff(Role.FINANCE)
        Payment.objects.create(parent=self.parent, gateway="fake", reference="TB_ghost", amount_kobo=1, status=Payment.Status.SUCCESS)
        run = services.reconcile()
        self.assertEqual(run.mismatches[0]["issue"], "success without ledger entry")
        self.assertTrue(Notification.objects.filter(user=fin, event="finance_alert").exists())

    def test_clean_run(self):
        run = services.reconcile()
        self.assertEqual(run.mismatches, [])
        self.assertEqual(ReconciliationRun.objects.count(), 1)


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class PayoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        config.set_value("payout_min_kobo", 100_000)
        config.set_value("vetting_fee_deduct_from_earnings", False)
        self.parent, self.child = make_parent()
        self.tutor = make_tutor(rate_kobo=600_000)
        self.booking = make_active_booking(self.parent, self.child, self.tutor)
        from bookings import services as bs

        for lesson in list(self.booking.lessons.all()[:2]):
            bs.confirm_lesson(deliver(lesson, self.tutor))
        self.bank = BankAccount.objects.create(tutor=self.tutor, bank_code="058", bank_name="GTBank", account_number="0123456789", account_last4="6789",
                                               account_name="X", name_match=True, verified_at=timezone.now(), recipient_code="RCP_1")
        self.fin1, self.fin2 = make_staff(Role.FINANCE), make_staff(Role.FINANCE)

    def _approve(self, payout):
        return staff_client(APIClient(), self.fin2).post(f"/api/staff/payouts/{payout.pk}/approve/", {"totp": pyotp.TOTP(self.fin2.totp_secret).now()}, format="json")

    def test_failed_transfer_returns_funds_and_retry_resends(self):
        payout = services.create_payout_batch(self.fin1)
        self.assertEqual(payout.total_kobo, 960_000)
        self.assertEqual(self._approve(payout).status_code, 200)
        item = payout.items.get()
        self.assertEqual(self.booking.lessons.filter(escrow_status=EscrowStatus.PAID_OUT).count(), 2)
        services.settle_transfer(item, success=False)
        item.refresh_from_db()
        self.assertEqual(item.status, PayoutItem.Status.FAILED)
        self.assertEqual(ledger.balance(ledger.earnings(self.tutor)), 960_000)
        self.assertEqual(self.booking.lessons.filter(escrow_status=EscrowStatus.RELEASED).count(), 2)
        payout.refresh_from_db()
        self.assertEqual(payout.status, Payout.Status.PARTIAL)
        self.assertTrue(Notification.objects.filter(user=self.tutor.user, event="payout_failed").exists())
        # Retry needs a fresh 2FA code and moves the money back into transit under a new reference.
        c = staff_client(APIClient(), self.fin1)
        self.assertEqual(c.post(f"/api/staff/payout-items/{item.pk}/retry/", {"totp": "000000"}, format="json").status_code, 403)
        r = c.post(f"/api/staff/payout-items/{item.pk}/retry/", {"totp": pyotp.TOTP(self.fin1.totp_secret).now()}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        item.refresh_from_db()
        self.assertEqual(item.status, PayoutItem.Status.SENT)
        self.assertEqual(ledger.balance(ledger.earnings(self.tutor)), 0)
        services.settle_transfer(item, success=True)
        self.assertEqual(ledger.balance(ledger.platform(AccountKind.PAYOUTS_IN_TRANSIT)), 0)
        d, c2 = ledger.trial_balance()
        self.assertEqual(d, c2)

    def test_settle_is_idempotent(self):
        payout = services.create_payout_batch(self.fin1)
        self._approve(payout)
        item = payout.items.get()
        services.settle_transfer(item, success=True)
        item.refresh_from_db()
        services.settle_transfer(item, success=True)
        self.assertEqual(ledger.balance(ledger.platform(AccountKind.PAYOUTS_IN_TRANSIT)), 0)

    def test_remove_item_from_draft(self):
        payout = services.create_payout_batch(self.fin1)
        item = payout.items.get()
        r = staff_client(APIClient(), self.fin1).post(f"/api/staff/payout-items/{item.pk}/remove/")
        self.assertEqual(r.status_code, 200)
        payout.refresh_from_db()
        self.assertEqual(payout.total_kobo, 0)

    def test_draft_only_and_cannot_approve_twice(self):
        payout = services.create_payout_batch(self.fin1)
        self._approve(payout)
        self.assertEqual(self._approve(payout).status_code, 400)

    def test_bank_change_hold_excludes_tutor(self):
        self.bank.payout_hold_until = timezone.now() + timedelta(hours=10)
        self.bank.save()
        self.assertEqual(services.create_payout_batch().items.count(), 0)

    def test_below_minimum_excluded(self):
        config.set_value("payout_min_kobo", 5_000_000)
        self.assertEqual(services.create_payout_batch().items.count(), 0)

    def test_no_verified_bank_excluded(self):
        self.bank.verified_at = None
        self.bank.save()
        self.assertEqual(services.create_payout_batch().items.count(), 0)

    def test_tutor_with_pending_item_not_batched_twice(self):
        services.create_payout_batch()
        self.assertEqual(services.create_payout_batch().items.count(), 0)

    def test_vetting_fee_deducted_once_from_first_earnings(self):
        config.set_value("vetting_fee_deduct_from_earnings", True)
        config.set_value("vetting_fee_kobo", 500_000)
        payout = services.create_payout_batch()
        self.assertEqual(payout.total_kobo, 960_000 - 500_000)
        revenue_before = ledger.balance(ledger.platform(AccountKind.PLATFORM_REVENUE))
        services.settle_vetting_fee(self.tutor)  # already fully deducted: no-op
        self.assertEqual(ledger.balance(ledger.platform(AccountKind.PLATFORM_REVENUE)), revenue_before)

    def test_weekly_cron_creates_system_batch_any_finance_can_approve(self):
        from django.core.management import call_command

        call_command("cron", "weekly", stdout=mock.Mock())
        payout = Payout.objects.get()
        self.assertIsNone(payout.created_by)
        self.assertEqual(self._approve(payout).status_code, 200)


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class BankAccountApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.tutor = make_tutor()
        self.c = APIClient()
        self.c.force_login(self.tutor.user)

    def test_first_account_name_match_passes_bank_check(self):
        r = self.c.post("/api/bank-account/", {"bank_code": "058", "bank_name": "GTBank", "account_number": "0123456789"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()["name_match"])
        self.assertIsNone(r.json()["payout_hold_until"])
        self.assertEqual(VerificationCheck.objects.get(tutor=self.tutor, check_type=CheckType.BANK).status, CheckStatus.PASSED)
        # Account number is encrypted at rest.
        from django.db import connection

        with connection.cursor() as cur:
            cur.execute("SELECT account_number FROM payments_bankaccount")
            self.assertNotIn("0123456789", cur.fetchone()[0])

    def test_name_mismatch_goes_to_manual_review(self):
        r = self.c.post("/api/bank-account/", {"bank_code": "058", "bank_name": "GTBank", "account_number": "0123450000"}, format="json")
        self.assertFalse(r.json()["name_match"])
        self.assertEqual(VerificationCheck.objects.get(tutor=self.tutor, check_type=CheckType.BANK).status, CheckStatus.MANUAL_REVIEW)

    def test_invalid_account_number(self):
        r = self.c.post("/api/bank-account/", {"bank_code": "058", "bank_name": "GTBank", "account_number": "123"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_change_requires_otp_and_starts_hold(self):
        self.c.post("/api/bank-account/", {"bank_code": "058", "bank_name": "GTBank", "account_number": "0123456789"}, format="json")
        body = {"bank_code": "044", "bank_name": "Access", "account_number": "9876543210"}
        self.assertEqual(self.c.post("/api/bank-account/", body, format="json").status_code, 400)
        self.assertEqual(self.c.post("/api/bank-account/otp/").status_code, 200)
        self.assertTrue(Notification.objects.filter(user=self.tutor.user, event="bank_change_otp").exists())
        code = OTPCode.issue(self.tutor.user, "bank_change")
        r = self.c.post("/api/bank-account/", {**body, "code": code}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNotNone(r.json()["payout_hold_until"])
        self.assertEqual(BankAccount.objects.filter(tutor=self.tutor, is_active=True).count(), 1)
        self.assertEqual(self.c.get("/api/bank-account/").json()["account_last4"], "3210")

    def test_banks_list(self):
        self.assertTrue(len(self.c.get("/api/banks/").json()) > 3)


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class WalletAndReceiptsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.c = APIClient()
        self.c.force_login(self.parent.user)

    def test_topup_limits_and_flow(self):
        self.assertEqual(self.c.post("/api/payments/topup/", {"amount_kobo": 50}, format="json").status_code, 400)
        r = self.c.post("/api/payments/topup/", {"amount_kobo": 2_000_000}, format="json")
        self.assertEqual(r.status_code, 201)
        ref = r.json()["reference"]
        self.assertIn("/dev/fake-checkout", r.json()["authorization_url"])
        self.c.post("/api/payments/dev/fake-complete/", {"reference": ref}, format="json")
        w = self.c.get("/api/wallet/").json()
        self.assertEqual(w["balance_kobo"], 2_000_000)
        self.assertEqual(w["entries"][0]["amount_kobo"], 2_000_000)
        self.assertEqual(self.c.get("/api/payments/").json()[0]["status"], "success")
        pdf = self.c.get(f"/api/payments/{ref}/receipt/")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_other_parents_payment_hidden(self):
        other, _ = make_parent()
        p = Payment.objects.create(parent=other, gateway="fake", reference="TB_other", amount_kobo=1)
        self.assertEqual(self.c.get(f"/api/payments/{p.reference}/").status_code, 404)

    @override_settings(DEBUG=False)
    def test_fake_gateway_disabled_without_debug(self):
        self.assertEqual(self.c.post("/api/payments/dev/fake-complete/", {"reference": "x"}, format="json").status_code, 404)

    def test_staff_cash_refund_requires_2fa_and_balance(self):
        fund_wallet(self.parent, 300_000)
        fin = make_staff(Role.FINANCE)
        c = staff_client(APIClient(), fin)
        url = f"/api/staff/parents/{self.parent.pk}/wallet-refund/"
        self.assertEqual(c.post(url, {"amount_kobo": 100_000, "totp": "1"}, format="json").status_code, 403)
        code = pyotp.TOTP(fin.totp_secret).now()
        self.assertEqual(c.post(url, {"amount_kobo": 900_000, "totp": code}, format="json").status_code, 400)
        self.assertEqual(c.post(url, {"amount_kobo": 100_000, "totp": code}, format="json").status_code, 200)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 200_000)


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class TutorEarningsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def test_earnings_and_statement(self):
        parent, child = make_parent()
        tutor = make_tutor(rate_kobo=600_000)
        booking = make_active_booking(parent, child, tutor)
        lessons = list(booking.lessons.all())
        from bookings import services as bs

        bs.confirm_lesson(deliver(lessons[0], tutor))
        deliver(lessons[1], tutor)  # completed, inside dispute window
        c = APIClient()
        c.force_login(tutor.user)
        e = c.get("/api/earnings/").json()
        self.assertEqual(e["cleared_kobo"], 480_000)
        self.assertEqual(e["pending_kobo"], 480_000)
        pdf = c.get(f"/api/earnings/statement/?month={timezone.localdate():%Y-%m}")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(c.get("/api/earnings/statement/?month=bad").status_code, 400)
