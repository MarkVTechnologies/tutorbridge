import hashlib
import hmac
import json

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Role, User
from accounts.phone import normalise_phone
from messaging.masking import mask
from payments.gateways import Paystack
from tests.factories import PASSWORD, make_parent, make_staff, make_tutor, seed, staff_client


class PhoneTests(TestCase):
    def test_nigerian_formats(self):
        for raw in ("08031234567", "8031234567", "2348031234567", "+234 803 123 4567", "0803-123-4567"):
            self.assertEqual(normalise_phone(raw), "+2348031234567")
        self.assertIsNone(normalise_phone("12345"))
        self.assertEqual(normalise_phone("+17135550100"), "+17135550100")  # diaspora


class MaskingTests(TestCase):
    def test_masks_contacts(self):
        for text in ("call me on 0803 123 4567", "email tobi.a@gmail.com", "tobi at gmail dot com", "my ig is @tobi_teaches",
                     "whatsapp me", "visit www.example.com", "zero eight zero three one two three"):
            masked, flagged = mask(text)
            self.assertTrue(flagged, text)
            self.assertIn("[hidden]", masked)

    def test_leaves_normal_text(self):
        masked, flagged = mask("Chidi did well on fractions today. Homework: exercise 4 page 12.")
        self.assertFalse(flagged)


class AuthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def test_signup_parent(self):
        c = APIClient()
        r = c.post("/api/auth/signup/", {"role": "parent", "first_name": "Ada", "last_name": "Obi", "email": "ada@example.com",
                                         "phone": "08031112222", "password": "Lekki-Lagos-2026", "consent_terms": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        u = User.objects.get(email="ada@example.com")
        self.assertEqual(u.phone, "+2348031112222")
        self.assertTrue(u.password.startswith("argon2"))
        self.assertFalse(r.json()["is_verified"])

    def test_signup_rejects_weak_password_and_no_consent(self):
        c = APIClient()
        r = c.post("/api/auth/signup/", {"role": "parent", "first_name": "A", "last_name": "B", "email": "x@example.com",
                                         "phone": "08031112223", "password": "short", "consent_terms": False}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_staff_signup_not_possible(self):
        r = APIClient().post("/api/auth/signup/", {"role": "super_admin", "first_name": "A", "last_name": "B", "email": "y@example.com",
                                                   "phone": "08031112224", "password": "Lekki-Lagos-2026", "consent_terms": True}, format="json")
        self.assertEqual(r.status_code, 400)

    @override_settings(REST_FRAMEWORK={"DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
                                       "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
                                       "DEFAULT_THROTTLE_RATES": {"login": "1000/min", "otp": "1000/min", "password_reset": "1000/min"}})
    def test_lockout_after_five_failures(self):
        p, _ = make_parent()
        c = APIClient()
        for _ in range(5):
            self.assertEqual(c.post("/api/auth/login/", {"identifier": p.user.email, "password": "wrong"}, format="json").status_code, 400)
        r = c.post("/api/auth/login/", {"identifier": p.user.email, "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 423)

    def test_login_by_phone(self):
        p, _ = make_parent()
        local = "0" + p.user.phone[4:]
        r = APIClient().post("/api/auth/login/", {"identifier": local, "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    def test_staff_with_totp_needs_code(self):
        import pyotp

        u = make_staff(Role.OPS)
        c = APIClient()
        r = c.post("/api/auth/login/", {"identifier": u.email, "password": PASSWORD}, format="json")
        self.assertEqual(r.json(), {"requires_2fa": True})
        self.assertEqual(c.get("/api/auth/me/").status_code, 401)
        r = c.post("/api/auth/login/2fa/", {"code": pyotp.TOTP(u.totp_secret).now()}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["two_factor_ok"])
        self.assertEqual(c.get("/api/staff/requests/").status_code, 200)


class PermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def test_staff_endpoints_require_2fa_session(self):
        u = make_staff(Role.OPS)
        c = APIClient()
        c.force_login(u)
        self.assertEqual(c.get("/api/staff/requests/").status_code, 403)
        staff_client(c, u)
        self.assertEqual(c.get("/api/staff/requests/").status_code, 200)

    def test_role_boundaries(self):
        ops = staff_client(APIClient(), make_staff(Role.OPS))
        self.assertEqual(ops.get("/api/staff/payouts/").status_code, 403)  # finance only
        self.assertEqual(ops.put("/api/staff/settings/", {"commission_pct_standard": 5}, format="json").status_code, 403)
        fin = staff_client(APIClient(), make_staff(Role.FINANCE))
        self.assertEqual(fin.get("/api/staff/vetting/").status_code, 403)
        admin = staff_client(APIClient(), make_staff(Role.SUPER))
        self.assertEqual(admin.put("/api/staff/settings/", {"commission_pct_standard": 18}, format="json").status_code, 200)

    def test_parent_and_tutor_cannot_reach_staff_api(self):
        p, _ = make_parent()
        c = APIClient()
        c.force_login(p.user)
        self.assertEqual(c.get("/api/staff/dashboard/").status_code, 403)
        t = make_tutor()
        c.force_login(t.user)
        self.assertEqual(c.get("/api/staff/dashboard/").status_code, 403)
        self.assertEqual(c.get("/api/parent/children/").status_code, 403)

    def test_unverified_parent_cannot_request(self):
        p, child = make_parent()
        p.user.phone_verified_at = None
        p.user.save()
        c = APIClient()
        c.force_login(p.user)
        self.assertEqual(c.post("/api/requests/", {}, format="json").status_code, 403)

    def test_public_search_hides_contacts(self):
        make_tutor()
        r = APIClient().get("/api/tutors/?subject=mathematics")
        self.assertEqual(r.status_code, 200)
        body = json.dumps(r.json())
        self.assertNotIn("@example.com", body)
        self.assertNotIn("+234", body)
        self.assertEqual(r.json()["count"], 1)


@override_settings(PAYSTACK_SECRET_KEY="sk_test_abc")
class PaystackSignatureTests(TestCase):
    def test_hmac(self):
        body = b'{"event":"charge.success"}'
        good = hmac.new(b"sk_test_abc", body, hashlib.sha512).hexdigest()
        self.assertTrue(Paystack().check_signature(body, {"X-Paystack-Signature": good}))
        self.assertFalse(Paystack().check_signature(body, {"X-Paystack-Signature": "bad"}))
        self.assertFalse(Paystack().check_signature(body, {}))
