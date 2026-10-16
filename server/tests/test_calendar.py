"""BKG-05: private iCalendar feed."""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Role
from bookings import services
from bookings.calendar import _fold
from tests.factories import make_active_booking, make_parent, make_staff, make_tutor, seed, staff_client


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake", SITE_URL="https://tutorbridge.test")
class CalendarFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor()
        self.booking = make_active_booking(self.parent, self.child, self.tutor, package_size=4)
        self.booking.area, self.booking.address = self.parent.area, "1 Test Street"  # as when booked through the app
        self.booking.save()

    def _feed_url(self, user):
        c = APIClient()
        c.force_login(user)
        info = c.get("/api/calendar/").json()
        self.assertTrue(info["webcal"].startswith("webcal://tutorbridge.test/api/calendar/"))
        return info["url"].replace("https://tutorbridge.test", "")

    def test_parent_feed_lists_lessons_without_secrets(self):
        url = self._feed_url(self.parent.user)
        r = APIClient().get(url)  # calendar apps fetch anonymously
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/calendar"))
        body = r.content.decode()
        self.assertTrue(body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n"))
        self.assertEqual(body.count("BEGIN:VEVENT"), 4)
        self.assertIn("SUMMARY:Mathematics with", body)
        self.assertIn("LOCATION:Lekki Phase 1\\, Lagos", body)
        for lesson in self.booking.lessons.all():
            self.assertIn(f"UID:lesson-{lesson.pk}@tutorbridge", body)
            self.assertNotIn(lesson.checkin_code, body)
            self.assertNotIn(lesson.checkout_code, body)
        self.assertNotIn("1 Test Street", body)  # full address never leaves the app

    def test_tutor_feed_only_after_accepting(self):
        other_parent, other_child = make_parent()
        pending = make_active_booking(other_parent, other_child, self.tutor, package_size=1, weekday=1, accept=False)
        body = APIClient().get(self._feed_url(self.tutor.user)).content.decode()
        self.assertEqual(body.count("BEGIN:VEVENT"), 4)
        self.assertNotIn(f"lesson-{pending.lessons.get().pk}@", body)
        self.assertIn("SUMMARY:Kid (JSS2) · Mathematics", body)

    def test_cancelled_lessons_marked_cancelled(self):
        lesson = self.booking.lessons.order_by("scheduled_start").last()
        services.cancel_lesson(lesson, self.parent.user, "Travel")
        body = APIClient().get(self._feed_url(self.parent.user)).content.decode()
        event = body.split(f"UID:lesson-{lesson.pk}@tutorbridge")[1].split("END:VEVENT")[0]
        self.assertIn("STATUS:CANCELLED", event)
        self.assertIn("SUMMARY:Cancelled: ", event)

    def test_reset_invalidates_old_url(self):
        old = self._feed_url(self.parent.user)
        c = APIClient()
        c.force_login(self.parent.user)
        new = c.post("/api/calendar/reset/").json()["url"].replace("https://tutorbridge.test", "")
        self.assertNotEqual(old, new)
        self.assertEqual(APIClient().get(old).status_code, 404)
        self.assertEqual(APIClient().get(new).status_code, 200)

    def test_bad_token_and_suspended_user(self):
        self.assertEqual(APIClient().get("/api/calendar/nope.ics").status_code, 404)
        url = self._feed_url(self.parent.user)
        from django.utils import timezone

        self.parent.user.suspended_at = timezone.now()
        self.parent.user.save()
        self.assertEqual(APIClient().get(url).status_code, 404)

    def test_staff_have_no_feed(self):
        c = staff_client(APIClient(), make_staff(Role.OPS))
        self.assertEqual(c.get("/api/calendar/").status_code, 400)

    def test_long_lines_fold_without_splitting_characters(self):
        line = "SUMMARY:" + "Mathématiques ₦ " * 20
        folded = _fold(line)
        for part in folded.split("\r\n"):
            self.assertLessEqual(len(part.encode("utf-8")), 75)
        self.assertEqual(folded.replace("\r\n ", ""), line)
