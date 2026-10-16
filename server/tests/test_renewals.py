"""BKG-06: package auto-renewal with saved cards."""
import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from bookings import services
from bookings.models import Booking, BookingStatus, Lesson, LessonStatus
from core.models import Subject
from messaging.models import Notification, Thread
from payments import ledger
from payments import services as pay
from payments.gateways import FakeGateway, Flutterwave, Paystack
from payments.models import AccountKind, Payment, SavedCard
from tests.factories import fund_wallet, make_active_booking, make_parent, make_tutor, next_weekday, seed
from tutors.models import TutorStatus


def drain_wallet(parent):
    bal = ledger.balance(ledger.wallet(parent))
    if bal:
        ledger.transfer(f"drain:{parent.pk}:{bal}", "test", "drain", ledger.wallet(parent), ledger.platform(AccountKind.GATEWAY_CLEARING), bal)


def last_lesson_left(booking):
    """Leave only the final lesson scheduled, as if the rest were taught."""
    lessons = list(booking.lessons.order_by("scheduled_start"))
    Lesson.objects.filter(pk__in=[lsn.pk for lsn in lessons[:-1]]).update(status=LessonStatus.CONFIRMED)
    return lessons[-1]


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class RenewalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor(rate_kobo=600_000)
        self.booking = make_active_booking(self.parent, self.child, self.tutor, package_size=4)
        self.booking.auto_renew = True
        self.booking.save()

    def _card(self, code="AUTH_fake"):
        return SavedCard.objects.create(parent=self.parent, gateway="fake", authorization_code=code, last4="4081", brand="Visa", exp_month="12", exp_year="2030")

    def test_not_due_while_several_lessons_remain(self):
        self.assertEqual(services.renew_due_packages(), [])

    def test_renews_from_wallet_and_is_auto_accepted(self):
        last = last_lesson_left(self.booking)
        renewed = services.renew_due_packages()
        self.assertEqual(len(renewed), 1)
        new = Booking.objects.get(pk=renewed[0].pk)
        self.assertEqual((new.status, new.renews_id, new.auto_renew, new.package_size), (BookingStatus.ACTIVE, self.booking.pk, True, 4))
        self.assertGreater(new.lessons.order_by("scheduled_start").first().scheduled_start, last.scheduled_start)
        self.assertEqual(ledger.balance(ledger.escrow(new)), 4 * 600_000)
        # One conversation thread carries over to the renewal.
        self.assertEqual(Thread.objects.filter(booking__in=[self.booking, new]).count(), 1)
        self.assertEqual(Thread.objects.get().booking_id, new.pk)
        self.assertTrue(Notification.objects.filter(user=self.parent.user, event="package_renewed").exists())
        self.assertTrue(Notification.objects.filter(user=self.tutor.user, event="tutor_package_renewed").exists())
        self.assertFalse(Notification.objects.filter(user=self.tutor.user, event="booking_offer", link__endswith=str(new.pk)).exists())
        # Idempotent: the original won't renew twice, and the renewal isn't due yet.
        self.assertEqual(services.renew_due_packages(), [])

    def test_renews_with_saved_card_when_wallet_is_short(self):
        drain_wallet(self.parent)
        card = self._card()
        last_lesson_left(self.booking)
        new = services.renew_due_packages()[0]
        new.refresh_from_db()
        self.assertEqual(new.status, BookingStatus.ACTIVE)
        payment = Payment.objects.get(booking=new)
        self.assertEqual((payment.status, payment.saved_card_id, payment.amount_kobo), (Payment.Status.SUCCESS, card.pk, 4 * 600_000))
        msg = Notification.objects.get(user=self.parent.user, event="package_renewed", channel="email")
        self.assertIn("ending 4081", msg.body)

    def test_declined_card_holds_slots_then_expires(self):
        drain_wallet(self.parent)
        self._card("AUTH_x_declined")
        last_lesson_left(self.booking)
        new = services.renew_due_packages()[0]
        new.refresh_from_db()
        self.assertEqual(new.status, BookingStatus.AWAITING_PAYMENT)
        n = Notification.objects.get(user=self.parent.user, event="renewal_payment_needed", channel="email")
        self.assertIn("declined", n.body)
        # The slots stay held for the family: another parent can't take them during the payment window...
        other, other_child = make_parent()
        fund_wallet(other, 10_000_000)
        first_new = new.lessons.order_by("scheduled_start").first()
        with self.assertRaisesMessage(Exception, "already booked"):
            services.create_booking(parent=other, tutor=self.tutor, child=other_child, subjects=[Subject.objects.get(slug="mathematics")],
                                    package_size=1, lesson_minutes=60, schedule=new.schedule, start_date=timezone.localtime(first_new.scheduled_start).date())
        # ...the 2-hour checkout expiry doesn't apply to renewals...
        Booking.objects.filter(pk=new.pk).update(created_at=timezone.now() - timedelta(hours=3))
        services.expire_unpaid()
        new.refresh_from_db()
        self.assertEqual(new.status, BookingStatus.AWAITING_PAYMENT)
        # ...but after the renewal window it's released.
        Booking.objects.filter(pk=new.pk).update(created_at=timezone.now() - timedelta(hours=49))
        services.expire_unpaid()
        new.refresh_from_db()
        self.assertEqual(new.status, BookingStatus.CANCELLED)

    def test_parent_pays_held_renewal(self):
        drain_wallet(self.parent)
        last_lesson_left(self.booking)
        new = services.renew_due_packages()[0]  # no card: waits for payment
        c = APIClient()
        c.force_login(self.parent.user)
        detail = c.get(f"/api/bookings/{new.pk}/").json()
        self.assertEqual((detail["status"], detail["amount_due_kobo"], detail["renews"]), ("awaiting_payment", 4 * 600_000, self.booking.pk))
        r = c.post(f"/api/bookings/{new.pk}/pay/")
        self.assertEqual(r.status_code, 200, r.content)
        ref = r.json()["payment"]["reference"]
        c.post("/api/payments/dev/fake-complete/", {"reference": ref}, format="json")
        new.refresh_from_db()
        self.assertEqual(new.status, BookingStatus.ACTIVE)  # renewal: auto-accepted once paid
        self.assertEqual(c.post(f"/api/bookings/{new.pk}/pay/").status_code, 400)  # nothing left to pay
        # Original booking links forward to its renewal.
        self.assertEqual(c.get(f"/api/bookings/{self.booking.pk}/").json()["renewed_by"], new.pk)

    def test_pay_endpoint_uses_wallet_when_it_covers(self):
        c = APIClient()
        c.force_login(self.parent.user)
        fresh = services.create_booking(parent=self.parent, tutor=make_tutor(), child=self.child, subjects=[Subject.objects.get(slug="mathematics")],
                                        package_size=1, lesson_minutes=60, schedule=[{"weekday": 1, "start": "10:00"}], start_date=next_weekday(1))
        r = c.post(f"/api/bookings/{fresh.pk}/pay/").json()
        self.assertIsNone(r["payment"])
        self.assertEqual(r["booking"]["status"], "offered")

    def test_tutor_no_longer_active_turns_off_auto_renew(self):
        last_lesson_left(self.booking)
        self.tutor.status = TutorStatus.SUSPENDED
        self.tutor.save()
        self.assertEqual(services.renew_due_packages(), [])
        self.booking.refresh_from_db()
        self.assertFalse(self.booking.auto_renew)
        self.assertTrue(Notification.objects.filter(user=self.parent.user, event="renewal_failed").exists())

    def test_trials_and_opted_out_bookings_never_renew(self):
        self.booking.auto_renew = False
        self.booking.save()
        last_lesson_left(self.booking)
        self.assertEqual(services.renew_due_packages(), [])

    def test_hourly_cron_runs_renewals(self):
        from io import StringIO

        from django.core.management import call_command

        last_lesson_left(self.booking)
        call_command("cron", "hourly", stdout=StringIO())
        self.assertTrue(Booking.objects.filter(renews=self.booking).exists())


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class SavedCardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, _ = make_parent()
        self.c = APIClient()
        self.c.force_login(self.parent.user)

    def _pay(self, amount=1_000_000):
        ref = self.c.post("/api/payments/topup/", {"amount_kobo": amount}, format="json").json()["reference"]
        self.c.post("/api/payments/dev/fake-complete/", {"reference": ref}, format="json")

    def test_card_saved_once_and_listed(self):
        self._pay()
        self._pay()
        self.assertEqual(SavedCard.objects.filter(parent=self.parent).count(), 1)  # same card: de-duplicated
        cards = self.c.get("/api/wallet/").json()["saved_cards"]
        self.assertEqual(cards[0]["last4"], "4081")
        self.assertNotIn("authorization_code", json.dumps(cards))  # the token never leaves the server

    def test_card_token_encrypted_at_rest(self):
        self._pay()
        from django.db import connection

        with connection.cursor() as cur:
            cur.execute("SELECT authorization_code FROM payments_savedcard")
            self.assertNotIn("AUTH_fake", cur.fetchone()[0])

    def test_parent_removes_card(self):
        self._pay()
        card = SavedCard.objects.get()
        stranger, _ = make_parent()
        sc = APIClient()
        sc.force_login(stranger.user)
        self.assertEqual(sc.delete(f"/api/saved-cards/{card.pk}/").status_code, 404)
        self.assertEqual(self.c.delete(f"/api/saved-cards/{card.pk}/").status_code, 204)
        self.assertEqual(self.c.get("/api/wallet/").json()["saved_cards"], [])

    def test_gateway_error_during_charge_marks_failed(self):
        card = SavedCard.objects.create(parent=self.parent, gateway="fake", authorization_code="AUTH_fake", last4="1")
        with mock.patch.object(FakeGateway, "charge_authorization", side_effect=pay.GatewayError("timeout")):
            p = pay.charge_saved_card(self.parent, card, 100_000)
        self.assertEqual(p.status, Payment.Status.FAILED)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 0)


