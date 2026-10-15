"""
End-to-end marketplace flow through the HTTP API, using the dev "fake" gateway:
request → matching → shortlist → trial booking → payment webhook → tutor accepts →
check-in/out → parent confirms → package with matching credit → payout (maker-checker) → transfer webhook.
"""
import json
from datetime import timedelta

import pyotp
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role
from bookings.models import Booking, BookingStatus, Lesson, LessonStatus
from core import config
from core.models import Area, Subject
from payments import ledger
from payments.gateways import FakeGateway
from payments.models import AccountKind, BankAccount, Payment, PayoutItem
from tests.factories import make_parent, make_staff, make_tutor, next_weekday, seed, staff_client


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class MarketplaceFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()
        cls.parent, cls.child = make_parent()
        cls.tutor = make_tutor(rate_kobo=600_000)  # ₦6,000/h
        cls.other_tutor = make_tutor(rate_kobo=550_000)
        cls.ops = make_staff(Role.OPS)
        cls.fin1 = make_staff(Role.FINANCE)
        cls.fin2 = make_staff(Role.FINANCE)
        cls.maths = Subject.objects.get(slug="mathematics")
        cls.area = Area.objects.get(slug="lekki-phase-1")

    def setUp(self):
        self.pc = APIClient()
        self.pc.force_login(self.parent.user)
        self.tc = APIClient()
        self.tc.force_login(self.tutor.user)

    # helpers ---------------------------------------------------------------
    def _request(self):
        self.start = next_weekday(2)
        r = self.pc.post("/api/requests/", {
            "child": self.child.pk, "subjects": [self.maths.pk], "schedule": [{"weekday": 2, "start": "16:00"}],
            "lesson_minutes": 60, "start_date": str(self.start), "address": "1 Test Street", "area": self.area.pk,
            "budget_max_kobo": 800_000, "preferences": {},
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def _publish(self, req_id, tutors):
        oc = staff_client(APIClient(), self.ops)
        detail = oc.get(f"/api/staff/requests/{req_id}/").json()
        for m in detail["matches"]:
            if m["tutor"]["id"] in tutors:
                self.assertEqual(oc.patch(f"/api/staff/matches/{m['id']}/", {"in_shortlist": True, "rank": tutors.index(m["tutor"]["id"]) + 1}, format="json").status_code, 200)
        r = oc.post(f"/api/staff/requests/{req_id}/publish/")
        self.assertEqual(r.status_code, 200, r.content)

    def _book(self, req_id, package_size):
        r = self.pc.post("/api/bookings/book/", {
            "tutor": self.tutor.pk, "child": self.child.pk, "subjects": [self.maths.pk], "package_size": package_size,
            "lesson_minutes": 60, "schedule": [{"weekday": 2, "start": "16:00"}], "start_date": str(self.start), "request": req_id,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def _pay(self, reference):
        r = self.pc.post("/api/payments/dev/fake-complete/", {"reference": reference}, format="json")
        self.assertEqual(r.json()["status"], "success")

    def _deliver(self, lesson):
        Lesson.objects.filter(pk=lesson.pk).update(scheduled_start=timezone.now() - timedelta(minutes=5), scheduled_end=timezone.now() + timedelta(minutes=55))
        lesson.refresh_from_db()
        bad = self.tc.post(f"/api/lessons/{lesson.pk}/check-in/", {"code": "000000" if lesson.checkin_code != "000000" else "111111"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.tc.post(f"/api/lessons/{lesson.pk}/check-in/", {"code": lesson.checkin_code}, format="json").status_code, 200)
        r = self.tc.post(f"/api/lessons/{lesson.pk}/check-out/", {"code": lesson.checkout_code, "topics": "Linear equations", "homework": "Ex 4.2"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.pc.post(f"/api/lessons/{lesson.pk}/confirm/").status_code, 200)

    # the test ----------------------------------------------------------------
    def test_full_flow(self):
        req_id = self._request()
        self.assertEqual(self.pc.get(f"/api/requests/{req_id}/shortlist/").json()["published"], False)
        self._publish(req_id, [self.tutor.pk, self.other_tutor.pk])
        shortlist = self.pc.get(f"/api/requests/{req_id}/shortlist/").json()
        self.assertEqual([i["tutor"]["id"] for i in shortlist["items"]], [self.tutor.pk, self.other_tutor.pk])
        self.assertNotIn("email", json.dumps(shortlist))  # TUT-14: never contact details

        # Trial: 1 lesson ₦6,000 + ₦5,000 matching fee
        res = self._book(req_id, 1)
        self.assertEqual(res["booking"]["total_kobo"], 600_000 + 500_000)
        booking = Booking.objects.get(pk=res["booking"]["id"])
        self.assertEqual(booking.status, BookingStatus.AWAITING_PAYMENT)
        self._pay(res["payment"]["reference"])
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.OFFERED)
        self.assertEqual(ledger.balance(ledger.escrow(booking)), 600_000)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 0)

        # The tutor cannot see the address before accepting, and never sees codes
        detail = self.tc.get(f"/api/bookings/{booking.pk}/").json()
        self.assertIsNone(detail["address_visible"])
        self.assertEqual(self.tc.post(f"/api/bookings/{booking.pk}/accept/").status_code, 200)
        detail = self.tc.get(f"/api/bookings/{booking.pk}/").json()
        self.assertEqual(detail["address_visible"], "1 Test Street")
        self.assertTrue(all(l["codes"] is None for l in detail["lessons"]))

        lesson = booking.lessons.get()
        self._deliver(lesson)
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, LessonStatus.CONFIRMED)
        self.assertEqual(ledger.balance(ledger.earnings(self.tutor)), 480_000)  # 80% of ₦6,000
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.COMPLETED)

        # Package of 4 with the matching fee credited back
        res = self._book(req_id, 4)
        self.assertEqual(res["booking"]["matching_credit_kobo"], 500_000)
        self.assertEqual(res["booking"]["total_kobo"], 4 * 600_000 - 500_000)
        self._pay(res["payment"]["reference"])
        pkg = Booking.objects.get(pk=res["booking"]["id"])
        self.assertEqual(ledger.balance(ledger.escrow(pkg)), 4 * 600_000)

        # Revenue so far: trial commission + matching fee - credit
        self.assertEqual(ledger.balance(ledger.platform(AccountKind.PLATFORM_REVENUE)), 120_000 + 500_000 - 500_000)

        # Payout: maker-checker
        config.set_value("payout_min_kobo", 100_000)
        config.set_value("vetting_fee_deduct_from_earnings", False)
        BankAccount.objects.create(tutor=self.tutor, bank_code="058", bank_name="GTBank", account_number="0123456789", account_last4="6789",
                                   account_name="X", name_match=True, verified_at=timezone.now(), recipient_code="RCP_x")
        f1 = staff_client(APIClient(), self.fin1)
        payout = f1.post("/api/staff/payouts/").json()
        self.assertEqual(payout["total_kobo"], 480_000)
        r = f1.post(f"/api/staff/payouts/{payout['id']}/approve/", {"totp": pyotp.TOTP(self.fin1.totp_secret).now()}, format="json")
        self.assertEqual(r.status_code, 403)  # creator cannot approve
        f2 = staff_client(APIClient(), self.fin2)
        r = f2.post(f"/api/staff/payouts/{payout['id']}/approve/", {"totp": "000000"}, format="json")
        self.assertEqual(r.status_code, 403)  # fresh 2FA code required
        r = f2.post(f"/api/staff/payouts/{payout['id']}/approve/", {"totp": pyotp.TOTP(self.fin2.totp_secret).now()}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(ledger.balance(ledger.earnings(self.tutor)), 0)
        self.assertEqual(ledger.balance(ledger.platform(AccountKind.PAYOUTS_IN_TRANSIT)), 480_000)

        item = PayoutItem.objects.get(payout_id=payout["id"])
        body = json.dumps({"event": "transfer.success", "reference": item.transfer_reference, "id": "t1"}).encode()
        r = self.client.post("/api/payments/webhooks/fake/", body, content_type="application/json", HTTP_X_FAKE_SIGNATURE=FakeGateway.sign(body))
        self.assertEqual(r.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.status, PayoutItem.Status.SUCCESS)
        self.assertEqual(ledger.balance(ledger.platform(AccountKind.PAYOUTS_IN_TRANSIT)), 0)
        d, c = ledger.trial_balance()
        self.assertEqual(d, c)

    def test_webhook_signature_and_replay(self):
        req_id = self._request()
        self._publish(req_id, [self.tutor.pk])
        res = self._book(req_id, 1)
        p = Payment.objects.get(reference=res["payment"]["reference"])
        p.raw_verification = {"fake_paid": True}
        p.save()
        body = json.dumps({"event": "charge.success", "reference": p.reference, "id": "x"}).encode()
        r = self.client.post("/api/payments/webhooks/fake/", body, content_type="application/json", HTTP_X_FAKE_SIGNATURE="forged")
        self.assertEqual(r.status_code, 401)
        p.refresh_from_db()
        self.assertEqual(p.status, Payment.Status.INITIATED)
        for _ in range(3):  # replays have no effect
            r = self.client.post("/api/payments/webhooks/fake/", body, content_type="application/json", HTTP_X_FAKE_SIGNATURE=FakeGateway.sign(body))
            self.assertEqual(r.status_code, 200)
        self.assertEqual(ledger.balance(ledger.escrow(Booking.objects.get(pk=res["booking"]["id"]))), 600_000)
        self.assertEqual(ledger.LedgerTransaction.objects.filter(reference=f"payment:{p.reference}").count(), 1)

    def test_browser_status_check_never_credits(self):
        req_id = self._request()
        self._publish(req_id, [self.tutor.pk])
        res = self._book(req_id, 1)
        r = self.pc.get(f"/api/payments/{res['payment']['reference']}/")
        self.assertEqual(r.json()["status"], "initiated")
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 0)

    def test_double_booking_prevented(self):
        req_id = self._request()
        self._publish(req_id, [self.tutor.pk])
        res = self._book(req_id, 4)
        self._pay(res["payment"]["reference"])
        parent2, child2 = make_parent()
        c2 = APIClient()
        c2.force_login(parent2.user)
        r = c2.post("/api/bookings/book/", {
            "tutor": self.tutor.pk, "child": child2.pk, "subjects": [self.maths.pk], "package_size": 1, "lesson_minutes": 60,
            "schedule": [{"weekday": 2, "start": "16:30"}], "start_date": str(self.start),
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("already booked", json.dumps(r.json()))

    def test_tutor_decline_reassigns_to_next_shortlisted(self):
        req_id = self._request()
        self._publish(req_id, [self.tutor.pk, self.other_tutor.pk])
        res = self._book(req_id, 1)
        self._pay(res["payment"]["reference"])
        r = self.tc.post(f"/api/bookings/{res['booking']['id']}/decline/", {"reason": "Too far"}, format="json")
        self.assertEqual(r.status_code, 200)
        b = Booking.objects.get(pk=res["booking"]["id"])
        self.assertEqual(b.tutor_id, self.other_tutor.pk)
        self.assertEqual(b.status, BookingStatus.OFFERED)
        # Cheaper tutor: the ₦500 difference goes back to the wallet
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 50_000)
        self.assertEqual(ledger.balance(ledger.escrow(b)), 550_000)
