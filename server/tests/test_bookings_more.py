"""Booking/lesson lifecycle: validation, scheduled jobs, reschedule/cancel paths, replacement and API permissions."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import Role
from bookings import services
from bookings.models import Booking, BookingStatus, Lesson, LessonStatus
from core.models import Subject
from matching.models import LessonRequest, Match
from messaging.models import Notification, Thread
from payments import ledger
from tests.factories import deliver, fund_wallet, make_active_booking, make_parent, make_staff, make_tutor, next_weekday, seed, staff_client
from trust.models import Strike
from tutors.models import TutorStatus


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class BookingValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor()
        self.maths = Subject.objects.get(slug="mathematics")

    def _create(self, **kw):
        args = dict(parent=self.parent, tutor=self.tutor, child=self.child, subjects=[self.maths], package_size=4, lesson_minutes=60,
                    schedule=[{"weekday": 2, "start": "16:00"}], start_date=next_weekday(2))
        args.update(kw)
        return services.create_booking(**args)

    def test_quote_rejects_unsupported_sizes(self):
        with self.assertRaises(ValidationError):
            services.quote(parent=self.parent, tutor=self.tutor, package_size=5, lesson_minutes=60)
        with self.assertRaises(ValidationError):
            services.quote(parent=self.parent, tutor=self.tutor, package_size=4, lesson_minutes=45)

    def test_inactive_tutor_rejected(self):
        self.tutor.status = TutorStatus.SUSPENDED
        self.tutor.save()
        with self.assertRaises(ValidationError):
            self._create()

    def test_other_parents_child_rejected(self):
        _, other_child = make_parent()
        with self.assertRaises(ValidationError):
            self._create(child=other_child)

    def test_outside_availability_rejected(self):
        self.tutor.availability.all().delete()
        with self.assertRaisesMessage(ValidationError, "not available"):
            self._create()

    def test_past_start_and_empty_schedule_rejected(self):
        with self.assertRaises(ValidationError):
            self._create(start_date=timezone.localdate() - timedelta(days=1))
        with self.assertRaises(ValidationError):
            self._create(schedule=[])

    def test_blocked_date_conflict(self):
        self.tutor.blocked_dates.create(date=next_weekday(2))
        with self.assertRaisesMessage(ValidationError, "already booked"):
            self._create(package_size=1)

    def test_travel_buffer_enforced(self):
        make_active_booking(self.parent, self.child, self.tutor, package_size=1, weekday=2, start="16:00")
        # 17:15 starts 15 min after the 17:00 end: inside the 30-minute travel buffer.
        with self.assertRaisesMessage(ValidationError, "already booked"):
            self._create(package_size=1, schedule=[{"weekday": 2, "start": "17:15"}])
        self._create(package_size=1, schedule=[{"weekday": 2, "start": "17:30"}])  # exactly at buffer: fine

    def test_wallet_must_cover_total(self):
        b = self._create()
        with self.assertRaises(ValidationError):
            services.pay_from_wallet(b)

    def test_stale_unpaid_bookings_do_not_block_tutor(self):
        b = self._create(package_size=1)
        Booking.objects.filter(pk=b.pk).update(created_at=timezone.now() - timedelta(hours=3))
        self._create(package_size=1)  # same slot is free again
        self.assertEqual(services.expire_unpaid(), 1)
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.CANCELLED)


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class ScheduledJobTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor()

    def test_expired_offer_without_shortlist_goes_to_reassigning(self):
        ops = make_staff(Role.OPS)
        b = make_active_booking(self.parent, self.child, self.tutor, accept=False)
        Booking.objects.filter(pk=b.pk).update(offer_expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(services.expire_offers(), 1)
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.REASSIGNING)
        self.assertIn(self.tutor.pk, b.declined_tutor_ids)
        self.assertTrue(Notification.objects.filter(user=self.parent.user, event="booking_unfilled").exists())
        self.assertTrue(Notification.objects.filter(user=ops).exists())
        # Escrow is untouched while reassigning.
        self.assertEqual(ledger.balance(ledger.escrow(b)), b.lesson_price_kobo * b.package_size)

    def test_expired_offer_with_shortlist_goes_to_next_tutor(self):
        other = make_tutor(rate_kobo=self.tutor.hourly_rate_kobo)
        b = make_active_booking(self.parent, self.child, self.tutor, accept=False)
        req = LessonRequest.objects.create(parent=self.parent, child=self.child, schedule=b.schedule, start_date=b.start_date, area=self.parent.area)
        Match.objects.create(request=req, tutor=other, in_shortlist=True, rank=2)
        Booking.objects.filter(pk=b.pk).update(request=req, offer_expires_at=timezone.now() - timedelta(minutes=1))
        services.expire_offers()
        b.refresh_from_db()
        self.assertEqual((b.tutor_id, b.status), (other.pk, BookingStatus.OFFERED))
        self.assertEqual(set(b.lessons.values_list("tutor_id", flat=True)), {other.pk})

    def test_reminders_include_parent_code_once(self):
        b = make_active_booking(self.parent, self.child, self.tutor, package_size=1)
        lesson = b.lessons.get()
        lesson.scheduled_start = timezone.now() + timedelta(hours=2)
        lesson.scheduled_end = lesson.scheduled_start + timedelta(hours=1)
        lesson.save()
        services.send_reminders()
        services.send_reminders()
        n = Notification.objects.filter(user=self.parent.user, event="lesson_reminder", channel="sms")
        self.assertEqual(n.count(), 1)
        self.assertIn(lesson.checkin_code, n.get().body)
        tutor_sms = Notification.objects.get(user=self.tutor.user, event="lesson_reminder_tutor", channel="sms")
        self.assertNotIn(lesson.checkin_code, tutor_sms.body)  # the tutor must never receive the code

    def test_late_alert_sent_once(self):
        b = make_active_booking(self.parent, self.child, self.tutor, package_size=1)
        lesson = b.lessons.get()
        lesson.scheduled_start = timezone.now() - timedelta(minutes=20)
        lesson.scheduled_end = lesson.scheduled_start + timedelta(hours=1)
        lesson.save()
        services.detect_late_and_no_shows()
        services.detect_late_and_no_shows()
        self.assertEqual(Notification.objects.filter(user=self.parent.user, event="tutor_late", channel="inapp").count(), 1)
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, LessonStatus.SCHEDULED)

    def test_auto_close_tutor_who_never_checked_out(self):
        b = make_active_booking(self.parent, self.child, self.tutor, package_size=1)
        lesson = b.lessons.get()
        lesson.scheduled_start = timezone.now() - timedelta(minutes=5)
        lesson.save()
        services.check_in(lesson, self.tutor, lesson.checkin_code)
        Lesson.objects.filter(pk=lesson.pk).update(scheduled_start=timezone.now() - timedelta(hours=9), scheduled_end=timezone.now() - timedelta(hours=8))
        services.auto_confirm()
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, LessonStatus.COMPLETED)
        self.assertIn("did not check out", lesson.note_observations)

    def test_cron_command_runs_and_records_heartbeat(self):
        from io import StringIO

        from django.core.management import call_command

        from core.models import CronHeartbeat

        for task in ("minute", "five", "hourly", "daily", "monthly"):
            out = StringIO()
            call_command("cron", task, stdout=out)
            self.assertIn("done", out.getvalue())
        hb = CronHeartbeat.objects.get(name="process_jobs")
        self.assertIsNotNone(hb.last_finished_at)
        self.assertIsNone(hb.locked_until)

    def test_cron_lock_prevents_overlap(self):
        from io import StringIO

        from django.core.management import call_command

        from core.models import CronHeartbeat

        CronHeartbeat.objects.create(name="cron_hourly", locked_until=timezone.now() + timedelta(minutes=10))
        out = StringIO()
        call_command("cron", "hourly", stdout=out)
        self.assertIn("skipping", out.getvalue())


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class LessonActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor()
        self.booking = make_active_booking(self.parent, self.child, self.tutor)
        self.lesson = self.booking.lessons.order_by("scheduled_start").first()
        self.pc, self.tc = APIClient(), APIClient()
        self.pc.force_login(self.parent.user)
        self.tc.force_login(self.tutor.user)

    def _at(self, start):
        Lesson.objects.filter(pk=self.lesson.pk).update(scheduled_start=start, scheduled_end=start + timedelta(hours=1))
        self.lesson.refresh_from_db()

    def test_reschedule_rules(self):
        self._at(timezone.now() + timedelta(days=3))
        new = (timezone.now() + timedelta(days=4)).replace(hour=18, minute=0, second=0, microsecond=0)
        r = self.pc.post(f"/api/lessons/{self.lesson.pk}/reschedule/", {"start": new.isoformat()}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.scheduled_start, new)
        self.assertEqual(self.pc.post(f"/api/lessons/{self.lesson.pk}/reschedule/", {"start": "nonsense"}, format="json").status_code, 400)
        self._at(timezone.now() + timedelta(hours=5))
        r = self.pc.post(f"/api/lessons/{self.lesson.pk}/reschedule/", {"start": new.isoformat()}, format="json")
        self.assertEqual(r.status_code, 400)  # < 24h notice

    def test_reschedule_into_conflict_rejected(self):
        other = self.booking.lessons.order_by("scheduled_start")[1]
        self._at(timezone.now() + timedelta(days=3))
        r = self.pc.post(f"/api/lessons/{self.lesson.pk}/reschedule/", {"start": (other.scheduled_start + timedelta(minutes=30)).isoformat()}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_check_in_guards(self):
        self._at(timezone.now() + timedelta(hours=3))
        self.assertEqual(self.tc.post(f"/api/lessons/{self.lesson.pk}/check-in/", {"code": self.lesson.checkin_code}, format="json").status_code, 400)  # too early
        self._at(timezone.now())
        self.assertEqual(self.pc.post(f"/api/lessons/{self.lesson.pk}/check-in/", {"code": self.lesson.checkin_code}, format="json").status_code, 400)  # parent can't
        for _ in range(5):
            self.tc.post(f"/api/lessons/{self.lesson.pk}/check-in/", {"code": "999999" if self.lesson.checkin_code != "999999" else "111111"}, format="json")
        r = self.tc.post(f"/api/lessons/{self.lesson.pk}/check-in/", {"code": self.lesson.checkin_code}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Too many", str(r.json()))
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.code_attempts, 5)  # persisted despite the request failing
        # Support unlocks after confirming identity; then the right code works.
        ops = make_staff(Role.OPS)
        self.assertEqual(staff_client(APIClient(), ops).post(f"/api/staff/lessons/{self.lesson.pk}/unlock-codes/", {"reason": "Called parent"}, format="json").status_code, 200)
        self.assertEqual(self.tc.post(f"/api/lessons/{self.lesson.pk}/check-in/", {"code": self.lesson.checkin_code}, format="json").status_code, 200)

    def test_other_tutor_cannot_burn_attempts(self):
        self._at(timezone.now())
        intruder = make_tutor()
        with self.assertRaises(ValidationError):
            services.check_in(self.lesson, intruder, "000000")
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.code_attempts, 0)

    def test_check_in_records_location_with_consent(self):
        self._at(timezone.now())
        self.tc.post(f"/api/lessons/{self.lesson.pk}/check-in/", {"code": self.lesson.checkin_code, "lat": 6.4478, "lng": 3.4723}, format="json")
        self.lesson.refresh_from_db()
        self.assertEqual(float(self.lesson.checkin_lat), 6.4478)
        self.assertTrue(Notification.objects.filter(user=self.parent.user, event="tutor_checked_in").exists())

    def test_codes_only_visible_to_parent_near_lesson(self):
        self._at(timezone.now() + timedelta(hours=2))
        p = self.pc.get(f"/api/lessons/{self.lesson.pk}/").json()
        self.assertEqual(p["codes"]["checkin"], self.lesson.checkin_code)
        self.assertIsNone(self.tc.get(f"/api/lessons/{self.lesson.pk}/").json()["codes"])
        self._at(timezone.now() + timedelta(days=3))
        self.assertIsNone(self.pc.get(f"/api/lessons/{self.lesson.pk}/").json()["codes"])

    def test_only_parent_confirms(self):
        deliver(self.lesson, self.tutor)
        self.assertEqual(self.tc.post(f"/api/lessons/{self.lesson.pk}/confirm/").status_code, 400)
        self.assertEqual(self.pc.post(f"/api/lessons/{self.lesson.pk}/confirm/").status_code, 200)
        self.assertEqual(self.pc.post(f"/api/lessons/{self.lesson.pk}/confirm/").status_code, 400)  # already confirmed

    def test_tutor_late_cancel_strikes_and_refunds_parent_fully(self):
        self._at(timezone.now() + timedelta(hours=5))
        before = ledger.balance(ledger.wallet(self.parent))
        r = self.tc.post(f"/api/lessons/{self.lesson.pk}/cancel/", {"reason": "Sick"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)) - before, self.lesson.amount_kobo)
        self.assertTrue(Strike.objects.filter(tutor=self.tutor, reason="late_cancel").exists())

    def test_strangers_cannot_see_or_act_on_lessons(self):
        stranger_parent, _ = make_parent()
        c = APIClient()
        c.force_login(stranger_parent.user)
        self.assertEqual(c.get(f"/api/lessons/{self.lesson.pk}/").status_code, 404)
        self.assertEqual(c.post(f"/api/lessons/{self.lesson.pk}/cancel/").status_code, 404)
        self.assertEqual(c.get(f"/api/bookings/{self.booking.pk}/").status_code, 404)

    def test_safety_report_from_lesson(self):
        safety = make_staff(Role.SAFETY)
        r = self.pc.post(f"/api/lessons/{self.lesson.pk}/safety-report/", {"description": "Tutor behaving inappropriately"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Notification.objects.filter(user=safety, event="safety_alert", channel="sms").exists())
        self.assertEqual(self.pc.post(f"/api/lessons/{self.lesson.pk}/safety-report/", {}, format="json").status_code, 400)

    def test_progress_report_pdf(self):
        r = self.pc.get(f"/api/bookings/{self.booking.pk}/progress-report/?month={timezone.localdate():%Y-%m}")
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertEqual(self.pc.get(f"/api/bookings/{self.booking.pk}/progress-report/?month=13-2026").status_code, 400)

    def test_thread_created_on_accept_only(self):
        self.assertTrue(Thread.objects.filter(booking=self.booking).exists())
        unaccepted = make_active_booking(self.parent, self.child, make_tutor(), accept=False)
        self.assertFalse(Thread.objects.filter(booking=unaccepted).exists())


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class BookingApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor()
        self.pc = APIClient()
        self.pc.force_login(self.parent.user)

    def test_parent_cancels_before_acceptance(self):
        b = make_active_booking(self.parent, self.child, self.tutor, accept=False)
        before = ledger.balance(ledger.wallet(self.parent))
        self.assertEqual(self.pc.post(f"/api/bookings/{b.pk}/cancel/").status_code, 200)
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)) - before, b.total_kobo)
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.CANCELLED)

    def test_parent_cannot_cancel_accepted_booking_wholesale(self):
        b = make_active_booking(self.parent, self.child, self.tutor)
        self.assertEqual(self.pc.post(f"/api/bookings/{b.pk}/cancel/").status_code, 400)

    def test_tutor_cannot_accept_someone_elses_booking(self):
        b = make_active_booking(self.parent, self.child, self.tutor, accept=False)
        other = make_tutor()
        c = APIClient()
        c.force_login(other.user)
        self.assertEqual(c.post(f"/api/bookings/{b.pk}/accept/").status_code, 404)

    def test_replacement_request_and_ops_replace(self):
        ops = make_staff(Role.OPS)
        b = make_active_booking(self.parent, self.child, self.tutor)
        self.assertEqual(self.pc.post(f"/api/bookings/{b.pk}/request-replacement/", {"reason": "Not a fit"}, format="json").status_code, 200)
        self.assertTrue(Notification.objects.filter(user=ops).exists())
        new_tutor = make_tutor()
        r = staff_client(APIClient(), ops).post(f"/api/staff/bookings/{b.pk}/replace/", {"tutor": new_tutor.pk, "reason": "Parent request"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        new = Booking.objects.get(pk=r.json()["new_booking"])
        self.assertEqual((new.tutor_id, new.status, new.replaces_id), (new_tutor.pk, BookingStatus.OFFERED, b.pk))

    def test_auto_renew_toggle(self):
        b = make_active_booking(self.parent, self.child, self.tutor)
        self.assertTrue(self.pc.patch(f"/api/bookings/{b.pk}/auto-renew/", {"auto_renew": True}, format="json").json()["auto_renew"])

    def test_book_requires_shortlisted_tutor_for_request(self):
        req = LessonRequest.objects.create(parent=self.parent, child=self.child, schedule=[{"weekday": 2, "start": "16:00"}], start_date=next_weekday(2), area=self.parent.area)
        fund_wallet(self.parent, 10_000_000)
        r = self.pc.post("/api/bookings/book/", {"tutor": self.tutor.pk, "child": self.child.pk, "subjects": [Subject.objects.get(slug="mathematics").pk],
                                                 "package_size": 1, "lesson_minutes": 60, "schedule": [{"weekday": 2, "start": "16:00"}], "start_date": str(next_weekday(2)), "request": req.pk}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("shortlist", str(r.json()))

    def test_book_rejects_subject_tutor_does_not_teach(self):
        r = self.pc.post("/api/bookings/book/", {"tutor": self.tutor.pk, "child": self.child.pk, "subjects": [Subject.objects.get(slug="french").pk],
                                                 "package_size": 1, "lesson_minutes": 60, "schedule": [{"weekday": 2, "start": "16:00"}], "start_date": str(next_weekday(2))}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_book_paid_entirely_from_wallet(self):
        fund_wallet(self.parent, 10_000_000)
        r = self.pc.post("/api/bookings/book/", {"tutor": self.tutor.pk, "child": self.child.pk, "subjects": [Subject.objects.get(slug="mathematics").pk],
                                                 "package_size": 4, "lesson_minutes": 60, "schedule": [{"weekday": 2, "start": "16:00"}], "start_date": str(next_weekday(2))}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(r.json()["payment"])
        self.assertEqual(r.json()["booking"]["status"], "offered")

    def test_quote_endpoint_hides_commission(self):
        r = self.pc.post("/api/bookings-quote/", {"tutor": self.tutor.pk, "package_size": 4, "lesson_minutes": 90}, format="json")
        self.assertEqual(r.json()["total_kobo"], 4 * 900_000)
        self.assertNotIn("commission_pct", r.json())

    def test_staff_cancel_and_no_show(self):
        ops = make_staff(Role.OPS)
        b = make_active_booking(self.parent, self.child, self.tutor)
        lesson = b.lessons.first()
        Lesson.objects.filter(pk=lesson.pk).update(scheduled_start=timezone.now() - timedelta(minutes=10))
        c = staff_client(APIClient(), ops)
        self.assertEqual(c.post(f"/api/staff/lessons/{lesson.pk}/no-show/").status_code, 200)
        self.assertEqual(c.post(f"/api/staff/bookings/{b.pk}/cancel/", {"reason": "Family moved"}, format="json").status_code, 200)
        self.assertEqual(ledger.balance(ledger.escrow(b)), 0)
        self.assertEqual(c.post(f"/api/staff/bookings/{b.pk}/explode/").status_code, 400)


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class DateFilterTests(TestCase):
    """Regression: date filters must not depend on the database's time-zone tables (MySQL CONVERT_TZ returns NULL without them)."""

    @classmethod
    def setUpTestData(cls):
        seed()

    def test_lesson_date_range_filter(self):
        parent, child = make_parent()
        tutor = make_tutor()
        b = make_active_booking(parent, child, tutor, package_size=4)
        lessons = list(b.lessons.order_by("scheduled_start"))
        c = APIClient()
        c.force_login(parent.user)
        first = timezone.localtime(lessons[0].scheduled_start).date()
        r = c.get(f"/api/lessons/?from={first}&to={first}").json()
        self.assertEqual([x["id"] for x in r["results"]], [lessons[0].pk])
        r = c.get(f"/api/lessons/?from={first}").json()
        self.assertEqual(len(r["results"]), 4)
        self.assertEqual(c.get("/api/lessons/?from=yesterday").status_code, 400)

    def test_lesson_near_midnight_counts_on_lagos_day(self):
        """23:30 Lagos is 22:30 UTC on the same day; 00:30 Lagos is 23:30 UTC on the previous UTC day."""
        from core.dates import day_range

        parent, child = make_parent()
        tutor = make_tutor()
        b = make_active_booking(parent, child, tutor, package_size=1)
        lesson = b.lessons.get()
        day = timezone.localdate() + timedelta(days=5)
        lo, hi = day_range(day, day)
        lesson.scheduled_start = lo + timedelta(minutes=30)  # 00:30 Lagos
        lesson.save()
        self.assertTrue(b.lessons.filter(scheduled_start__gte=lo, scheduled_start__lt=hi).exists())
        self.assertFalse(b.lessons.filter(scheduled_start__gte=lo + timedelta(days=1), scheduled_start__lt=hi + timedelta(days=1)).exists())

    def test_export_from_filter(self):
        admin = make_staff(Role.SUPER)
        make_parent()
        s = staff_client(APIClient(), admin)
        today = timezone.localdate()
        rows = s.get(f"/api/staff/exports/payments/?from={today}").content.decode().strip().splitlines()
        self.assertEqual(len(rows), 1)  # header only, no crash
        self.assertEqual(s.get("/api/staff/exports/users/?from=nope").status_code, 400)

    def test_statement_includes_this_months_lessons(self):
        from unittest import mock

        parent, child = make_parent()
        tutor = make_tutor()
        b = make_active_booking(parent, child, tutor, package_size=1)
        services.confirm_lesson(deliver(b.lessons.get(), tutor))
        from core import pdf

        captured = []
        real_table = pdf._table
        with mock.patch.object(pdf, "_table", side_effect=lambda rows, *a, **k: captured.append(rows) or real_table(rows, *a, **k)):
            pdf.statement_pdf(tutor, timezone.localdate().year, timezone.localdate().month)
        lesson_rows = captured[0]
        self.assertEqual(len(lesson_rows), 3)  # header + 1 lesson + total

