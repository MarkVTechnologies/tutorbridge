"""Cancellation, no-show, dispute and auto-confirm policies (section 4.4)."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Role
from bookings import services
from bookings.models import BookingStatus, EscrowStatus, LessonStatus
from core.models import Subject
from payments import ledger
from payments.models import AccountKind
from tests.factories import make_parent, make_staff, make_tutor, next_weekday, seed
from trust import services as trust
from trust.models import Strike


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class PolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor(rate_kobo=600_000)
        self.maths = Subject.objects.get(slug="mathematics")
        # Fund the wallet directly (as if a payment had cleared)
        ledger.transfer(f"seed:{self.parent.pk}", "payment", "seed", ledger.platform(AccountKind.GATEWAY_CLEARING), ledger.wallet(self.parent), 5_000_000)
        self.booking = services.create_booking(
            parent=self.parent, tutor=self.tutor, child=self.child, subjects=[self.maths], package_size=4, lesson_minutes=60,
            schedule=[{"weekday": 3, "start": "17:00"}], start_date=next_weekday(3),
        )
        services.pay_from_wallet(self.booking)
        services.tutor_accept(self.booking, self.tutor)
        self.lesson = self.booking.lessons.order_by("scheduled_start").first()

    def _move(self, start):
        self.lesson.scheduled_start, self.lesson.scheduled_end = start, start + timedelta(hours=1)
        self.lesson.save()

    def test_cancel_with_notice_full_credit(self):
        before = ledger.balance(ledger.wallet(self.parent))
        self._move(timezone.now() + timedelta(hours=30))
        services.cancel_lesson(self.lesson, self.parent.user, "Travel")
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)) - before, 600_000)
        self.assertEqual(ledger.balance(ledger.earnings(self.tutor)), 0)

    def test_late_cancel_pays_tutor_half(self):
        before = ledger.balance(ledger.wallet(self.parent))
        self._move(timezone.now() + timedelta(hours=5))
        services.cancel_lesson(self.lesson, self.parent.user, "Sick")
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)) - before, 300_000)
        self.assertEqual(ledger.balance(ledger.earnings(self.tutor)), 240_000)  # 50% of ₦6,000 minus 20%

    def test_no_show_refunds_and_strikes(self):
        before = ledger.balance(ledger.wallet(self.parent))
        self._move(timezone.now() - timedelta(minutes=50))
        services.detect_late_and_no_shows()
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.status, LessonStatus.NO_SHOW)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)) - before, 600_000)
        self.assertEqual(Strike.objects.filter(tutor=self.tutor, reason="no_show").count(), 1)

    def _complete(self):
        self._move(timezone.now() - timedelta(minutes=10))
        services.check_in(self.lesson, self.tutor, self.lesson.checkin_code)
        self.lesson.refresh_from_db()
        services.check_out(self.lesson, self.tutor, self.lesson.checkout_code, "Fractions")
        self.lesson.refresh_from_db()

    def test_check_out_requires_note(self):
        self._move(timezone.now() - timedelta(minutes=10))
        services.check_in(self.lesson, self.tutor, self.lesson.checkin_code)
        self.lesson.refresh_from_db()
        with self.assertRaises(Exception):
            services.check_out(self.lesson, self.tutor, self.lesson.checkout_code, "  ")

    def test_dispute_freezes_and_refund_resolution(self):
        self._complete()
        d = trust.raise_dispute(self.lesson, self.parent.user, "quality", "Tutor left early")
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.status, LessonStatus.DISPUTED)
        # Auto-confirm must skip disputed lessons even after the window
        self.lesson.scheduled_end = timezone.now() - timedelta(hours=72)
        self.lesson.save()
        services.auto_confirm()
        self.assertEqual(ledger.balance(ledger.earnings(self.tutor)), 0)
        before = ledger.balance(ledger.wallet(self.parent))
        trust.resolve_dispute(d, make_staff(Role.SAFETY), "refund", "Confirmed early departure")
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)) - before, 600_000)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.escrow_status, EscrowStatus.REFUNDED)

    def test_partial_dispute_resolution(self):
        self._complete()
        d = trust.raise_dispute(self.lesson, self.parent.user, "late", "45 minutes late")
        before = ledger.balance(ledger.wallet(self.parent))
        trust.resolve_dispute(d, make_staff(Role.SAFETY), "partial", "Half refund", refund_kobo=300_000)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)) - before, 300_000)
        self.assertEqual(ledger.balance(ledger.earnings(self.tutor)), 240_000)

    def test_auto_confirm_after_window(self):
        self._complete()
        self.lesson.scheduled_end = timezone.now() - timedelta(hours=49)
        self.lesson.save()
        self.assertEqual(services.auto_confirm(), 1)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.status, LessonStatus.CONFIRMED)
        self.assertEqual(ledger.balance(ledger.earnings(self.tutor)), 480_000)

    def test_dispute_window_closes(self):
        self._complete()
        self.lesson.scheduled_end = timezone.now() - timedelta(hours=49)
        self.lesson.save()
        with self.assertRaises(Exception):
            trust.raise_dispute(self.lesson, self.parent.user, "quality", "late complaint")

    def test_replace_tutor_carries_balance(self):
        new_tutor = make_tutor(rate_kobo=500_000)
        new = services.replace_tutor(self.booking, new_tutor, make_staff(Role.OPS), "Parent request")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.REPLACED)
        remaining = 4 * 600_000
        self.assertEqual(new.package_size, 4)  # ₦24,000 covers 4 lessons at ₦5,000
        self.assertEqual(ledger.balance(ledger.escrow(new)), 4 * 500_000)
        self.assertEqual(ledger.balance(ledger.escrow(self.booking)), 0)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 5_000_000 - remaining + (remaining - 4 * 500_000))

    def test_suspended_tutor_bookings_reassigning(self):
        trust.suspend_user(self.tutor.user, make_staff(Role.SAFETY), "Serious complaint")
        self.booking.refresh_from_db()
        self.tutor.refresh_from_db()
        self.assertEqual(self.tutor.status, "suspended")
        self.assertEqual(self.booking.status, BookingStatus.REASSIGNING)
