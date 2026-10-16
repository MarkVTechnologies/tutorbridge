"""LSN-07: tutors add a video link to online bookings."""
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from bookings import services
from messaging.models import Notification
from tests.factories import make_active_booking, make_parent, make_tutor, seed

MEET = "https://meet.google.com/abc-defg-hij"


class OnlineLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor()
        self.booking = make_active_booking(self.parent, self.child, self.tutor)
        self.booking.is_online = True
        self.booking.save(update_fields=["is_online"])
        self.c = APIClient()
        self.c.force_login(self.tutor.user)

    def url(self):
        return f"/api/bookings/{self.booking.pk}/online-link/"

    def test_validator_allows_known_video_hosts_only(self):
        for ok in (MEET, "https://us02web.zoom.us/j/123", "https://teams.microsoft.com/l/meetup-join/x", "https://whereby.com/room"):
            self.assertEqual(services.validate_online_link(f"  {ok} "), ok)
        for bad in ("http://meet.google.com/abc", "https://evil.com/zoom.us", "https://zoom.us.evil.com/j/1", "javascript:alert(1)", ""):
            with self.assertRaises(ValidationError, msg=bad):
                services.validate_online_link(bad)

    def test_tutor_sets_link_and_parent_is_notified_once(self):
        r = self.c.patch(self.url(), {"online_link": MEET}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["online_link"], MEET)
        self.c.patch(self.url(), {"online_link": MEET}, format="json")  # unchanged: no second notification
        self.assertEqual(Notification.objects.filter(user=self.parent.user, event="online_link_set", channel="inapp").count(), 1)
        lesson = self.booking.lessons.first()
        pc = APIClient()
        pc.force_login(self.parent.user)
        data = pc.get(f"/api/lessons/{lesson.pk}/").json()
        self.assertEqual((data["is_online"], data["online_link"]), (True, MEET))

    def test_rejects_bad_link_in_person_booking_and_parent(self):
        self.assertEqual(self.c.patch(self.url(), {"online_link": "https://example.com/x"}, format="json").status_code, 400)
        self.booking.is_online = False
        self.booking.save(update_fields=["is_online"])
        self.assertEqual(self.c.patch(self.url(), {"online_link": MEET}, format="json").status_code, 400)
        pc = APIClient()
        pc.force_login(self.parent.user)
        self.assertEqual(pc.patch(self.url(), {"online_link": MEET}, format="json").status_code, 400)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.online_link, "")

    def test_other_tutor_cannot_set_link(self):
        other = make_tutor()
        c = APIClient()
        c.force_login(other.user)
        self.assertIn(c.patch(self.url(), {"online_link": MEET}, format="json").status_code, (400, 404))
