"""Address search, real distances in matching, and check-in distance from the booked address."""
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from bookings import services
from core.geo import haversine_km, nearest_area, search
from core.models import Area
from matching.engine import distance_km
from matching.models import LessonRequest
from tests.factories import make_active_booking, make_parent, make_tutor, next_weekday, seed


def http(body):
    r = mock.Mock(status_code=200)
    r.json.return_value = body
    r.raise_for_status.return_value = None
    return r


NOMINATIM = [{"display_name": "12 Admiralty Way, Lekki Phase 1, Lagos", "lat": "6.4474", "lon": "3.4702"}]


@override_settings(GEO_PROVIDER="nominatim", GOOGLE_MAPS_API_KEY="", GEO_CONTACT_EMAIL="ops@tutorbridge.test")
class GeoSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        cache.clear()

    def test_nominatim_request_follows_usage_policy_and_is_cached(self):
        with mock.patch("core.geo.requests.get", return_value=http(NOMINATIM)) as get:
            first = search("12 Admiralty Way Lekki")
            second = search("  12 admiralty   way LEKKI ")  # same query after normalising
        self.assertEqual(first, [{"label": NOMINATIM[0]["display_name"], "lat": 6.4474, "lng": 3.4702}])
        self.assertEqual(first, second)
        self.assertEqual(get.call_count, 1)  # cached
        kw = get.call_args.kwargs
        self.assertIn("ops@tutorbridge.test", kw["headers"]["User-Agent"])
        self.assertEqual(kw["params"]["countrycodes"], "ng")

    @override_settings(GOOGLE_MAPS_API_KEY="AIza-test")
    def test_google_used_when_key_set(self):
        body = {"status": "OK", "results": [{"formatted_address": "Admiralty Way, Lekki", "geometry": {"location": {"lat": 6.44741, "lng": 3.47021}}}]}
        with mock.patch("core.geo.requests.get", return_value=http(body)) as get:
            self.assertEqual(search("Admiralty Way Lekki")[0]["lat"], 6.44741)
        self.assertIn("maps.googleapis.com", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["params"]["components"], "country:NG")

    @override_settings(GOOGLE_MAPS_API_KEY="AIza-test")
    def test_google_error_returns_empty_and_is_not_cached(self):
        with mock.patch("core.geo.requests.get", return_value=http({"status": "REQUEST_DENIED", "error_message": "bad key"})):
            self.assertEqual(search("Admiralty Way"), [])
        with mock.patch("core.geo.requests.get", return_value=http({"status": "ZERO_RESULTS", "results": []})) as get:
            search("Admiralty Way")
        self.assertEqual(get.call_count, 1)  # the failure wasn't cached

    def test_short_queries_skip_lookup(self):
        with mock.patch("core.geo.requests.get") as get:
            self.assertEqual(search("abc"), [])
        get.assert_not_called()

    def test_nearest_area(self):
        self.assertEqual(nearest_area(6.4474, 3.4702).slug, "lekki-phase-1")
        self.assertIsNone(nearest_area(9.07, 7.49))  # Abuja: no Lagos area within 15 km

    def test_search_endpoint_adds_nearest_area_and_needs_login(self):
        parent, _ = make_parent()
        c = APIClient()
        self.assertEqual(c.get("/api/geo/search/?q=Admiralty Way").status_code, 403)
        c.force_login(parent.user)
        with mock.patch("core.geo.requests.get", return_value=http(NOMINATIM)):
            r = c.get("/api/geo/search/?q=12 Admiralty Way").json()
        self.assertEqual((r[0]["area_name"], r[0]["lat"]), ("Lekki Phase 1", 6.4474))


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class DistanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def test_haversine(self):
        self.assertAlmostEqual(haversine_km(6.4474, 3.4702, 6.4698, 3.5852), 12.9, delta=0.3)  # Lekki Ph1 -> Ajah

    def test_precise_home_beats_area_centre(self):
        parent, child = make_parent()
        tutor = make_tutor(area_slug="ajah")
        req = LessonRequest.objects.create(parent=parent, child=child, schedule=[{"weekday": 2, "start": "16:00"}], start_date=next_weekday(2),
                                           area=Area.objects.get(slug="lekki-phase-1"), lat=Decimal("6.4474"), lng=Decimal("3.4702"))
        by_area = distance_km(tutor, req)
        tutor.home_lat, tutor.home_lng = Decimal("6.4480"), Decimal("3.4800")  # actually lives near Lekki Phase 1
        tutor.save()
        self.assertGreater(by_area, 10)
        self.assertLess(distance_km(tutor, req), 2)

    def test_checkin_distance_recorded(self):
        parent, child = make_parent()
        tutor = make_tutor()
        b = make_active_booking(parent, child, tutor, package_size=1)
        b.lat, b.lng = Decimal("6.447400"), Decimal("3.470200")
        b.save()
        lesson = b.lessons.get()
        lesson.scheduled_start = timezone.now()
        lesson.save()
        services.check_in(lesson, tutor, lesson.checkin_code, lat=6.4483, lng=3.4702)  # ~100 m north
        lesson.refresh_from_db()
        self.assertAlmostEqual(lesson.checkin_distance_m, 100, delta=5)

    def test_booking_carries_request_coordinates(self):
        from core.models import Subject
        from matching.models import Match
        from tests.factories import fund_wallet

        parent, child = make_parent()
        tutor = make_tutor()
        req = LessonRequest.objects.create(parent=parent, child=child, schedule=[{"weekday": 2, "start": "16:00"}], start_date=next_weekday(2),
                                           area=parent.area, address="12 Admiralty Way", lat=Decimal("6.4474"), lng=Decimal("3.4702"))
        Match.objects.create(request=req, tutor=tutor, in_shortlist=True)
        fund_wallet(parent, 10_000_000)
        c = APIClient()
        c.force_login(parent.user)
        r = c.post("/api/bookings/book/", {"tutor": tutor.pk, "child": child.pk, "subjects": [Subject.objects.get(slug="mathematics").pk], "package_size": 1,
                                           "lesson_minutes": 60, "schedule": [{"weekday": 2, "start": "16:00"}], "start_date": str(next_weekday(2)), "request": req.pk}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        from bookings.models import Booking

        b = Booking.objects.get(pk=r.json()["booking"]["id"])
        self.assertEqual((float(b.lat), float(b.lng)), (6.4474, 3.4702))
