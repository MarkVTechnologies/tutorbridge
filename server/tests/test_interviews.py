"""TUT-10: interview booking confirmations and reminders."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role
from messaging.models import Notification
from tests.factories import make_staff, make_tutor, seed
from tutors.models import TutorStatus
from vetting.models import InterviewSlot
from vetting.services import send_interview_reminders


class InterviewReminderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.officer = make_staff(Role.VETTING)
        self.tutor = make_tutor()
        self.tutor.status = TutorStatus.UNDER_REVIEW
        self.tutor.save()

    def _slot(self, hours, booked=True):
        return InterviewSlot.objects.create(officer=self.officer, starts_at=timezone.now() + timedelta(hours=hours),
                                            meeting_link="https://meet.google.com/abc-defg-hij", tutor=self.tutor if booked else None)

    def test_booking_confirms_to_tutor_and_officer(self):
        slot = self._slot(48, booked=False)
        c = APIClient()
        c.force_login(self.tutor.user)
        self.assertEqual(c.post(f"/api/vetting/interview-slots/{slot.pk}/book/").status_code, 200)
        email = Notification.objects.get(user=self.tutor.user, event="interview_booked", channel="email")
        self.assertIn("meet.google.com/abc-defg-hij", email.body)
        self.assertTrue(Notification.objects.filter(user=self.tutor.user, event="interview_booked", channel="sms").exists())
        self.assertTrue(Notification.objects.filter(user=self.officer, event="interview_booked_officer").exists())

    def test_24h_then_1h_reminders_sent_once(self):
        slot = self._slot(20)
        self.assertEqual(send_interview_reminders(), 1)
        self.assertEqual(send_interview_reminders(), 0)
        self.assertEqual(Notification.objects.filter(user=self.tutor.user, event="interview_reminder", channel="sms").count(), 1)
        InterviewSlot.objects.filter(pk=slot.pk).update(starts_at=timezone.now() + timedelta(minutes=45))
        self.assertEqual(send_interview_reminders(), 1)
        self.assertEqual(send_interview_reminders(), 0)
        self.assertTrue(Notification.objects.filter(user=self.tutor.user, event="interview_soon", channel="sms").exists())

    def test_late_booking_gets_only_the_1h_reminder(self):
        self._slot(0.5)
        send_interview_reminders()
        self.assertFalse(Notification.objects.filter(event="interview_reminder").exists())
        self.assertTrue(Notification.objects.filter(event="interview_soon").exists())

    def test_ignored_slots(self):
        self._slot(20, booked=False)  # nobody booked
        done = self._slot(20)
        done.outcome = "pass"
        done.save()
        self._slot(-1)  # already started
        self._slot(30)  # more than 24h away
        self.assertEqual(send_interview_reminders(), 0)

    def test_five_minute_cron_sends_reminders(self):
        from io import StringIO

        from django.core.management import call_command

        self._slot(20)
        call_command("cron", "five", stdout=StringIO())
        self.assertTrue(Notification.objects.filter(event="interview_reminder").exists())
