"""ADM-07: pilot reports."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role
from backoffice.reports import pilot_report
from bookings.models import Booking, Lesson, LessonStatus
from matching.models import LessonRequest
from tests.factories import deliver, make_active_booking, make_parent, make_staff, make_tutor, next_weekday, seed, staff_client


class PilotReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor()
        now = timezone.now()
        mk = lambda: LessonRequest.objects.create(parent=self.parent, child=self.child, schedule=[{"weekday": 2, "start": "16:00"}],  # noqa: E731
                                                  start_date=next_weekday(2), area=self.parent.area)
        self.filled, self.unfilled = mk(), mk()
        LessonRequest.objects.filter(pk__in=[self.filled.pk, self.unfilled.pk]).update(
            created_at=now - timedelta(days=3), shortlist_published_at=now - timedelta(days=3) + timedelta(hours=6))
        self.booking = make_active_booking(self.parent, self.child, self.tutor)
        Booking.objects.filter(pk=self.booking.pk).update(request=self.filled, created_at=now - timedelta(days=3) + timedelta(hours=2))
        first, second = self.booking.lessons.order_by("scheduled_start")[:2]
        deliver(first, self.tutor)
        Lesson.objects.filter(pk=first.pk).update(scheduled_start=now - timedelta(hours=3), scheduled_end=now - timedelta(hours=2))
        Lesson.objects.filter(pk=second.pk).update(status=LessonStatus.NO_SHOW, scheduled_start=now - timedelta(days=1, hours=1),
                                                   scheduled_end=now - timedelta(days=1))

    def metric(self, report, key):
        return next(m for m in report["scorecard"] if m["key"] == key)

    def test_scorecard_against_targets(self):
        r = pilot_report(days=30)
        fill = self.metric(r, "fill_rate")
        self.assertEqual((fill["value"], fill["n"], fill["on_target"]), (50.0, 2, False))
        self.assertEqual(self.metric(r, "time_to_shortlist")["value"], 6.0)
        self.assertTrue(self.metric(r, "time_to_shortlist")["on_target"])
        self.assertEqual(self.metric(r, "lesson_completion")["value"], 50.0)
        self.assertEqual(self.metric(r, "no_show_rate")["value"], 50.0)
        trial = self.metric(r, "trial_conversion")
        self.assertEqual((trial["value"], trial["on_target"]), (None, None))  # no data: neither pass nor fail

    def test_weekly_and_cohorts_and_areas(self):
        r = pilot_report(days=30)
        self.assertEqual(len(r["weekly"]), 12)
        self.assertEqual(sum(w["requests"] for w in r["weekly"]), 2)
        self.assertEqual(sum(w["lessons"] for w in r["weekly"]), 1)
        self.assertEqual(r["cohorts"][-1]["size"], 1)
        self.assertEqual(r["cohorts"][-1]["retention"][0], 100.0)
        self.assertEqual(r["areas"][0], {"area": "Lekki Phase 1", "requests": 2, "filled": 1, "fill_rate": 50.0})

    def test_endpoint_permissions_and_csv(self):
        ops = staff_client(APIClient(), make_staff(Role.OPS))
        self.assertEqual(ops.get("/api/staff/reports/").status_code, 200)
        self.assertEqual(ops.get("/api/staff/reports/?days=13").status_code, 400)
        csv = ops.get("/api/staff/reports/?days=90&export=csv")
        self.assertEqual(csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Fill rate,50.0,%", csv.content.decode("utf-8-sig"))
        vetting = staff_client(APIClient(), make_staff(Role.VETTING))
        self.assertEqual(vetting.get("/api/staff/reports/").status_code, 403)
