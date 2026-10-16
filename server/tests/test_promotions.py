"""PAY-10: promo codes and referral credits."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import Role, User
from bookings import services
from bookings.models import BookingStatus
from core.models import Subject
from messaging.models import Notification
from payments import ledger
from payments.models import AccountKind, PromoCode, PromoRedemption, ReferralReward
from payments.promotions import evaluate, referral_code_for
from tests.factories import (
    deliver,
    fund_wallet,
    make_parent,
    make_staff,
    make_tutor,
    next_weekday,
    seed,
    staff_client,
)


def promo(**kw):
    defaults = dict(code="WELCOME10", kind="percent", value=10, max_uses_per_parent=1)
    defaults.update(kw)
    return PromoCode.objects.create(**defaults)


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class PromoCodeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor(rate_kobo=600_000)
        self.maths = Subject.objects.get(slug="mathematics")

    def _book(self, code=None, size=4, weekday=2, parent=None, child=None):
        parent, child = parent or self.parent, child or self.child
        return services.create_booking(parent=parent, tutor=self.tutor, child=child, subjects=[self.maths], package_size=size, lesson_minutes=60,
                                       schedule=[{"weekday": weekday, "start": "16:00"}], start_date=next_weekday(weekday), promo_code=code)

    def test_percent_discount_tutor_paid_in_full(self):
        promo(value=10)
        b = self._book("welcome10")  # case-insensitive
        self.assertEqual((b.discount_kobo, b.total_kobo), (240_000, 2_400_000 - 240_000))
        fund_wallet(self.parent, b.total_kobo)
        services.pay_from_wallet(b)
        b.refresh_from_db()
        self.assertEqual(ledger.balance(ledger.escrow(b)), 2_400_000)  # escrow holds full lesson value
        self.assertEqual(ledger.balance(ledger.platform(AccountKind.PROMOTIONS)), 240_000)  # funded by promotions expense
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 0)
        services.tutor_accept(b, self.tutor)
        services.confirm_lesson(deliver(b.lessons.first(), self.tutor))
        self.assertEqual(ledger.balance(ledger.earnings(self.tutor)), 480_000)  # 80% of the full ₦6,000

    def test_fixed_discount_with_cap_and_min_spend(self):
        promo(code="BIG", kind="fixed", value=5_000_000, max_discount_kobo=300_000)
        self.assertEqual(self._book("BIG").discount_kobo, 300_000)
        promo(code="MIN", kind="fixed", value=100_000, min_spend_kobo=10_000_000)
        with self.assertRaisesMessage(ValidationError, "at least"):
            self._book("MIN", weekday=3)

    def test_rules(self):
        now = timezone.now()
        promo(code="OLD", valid_until=now - timedelta(days=1))
        promo(code="SOON", valid_from=now + timedelta(days=1))
        promo(code="OFF", is_active=False)
        promo(code="PKG", packages_only=True)
        for code, msg in [("OLD", "expired"), ("SOON", "isn't active yet"), ("OFF", "isn't valid"), ("NOPE", "isn't valid"), ("PKG", "packages")]:
            with self.assertRaisesMessage(ValidationError, msg):
                evaluate(code, self.parent, 600_000, 1)

    def test_per_parent_and_total_limits_and_cancellation_frees_a_use(self):
        promo(code="ONCE", max_uses=2, max_uses_per_parent=1)
        b1 = self._book("ONCE")
        with self.assertRaisesMessage(ValidationError, "already used"):
            self._book("ONCE", weekday=3)
        p2, c2 = make_parent()
        self._book("ONCE", weekday=4, parent=p2, child=c2)
        p3, c3 = make_parent()
        with self.assertRaisesMessage(ValidationError, "fully redeemed"):
            self._book("ONCE", weekday=5, parent=p3, child=c3)
        services.cancel_booking(b1, self.parent.user, "changed mind")  # unpaid cancel frees the use
        self._book("ONCE", weekday=5, parent=p3, child=c3)
        self.assertEqual(PromoRedemption.objects.count(), 3)

    def test_first_booking_only(self):
        promo(code="FIRST", first_booking_only=True)
        b = self._book()
        fund_wallet(self.parent, b.total_kobo)
        services.pay_from_wallet(b)
        with self.assertRaisesMessage(ValidationError, "first booking"):
            evaluate("FIRST", self.parent, 2_400_000, 4)

    def test_cancelling_discounted_booking_claws_back_discount(self):
        promo(value=50)
        b = self._book("WELCOME10")
        fund_wallet(self.parent, b.total_kobo)
        services.pay_from_wallet(b)
        services.cancel_booking(b, self.parent.user, "changed mind")
        # They paid ₦12,000; ₦24,000 escrow returns to the wallet, minus the ₦12,000 discount clawed back.
        self.assertEqual(ledger.balance(ledger.wallet(self.parent)), 1_200_000)
        self.assertEqual(ledger.balance(ledger.platform(AccountKind.PROMOTIONS)), 0)
        d, c = ledger.trial_balance()
        self.assertEqual(d, c)

    def test_quote_and_book_api(self):
        promo(value=10)
        c = APIClient()
        c.force_login(self.parent.user)
        q = c.post("/api/bookings-quote/", {"tutor": self.tutor.pk, "package_size": 4, "lesson_minutes": 60, "promo_code": "welcome10"}, format="json").json()
        self.assertEqual((q["discount_kobo"], q["promo_code"], q["total_kobo"]), (240_000, "WELCOME10", 2_160_000))
        bad = c.post("/api/bookings-quote/", {"tutor": self.tutor.pk, "package_size": 4, "lesson_minutes": 60, "promo_code": "NOPE"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("promo_code", bad.json())
        fund_wallet(self.parent, 5_000_000)
        r = c.post("/api/bookings/book/", {"tutor": self.tutor.pk, "child": self.child.pk, "subjects": [self.maths.pk], "package_size": 4, "lesson_minutes": 60,
                                           "schedule": [{"weekday": 2, "start": "16:00"}], "start_date": str(next_weekday(2)), "promo_code": "WELCOME10"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.json()["booking"]["discount_kobo"], r.json()["booking"]["promo_code"]), (240_000, "WELCOME10"))

    def test_staff_promo_management(self):
        fin = make_staff(Role.FINANCE)
        s = staff_client(APIClient(), fin)
        r = s.post("/api/staff/promos/", {"code": "exam-25", "kind": "percent", "value": 25, "max_uses": 100, "packages_only": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["code"], "EXAM-25")
        self.assertEqual(s.post("/api/staff/promos/", {"code": "exam-25", "kind": "percent", "value": 5}, format="json").status_code, 400)
        self.assertEqual(s.post("/api/staff/promos/", {"code": "X", "kind": "percent", "value": 150}, format="json").status_code, 400)
        self.assertEqual(s.post("/api/staff/promos/", {"code": "bad code!", "kind": "fixed", "value": 5}, format="json").status_code, 400)
        pid = r.json()["id"]
        self.assertFalse(s.patch(f"/api/staff/promos/{pid}/", {"is_active": False}, format="json").json()["is_active"])
        self.assertEqual(s.get("/api/staff/promos/").json()[0]["uses"], 0)
        ops = staff_client(APIClient(), make_staff(Role.OPS))
        self.assertEqual(ops.get("/api/staff/promos/").status_code, 403)


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class ReferralTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def _signup(self, ref, email="new@example.com", phone="08031239999"):
        r = APIClient().post("/api/auth/signup/", {"role": "parent", "first_name": "New", "last_name": "Family", "email": email, "phone": phone,
                                                   "password": "Lekki-Lagos-2026", "consent_terms": True, "ref": ref}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return User.objects.get(email=email)

    def _complete_first_package(self, user):
        from core.models import Area, Curriculum, Level
        from parents.models import Child

        parent = user.parent_profile
        parent.area = Area.objects.get(slug="lekki-phase-1")
        parent.save()
        child = Child.objects.create(parent=parent, first_name="Kid", class_name="JSS1", level=Level.objects.get(code="jss"),
                                     curriculum=Curriculum.objects.get(code="nigerian"), parental_consent_at=timezone.now())
        tutor = make_tutor()
        fund_wallet(parent, 10_000_000)
        b = services.create_booking(parent=parent, tutor=tutor, child=child, subjects=[Subject.objects.get(slug="mathematics")], package_size=4,
                                    lesson_minutes=60, schedule=[{"weekday": 2, "start": "16:00"}], start_date=next_weekday(2))
        services.pay_from_wallet(b)
        services.tutor_accept(b, tutor)
        for lesson in b.lessons.all():
            services.confirm_lesson(deliver(lesson, tutor))
        b.refresh_from_db()
        self.assertEqual(b.status, BookingStatus.COMPLETED)
        return b

    def test_parent_refers_parent_both_credited_once(self):
        referrer, _ = make_parent()
        code = referral_code_for(referrer.user)
        self.assertEqual(APIClient().get(f"/api/referrals/{code.lower()}/").json(), {"valid": True, "first_name": referrer.user.first_name})
        new = self._signup(code.lower())
        self.assertEqual(new.referred_by, referrer.user)
        self._complete_first_package(new)
        self.assertEqual(ledger.balance(ledger.wallet(referrer)), 200_000)
        self.assertEqual(ReferralReward.objects.count(), 1)
        self.assertTrue(Notification.objects.filter(user=referrer.user, event="referral_reward").exists())
        self.assertEqual(ledger.balance(ledger.platform(AccountKind.PROMOTIONS)), 400_000)
        self._complete_first_package(new)  # second package: no new reward
        self.assertEqual(ReferralReward.objects.count(), 1)
        c = APIClient()
        c.force_login(referrer.user)
        stats = c.get("/api/referrals/").json()
        self.assertEqual((stats["invited"], stats["rewarded"], stats["earned_kobo"]), (1, 1, 200_000))
        self.assertTrue(stats["link"].endswith(f"/signup?ref={code}"))

    def test_tutor_referrer_credited_to_earnings(self):
        tutor = make_tutor()
        new = self._signup(referral_code_for(tutor.user))
        self._complete_first_package(new)
        self.assertEqual(ledger.balance(ledger.earnings(tutor)), 200_000)

    def test_trial_only_does_not_reward(self):
        referrer, _ = make_parent()
        new = self._signup(referral_code_for(referrer.user))
        from payments.promotions import grant_referral_reward

        b = self._complete_first_package(new)
        ReferralReward.objects.all().delete()
        b.is_trial = True
        self.assertIsNone(grant_referral_reward(b))

    def test_invalid_staff_or_suspended_referrers_ignored(self):
        staff = make_staff(Role.OPS)
        staff.referral_code = "STAFF123"
        staff.save()
        self.assertIsNone(self._signup("STAFF123").referred_by)
        self.assertIsNone(self._signup("NOSUCH", email="b@example.com", phone="08031238888").referred_by)
        referrer, _ = make_parent()
        code = referral_code_for(referrer.user)
        referrer.user.suspended_at = timezone.now()
        referrer.user.save()
        self.assertIsNone(self._signup(code, email="c@example.com", phone="08031237777").referred_by)

    def test_staff_get_no_referral_link(self):
        c = staff_client(APIClient(), make_staff(Role.OPS))
        self.assertEqual(c.get("/api/referrals/").status_code, 403)