@override_settings(PAYSTACK_SECRET_KEY="sk_test_1", FLUTTERWAVE_SECRET_KEY="FLW_1")
class GatewayCardTests(TestCase):
    def test_paystack_reusable_card_only(self):
        raw = {"customer": {"email": "a@b.c"}, "authorization": {"authorization_code": "AUTH_1", "reusable": True, "channel": "card", "last4": "1234",
                                                                    "exp_month": "09", "exp_year": "2031", "card_type": "visa ", "signature": "SIG_1"}}
        info = Paystack().saved_card(raw)
        self.assertEqual((info.authorization_code, info.last4, info.brand, info.email), ("AUTH_1", "1234", "Visa", "a@b.c"))
        self.assertIsNone(Paystack().saved_card({**raw, "authorization": {**raw["authorization"], "reusable": False}}))
        self.assertIsNone(Paystack().saved_card({**raw, "authorization": {**raw["authorization"], "channel": "bank"}}))

    def test_paystack_charge_authorization_body(self):
        resp = mock.Mock(status_code=200, content=b"x")
        resp.json.return_value = {"status": True, "data": {"status": "success"}}
        with mock.patch("payments.gateways.requests.request", return_value=resp) as req:
            self.assertEqual(Paystack().charge_authorization(email="a@b.c", amount_kobo=500, authorization_code="AUTH_1", reference="R1"), "success")
        self.assertTrue(req.call_args.args[1].endswith("/transaction/charge_authorization"))
        self.assertEqual(req.call_args.kwargs["json"]["authorization_code"], "AUTH_1")

    def test_flutterwave_token_card(self):
        raw = {"customer": {"email": "a@b.c"}, "card": {"token": "flw-t1", "last_4digits": "5678", "expiry": "09/31", "type": "MASTERCARD", "first_6digits": "539983"}}
        info = Flutterwave().saved_card(raw)
        self.assertEqual((info.authorization_code, info.last4, info.exp_month, info.exp_year), ("flw-t1", "5678", "09", "31"))
        resp = mock.Mock(status_code=200, content=b"x")
        resp.json.return_value = {"status": "success", "data": {"status": "successful"}}
        with mock.patch("payments.gateways.requests.request", return_value=resp) as req:
            self.assertEqual(Flutterwave().charge_authorization(email="a@b.c", amount_kobo=150_000, authorization_code="flw-t1", reference="R1"), "success")
        self.assertEqual(req.call_args.kwargs["json"]["amount"], 1500)
