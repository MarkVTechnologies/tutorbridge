"""Reviews, reputation, incidents, account flows, messaging and staff vetting/matching endpoints."""
from datetime import timedelta

import pyotp
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import OTPCode, Role, User
from accounts.tokens import email_verification_token, encode_uid, password_reset_token
from bookings import services as bs
from bookings.models import LessonStatus
from core.models import AuditLog
from matching.models import LessonRequest, Match, MatchStatus, RequestStatus
from messaging.models import Message, Notification
from tests.factories import PASSWORD, deliver, make_active_booking, make_parent, make_staff, make_tutor, next_weekday, seed, staff_client
from trust import services as trust
from trust.models import Incident
from tutors.models import TutorStatus
from vetting.models import CheckStatus, CheckType, VerificationCheck


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class ReviewAndReputationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor()
        self.booking = make_active_booking(self.parent, self.child, self.tutor)

    def test_review_requires_confirmed_lesson_and_is_once_per_period(self):
        with self.assertRaises(ValidationError):
            trust.submit_review(self.booking, self.parent.user, 5)
        bs.confirm_lesson(deliver(self.booking.lessons.first(), self.tutor))
        with self.assertRaises(ValidationError):
            trust.submit_review(self.booking, self.parent.user, 6)
        trust.submit_review(self.booking, self.parent.user, 4, "Good")
        self.tutor.refresh_from_db()
        self.assertEqual((float(self.tutor.rating_avg), self.tutor.rating_count), (4.0, 1))
        with self.assertRaises(ValidationError):
            trust.submit_review(self.booking, self.parent.user, 5)
        stranger, _ = make_parent()
        with self.assertRaises(ValidationError):
            trust.submit_review(self.booking, stranger.user, 5)

    def test_tutor_rating_of_parent_is_private_and_aggregated(self):
        bs.confirm_lesson(deliver(self.booking.lessons.first(), self.tutor))
        r = trust.submit_review(self.booking, self.tutor.user, 2, "Often not home")
        self.assertEqual(r.direction, "tutor_to_parent")
        self.tutor.refresh_from_db()
        self.assertEqual(self.tutor.rating_count, 0)  # never mixed into the tutor's public rating
        self.assertEqual(trust.parent_rating_summary(self.parent)["rating_avg"], 2.0)
        public = APIClient().get(f"/api/tutors/{self.tutor.pk}/").json()
        self.assertNotIn("Often not home", str(public))

    def test_staff_hides_review_and_rating_recomputes(self):
        bs.confirm_lesson(deliver(self.booking.lessons.first(), self.tutor))
        r = trust.submit_review(self.booking, self.parent.user, 1, "abusive text")
        mod = make_staff(Role.SUPER)
        c = staff_client(APIClient(), mod)
        self.assertEqual(c.post(f"/api/staff/reviews/{r.pk}/visibility/", {"hide": True}, format="json").status_code, 400)  # reason required
        self.assertEqual(c.post(f"/api/staff/reviews/{r.pk}/visibility/", {"hide": True, "reason": "Abusive"}, format="json").status_code, 200)
        self.tutor.refresh_from_db()
        self.assertEqual(self.tutor.rating_count, 0)

    def test_reviews_api(self):
        bs.confirm_lesson(deliver(self.booking.lessons.first(), self.tutor))
        c = APIClient()
        c.force_login(self.parent.user)
        self.assertEqual(c.post("/api/reviews/", {"booking": self.booking.pk, "rating": 5, "comment": "Great"}, format="json").status_code, 201)
        self.assertEqual(len(c.get(f"/api/reviews/?booking={self.booking.pk}").json()), 1)

    def test_reliability_and_tier(self):
        lessons = list(self.booking.lessons.order_by("scheduled_start"))
        bs.confirm_lesson(deliver(lessons[0], self.tutor))
        lessons[1].scheduled_start = timezone.now() - timedelta(hours=2)
        lessons[1].scheduled_end = lessons[1].scheduled_start + timedelta(hours=1)
        lessons[1].save()
        bs.mark_no_show(lessons[1])
        score = trust.recompute_reliability(self.tutor)
        self.assertLess(score, 100)
        self.tutor.hours_taught, self.tutor.rating_avg, self.tutor.reliability_score = 400, 4.9, 99
        self.tutor.save()
        self.assertEqual(trust.recompute_tier(self.tutor), "elite")
        self.tutor.reliability_score = 90
        self.tutor.save()
        self.assertEqual(trust.recompute_tier(self.tutor), "gold")
        trust.nightly_reputation()  # smoke

    def test_third_strike_alerts_safety(self):
        safety = make_staff(Role.SAFETY)
        for _ in range(3):
            trust.add_strike(self.tutor, "policy_breach")
        self.assertTrue(Notification.objects.filter(user=safety, event="finance_alert").exists())

    def test_incident_api_and_staff_workflow(self):
        safety = make_staff(Role.SAFETY)
        c = APIClient()
        c.force_login(self.parent.user)
        r = c.post("/api/incidents/", {"description": "Concern", "booking": self.booking.pk}, format="json")
        self.assertEqual(r.status_code, 201)
        incident = Incident.objects.get()
        self.assertEqual(incident.subject_user, self.tutor.user)
        s = staff_client(APIClient(), safety)
        self.assertEqual(s.patch(f"/api/staff/incidents/{incident.pk}/", {"acknowledge": True}, format="json").status_code, 200)
        self.assertEqual(s.patch(f"/api/staff/incidents/{incident.pk}/", {"resolve": True}, format="json").status_code, 400)  # needs actions
        self.assertEqual(s.patch(f"/api/staff/incidents/{incident.pk}/", {"actions_taken": "Called both", "resolve": True}, format="json").status_code, 200)
        incident.refresh_from_db()
        self.assertEqual(incident.status, "resolved")
        self.assertEqual(len(s.get("/api/staff/incidents/").json()["results"]), 1)

    def test_suspend_reinstate_via_api(self):
        safety = make_staff(Role.SAFETY)
        s = staff_client(APIClient(), safety)
        self.assertEqual(s.post(f"/api/staff/users/{self.tutor.user.pk}/suspend/", {}, format="json").status_code, 400)
        self.assertEqual(s.post(f"/api/staff/users/{self.tutor.user.pk}/suspend/", {"reason": "Investigation"}, format="json").status_code, 200)
        r = APIClient().post("/api/auth/login/", {"identifier": self.tutor.user.email, "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(s.post(f"/api/staff/users/{self.tutor.user.pk}/suspend/", {"op": "reinstate", "reason": "Cleared"}, format="json").status_code, 200)
        self.tutor.refresh_from_db()
        self.assertEqual(self.tutor.status, TutorStatus.ACTIVE)
        self.assertEqual(s.post(f"/api/staff/users/{safety.pk}/suspend/", {"reason": "x"}, format="json").status_code, 400)  # staff via staff screen only

    def test_dispute_api(self):
        lesson = deliver(self.booking.lessons.first(), self.tutor)
        c = APIClient()
        c.force_login(self.parent.user)
        self.assertEqual(c.post(f"/api/lessons/{lesson.pk}/dispute/", {}, format="json").status_code, 400)
        self.assertEqual(c.post(f"/api/lessons/{lesson.pk}/dispute/", {"reason": "late", "description": "Very late"}, format="json").status_code, 200)
        self.assertEqual(c.post(f"/api/lessons/{lesson.pk}/dispute/", {"reason": "late", "description": "again"}, format="json").status_code, 400)
        self.assertEqual(c.get("/api/disputes/").json()[0]["status"], "open")
        safety = make_staff(Role.SAFETY)
        s = staff_client(APIClient(), safety)
        d = s.get("/api/staff/disputes/").json()["results"][0]
        self.assertEqual(s.post(f"/api/staff/disputes/{d['id']}/", {"assign_to_me": True}, format="json").status_code, 200)
        self.assertEqual(s.post(f"/api/staff/disputes/{d['id']}/", {"resolution": "reject", "notes": "Check-in times fine"}, format="json").status_code, 200)
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, LessonStatus.CONFIRMED)


class AccountFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def _signup(self):
        c = APIClient()
        r = c.post("/api/auth/signup/", {"role": "tutor", "first_name": "Tobi", "last_name": "Ade", "email": "tobi@example.com",
                                         "phone": "08031230000", "password": "Lekki-Lagos-2026", "consent_terms": True, "gender": "male"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return c, User.objects.get(email="tobi@example.com")

    def test_signup_tutor_creates_profile_and_sends_codes(self):
        c, u = self._signup()
        self.assertTrue(hasattr(u, "tutor_profile"))
        self.assertTrue(Notification.objects.filter(user=u, event="verify_email").exists())
        self.assertTrue(Notification.objects.filter(user=u, event="phone_otp", channel="sms").exists())
        # Duplicate email / phone rejected
        r = APIClient().post("/api/auth/signup/", {"role": "parent", "first_name": "X", "last_name": "Y", "email": "TOBI@example.com",
                                                   "phone": "+2348031230000", "password": "Lekki-Lagos-2026", "consent_terms": True}, format="json")
        self.assertIn("email", r.json())
        self.assertIn("phone", r.json())

    def test_phone_otp_verification(self):
        c, u = self._signup()
        self.assertEqual(c.post("/api/auth/phone/verify/", {"code": "000000"}, format="json").status_code, 400)
        code = OTPCode.issue(u, "phone")
        r = c.post("/api/auth/phone/verify/", {"code": code}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.json()["phone_verified_at"])
        self.assertEqual(c.post("/api/auth/phone/verify/", {"code": code}, format="json").status_code, 400)  # single use

    def test_otp_locks_after_five_wrong_tries(self):
        _, u = self._signup()
        code = OTPCode.issue(u, "phone")
        for _ in range(5):
            OTPCode.verify(u, "phone", "999999" if code != "999999" else "111111")
        self.assertFalse(OTPCode.verify(u, "phone", code))

    def test_email_verification_link(self):
        c, u = self._signup()
        token = email_verification_token.make_token(u)
        self.assertEqual(c.post("/api/auth/verify-email/", {"uid": encode_uid(u), "token": "bad"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/auth/verify-email/", {"uid": encode_uid(u), "token": token}, format="json").status_code, 200)
        u.refresh_from_db()
        self.assertIsNotNone(u.email_verified_at)
        self.assertEqual(c.post("/api/auth/verify-email/", {"uid": encode_uid(u), "token": token}, format="json").status_code, 400)  # single use

    def test_password_reset_is_single_use_and_no_enumeration(self):
        _, u = self._signup()
        a = APIClient().post("/api/auth/password/forgot/", {"email": "nobody@example.com"}, format="json").json()
        b = APIClient().post("/api/auth/password/forgot/", {"email": u.email}, format="json").json()
        self.assertEqual(a, b)
        token = password_reset_token.make_token(u)
        c = APIClient()
        self.assertEqual(c.post("/api/auth/password/reset/", {"uid": encode_uid(u), "token": token, "password": "short"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/auth/password/reset/", {"uid": encode_uid(u), "token": token, "password": "Brand-New-Pass-99"}, format="json").status_code, 200)
        self.assertEqual(c.post("/api/auth/password/reset/", {"uid": encode_uid(u), "token": token, "password": "Another-Pass-77"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/auth/login/", {"identifier": u.email, "password": "Brand-New-Pass-99"}, format="json").status_code, 200)

    def test_two_factor_setup_enable_disable(self):
        c, u = self._signup()
        setup = c.get("/api/auth/2fa/setup/").json()
        self.assertIn("<svg", setup["qr_svg"])
        self.assertEqual(c.post("/api/auth/2fa/enable/", {"code": "123456"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/auth/2fa/enable/", {"code": pyotp.TOTP(setup["secret"]).now()}, format="json").status_code, 200)
        self.assertEqual(c.get("/api/auth/2fa/setup/").status_code, 400)
        self.assertEqual(c.post("/api/auth/2fa/verify/", {"code": pyotp.TOTP(setup["secret"]).now()}, format="json").status_code, 200)
        self.assertEqual(c.post("/api/auth/2fa/disable/", {"code": pyotp.TOTP(setup["secret"]).now()}, format="json").status_code, 200)
        u.refresh_from_db()
        self.assertFalse(u.totp_enabled)
        self.assertTrue(AuditLog.objects.filter(action="auth.2fa_enabled", entity_id=str(u.pk)).exists())

    def test_staff_cannot_disable_2fa(self):
        s = make_staff(Role.OPS)
        c = staff_client(APIClient(), s)
        self.assertEqual(c.post("/api/auth/2fa/disable/", {"code": pyotp.TOTP(s.totp_secret).now()}, format="json").status_code, 400)

    def test_me_patch_only_safe_fields_and_export(self):
        c, u = self._signup()
        r = c.patch("/api/auth/me/", {"first_name": "Tobs", "role": "super_admin", "email": "x@y.z"}, format="json").json()
        self.assertEqual((r["first_name"], r["role"], r["email"]), ("Tobs", "tutor", "tobi@example.com"))
        data = c.get("/api/auth/me/export/").json()
        self.assertEqual(data["account"]["email"], "tobi@example.com")
        self.assertIn("profile", data)
        self.assertEqual(c.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(c.get("/api/auth/me/").status_code, 401)

    def test_email_job_delivers(self):
        _, u = self._signup()
        from core.jobs import enqueue, process_pending

        n = Notification.objects.filter(user=u, channel="email").first()
        with self.captureOnCommitCallbacks(execute=True):
            enqueue("send_email", {"notification_id": n.pk})
        self.assertGreaterEqual(process_pending(), 1)
        n.refresh_from_db()
        self.assertEqual(n.status, "sent")
        self.assertEqual(mail.outbox[-1].to, [u.email])


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class MessagingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.parent, self.child = make_parent()
        self.tutor = make_tutor()
        self.booking = make_active_booking(self.parent, self.child, self.tutor)
        self.pc, self.tc = APIClient(), APIClient()
        self.pc.force_login(self.parent.user)
        self.tc.force_login(self.tutor.user)
        self.thread = self.pc.get("/api/threads/").json()[0]["id"]

    def test_masking_storage_and_unread(self):
        r = self.tc.post(f"/api/threads/{self.thread}/messages/", {"body": "Call me 0803 123 4567"}, format="json")
        self.assertEqual(r.status_code, 200)
        m = Message.objects.get()
        self.assertNotIn("0803", m.body)
        self.assertIn("0803", m.original_body)
        self.assertTrue(m.flagged)
        self.assertEqual(self.pc.get("/api/threads/").json()[0]["unread"], 1)
        msgs = self.pc.get(f"/api/threads/{self.thread}/messages/").json()
        self.assertNotIn("0803", str(msgs))
        self.assertEqual(self.pc.get("/api/threads/").json()[0]["unread"], 0)
        self.assertTrue(Notification.objects.filter(user=self.parent.user, event="new_message").exists())

    def test_repeat_attempts_alert_staff(self):
        safety = make_staff(Role.SAFETY)
        for i in range(3):
            self.tc.post(f"/api/threads/{self.thread}/messages/", {"body": f"my whatsapp {i}"}, format="json")
        self.assertTrue(Notification.objects.filter(user=safety, event="finance_alert").exists())
        s = staff_client(APIClient(), safety)
        flagged = s.get("/api/staff/flagged-messages/").json()["results"]
        self.assertEqual(len(flagged), 3)
        self.assertIn("whatsapp", s.get(f"/api/staff/threads/{self.thread}/").json()[0]["original_body"])
        self.assertTrue(AuditLog.objects.filter(action="messages.view").exists())

    def test_validation_and_outsiders(self):
        self.assertEqual(self.pc.post(f"/api/threads/{self.thread}/messages/", {"body": "  "}, format="json").status_code, 400)
        self.assertEqual(self.pc.post(f"/api/threads/{self.thread}/messages/", {"body": "x" * 2001}, format="json").status_code, 400)
        stranger, _ = make_parent()
        c = APIClient()
        c.force_login(stranger.user)
        self.assertEqual(c.get(f"/api/threads/{self.thread}/messages/").status_code, 404)

    def test_closed_booking_blocks_messages(self):
        self.booking.status = "cancelled"
        self.booking.save()
        self.assertEqual(self.pc.post(f"/api/threads/{self.thread}/messages/", {"body": "hello"}, format="json").status_code, 400)

    def test_notifications_list_and_read(self):
        n = self.pc.get("/api/notifications/").json()
        self.assertGreater(n["unread"], 0)
        self.assertEqual(self.pc.post("/api/notifications/read/").json()["unread"], 0)


@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class StaffVettingAndMatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def test_vetting_decisions_return_detail(self):
        tutor = make_tutor()
        tutor.status = TutorStatus.UNDER_REVIEW
        tutor.background_valid_until = None
        tutor.save()
        VerificationCheck.objects.filter(tutor=tutor).update(status=CheckStatus.SUBMITTED)
        officer = make_staff(Role.VETTING)
        c = staff_client(APIClient(), officer)
        self.assertEqual(len(c.get("/api/staff/vetting/").json()["results"]), 1)
        r = c.post(f"/api/staff/vetting/{tutor.pk}/decision/", {"decision": "approve", "reason": "ok"}, format="json")
        self.assertEqual(r.status_code, 400)  # checks not passed
        self.assertEqual(c.post(f"/api/staff/vetting/{tutor.pk}/check/", {"check_type": "identity", "status": "failed"}, format="json").status_code, 400)  # notes needed
        for ct in CheckType.values:
            r = c.post(f"/api/staff/vetting/{tutor.pk}/check/", {"check_type": ct, "status": "passed", "notes": "ok"}, format="json")
            self.assertEqual(r.status_code, 200, r.content)  # previously 405
        r = c.post(f"/api/staff/vetting/{tutor.pk}/decision/", {"decision": "approve", "reason": "All checks passed"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        tutor.refresh_from_db()
        self.assertEqual(tutor.status, TutorStatus.ACTIVE)  # background passed → active immediately
        self.assertIsNotNone(tutor.background_valid_until)
        self.assertEqual(r.json()["history"][0]["to"], "active")
        self.assertTrue(Notification.objects.filter(user=tutor.user, event="tutor_approved").exists())

    def test_ops_matching_workflow(self):
        parent, child = make_parent()
        t1, t2 = make_tutor(), make_tutor(gender="male")
        c = APIClient()
        c.force_login(parent.user)
        r = c.post("/api/requests/", {"child": child.pk, "subjects": [t1.subjects.first().subject_id], "schedule": [{"weekday": 2, "start": "16:00"}],
                                      "lesson_minutes": 60, "start_date": str(next_weekday(2)), "address": "1 Road", "area": parent.area_id,
                                      "preferences": {"gender": "female"}}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        req = LessonRequest.objects.get()
        self.assertEqual(list(req.matches.values_list("tutor_id", flat=True)), [t1.pk])  # gender filter
        ops = make_staff(Role.OPS)
        s = staff_client(APIClient(), ops)
        self.assertEqual(s.post(f"/api/staff/requests/{req.pk}/publish/").status_code, 400)  # empty shortlist
        s.post(f"/api/staff/requests/{req.pk}/add-tutor/", {"tutor": t2.pk}, format="json")
        m1 = Match.objects.get(tutor=t1)
        s.post(f"/api/staff/matches/{m1.pk}/invite/")
        tc = APIClient()
        tc.force_login(t1.user)
        inv = tc.get("/api/tutor/invitations/").json()
        self.assertEqual(len(inv), 1)
        self.assertEqual(tc.post(f"/api/tutor/invitations/{m1.pk}/respond/", {"accept": False}, format="json").status_code, 400)  # reason needed
        self.assertEqual(tc.post(f"/api/tutor/invitations/{m1.pk}/respond/", {"accept": True}, format="json").status_code, 200)
        s.patch(f"/api/staff/matches/{m1.pk}/", {"in_shortlist": True}, format="json")
        r = s.post(f"/api/staff/requests/{req.pk}/publish/")
        self.assertEqual(r.status_code, 200)
        req.refresh_from_db()
        self.assertEqual(req.status, RequestStatus.SHORTLIST_READY)
        self.assertTrue(Notification.objects.filter(user=parent.user, event="shortlist_ready").exists())
        shortlist = c.get(f"/api/requests/{req.pk}/shortlist/").json()
        self.assertEqual([i["tutor"]["id"] for i in shortlist["items"]], [t1.pk])
        m2 = Match.objects.get(tutor=t2)
        s.patch(f"/api/staff/matches/{m2.pk}/", {"withdraw": True}, format="json")
        m2.refresh_from_db()
        self.assertEqual(m2.status, MatchStatus.WITHDRAWN)

    def test_sla_alert_once(self):
        from core.management.commands.cron import _request_sla_alerts

        parent, child = make_parent()
        ops = make_staff(Role.OPS)
        req = LessonRequest.objects.create(parent=parent, child=child, schedule=[{"weekday": 2, "start": "16:00"}], start_date=next_weekday(2),
                                           area=parent.area, sla_due_at=timezone.now() - timedelta(minutes=1))
        _request_sla_alerts()
        _request_sla_alerts()
        self.assertEqual(Notification.objects.filter(user=ops, channel="inapp").count(), 1)
        req.refresh_from_db()
        self.assertTrue(req.sla_alerted)

    def test_staff_lists_dashboard_and_exports(self):
        admin = make_staff(Role.SUPER)
        s = staff_client(APIClient(), admin)
        for url in ("/api/staff/dashboard/", "/api/staff/finance/", "/api/staff/finance/payments/", "/api/staff/payouts/", "/api/staff/users/",
                    "/api/staff/bookings/", "/api/staff/requests/", "/api/staff/disputes/", "/api/staff/reviews/", "/api/staff/audit/",
                    "/api/staff/staff-accounts/", "/api/staff/settings/", "/api/staff/interview-slots/", "/api/staff/questions/"):
            self.assertEqual(s.get(url).status_code, 200, url)
        for name in ("payments", "ledger", "payouts", "bookings", "lessons", "users"):
            r = s.get(f"/api/staff/exports/{name}/")
            self.assertEqual(r.status_code, 200, name)
            self.assertIn("text/csv", r["Content-Type"])
        self.assertEqual(s.get("/api/staff/exports/secrets/").status_code, 400)

    def test_csv_export_neutralises_formulas(self):
        admin = make_staff(Role.SUPER)
        make_parent()
        User.objects.filter(role=Role.PARENT).update(first_name="=HYPERLINK(evil)")
        body = staff_client(APIClient(), admin).get("/api/staff/exports/users/").content.decode()
        self.assertIn("'=HYPERLINK", body)

    def test_staff_account_management(self):
        admin = make_staff(Role.SUPER)
        s = staff_client(APIClient(), admin)
        r = s.post("/api/staff/staff-accounts/", {"email": "new@tb.test", "phone": "08099990000", "password": "Strong-Pass-123", "first_name": "N", "last_name": "S",
                                                  "role": "finance_officer", "extra_permissions": ["reports.export", "made.up"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        u = User.objects.get(email="new@tb.test")
        self.assertEqual(u.extra_permissions, ["reports.export"])
        self.assertEqual(s.post("/api/staff/staff-accounts/", {"role": "parent"}, format="json").status_code, 400)
        self.assertEqual(s.patch(f"/api/staff/staff-accounts/{u.pk}/", {"role": "ops_officer"}, format="json").status_code, 200)
        self.assertEqual(s.patch(f"/api/staff/staff-accounts/{admin.pk}/", {"is_active": False}, format="json").json()["suspended"], False)
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)  # can't deactivate yourself
