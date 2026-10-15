"""
Local demo accounts and data. Refuses to run unless DEBUG is on.

Creates staff (one per role), a verified parent with a child, and three
fully-vetted Active tutors in Lekki/Ajah/Yaba so matching and booking can be
tried end to end.
"""
from datetime import date, time, timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Role, User
from core.models import Area, Curriculum, Level, Subject
from parents.models import Child, ParentProfile
from tutors.models import AvailabilitySlot, TutorArea, TutorProfile, TutorStatus, TutorSubject
from vetting.models import CheckStatus, CheckType, VerificationCheck

PASSWORD = "DemoPass!2026"

STAFF = [
    ("admin@tutorbridge.test", "+2348000000001", "Ada", "Admin", Role.SUPER),
    ("vetting@tutorbridge.test", "+2348000000002", "Victor", "Vetting", Role.VETTING),
    ("ops@tutorbridge.test", "+2348000000003", "Ope", "Operations", Role.OPS),
    ("finance@tutorbridge.test", "+2348000000004", "Fola", "Finance", Role.FINANCE),
    ("finance2@tutorbridge.test", "+2348000000005", "Femi", "Checker", Role.FINANCE),
    ("safety@tutorbridge.test", "+2348000000006", "Sade", "Safety", Role.SAFETY),
]

TUTORS = [
    ("tobi@tutorbridge.test", "+2348100000001", "Tobi", "Adeyemi", "male", "yaba", ["mathematics", "physics"], ["jss", "sss"], 6_000_00, "Physics graduate and WAEC/JAMB specialist",
     "Physics graduate (UNILAG) and secondary-school teacher. Patient, exam-focused, WAEC and JAMB specialist."),
    ("ngozi@tutorbridge.test", "+2348100000002", "Ngozi", "Okafor", "female", "lekki-phase-1", ["mathematics", "english-language"], ["primary", "jss"], 5_500_00, "Common Entrance and phonics specialist",
     "Primary and JSS teacher with 8 years' experience, Common Entrance preparation and phonics."),
    ("aisha@tutorbridge.test", "+2348100000003", "Aisha", "Bello", "female", "ajah", ["english-language", "mathematics"], ["jss", "primary"], 5_000_00, "Calm, structured English & Maths lessons",
     "English and Maths tutor; NCE and B.Ed. Calm, structured lessons; experience with learners who need extra support."),
]


class Command(BaseCommand):
    help = "Create demo accounts (DEBUG only)"

    def handle(self, **opts):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DJANGO_DEBUG=1")
        call_command("seed_reference")
        now = timezone.now()
        for email, phone, first, last, role in STAFF:
            if not User.objects.filter(email=email).exists():
                User.objects.create_user(email=email, phone=phone, password=PASSWORD, first_name=first, last_name=last, role=role,
                                         email_verified_at=now, phone_verified_at=now)

        if not User.objects.filter(email="parent@tutorbridge.test").exists():
            u = User.objects.create_user(email="parent@tutorbridge.test", phone="+2348200000001", password=PASSWORD, first_name="Adaeze",
                                         last_name="Nwosu", gender="female", role=Role.PARENT, email_verified_at=now, phone_verified_at=now, consent_terms_at=now)
            p = ParentProfile.objects.create(user=u, address="12 Admiralty Way, Lekki Phase 1", area=Area.objects.get(slug="lekki-phase-1"))
            Child.objects.create(parent=p, first_name="Chidi", class_name="JSS2", level=Level.objects.get(code="jss"),
                                 curriculum=Curriculum.objects.get(code="nigerian"), school_type="private", parental_consent_at=now,
                                 learning_notes="Strong in English; needs confidence with algebra.")

        nigerian, british = Curriculum.objects.get(code="nigerian"), Curriculum.objects.get(code="british")
        for email, phone, first, last, gender, area_slug, subjects, levels, rate, headline, bio in TUTORS:
            if User.objects.filter(email=email).exists():
                continue
            u = User.objects.create_user(email=email, phone=phone, password=PASSWORD, first_name=first, last_name=last, gender=gender,
                                         role=Role.TUTOR, email_verified_at=now, phone_verified_at=now, consent_terms_at=now)
            home = Area.objects.get(slug=area_slug)
            t = TutorProfile.objects.create(
                user=u, status=TutorStatus.ACTIVE, headline=headline, bio=bio, highest_qualification="B.Sc. / B.Ed.",
                years_experience=6, hourly_rate_kobo=rate, home_area=home, max_travel_km=15, accepts_special_needs=first == "Aisha",
                submitted_at=now, approved_at=now, background_valid_until=date.today() + timedelta(days=365),
                safeguarding_completed_at=now, agreement_signed_at=now, agreement_signature=f"{first} {last}", location_consent=True,
            )
            t.curricula.set([nigerian, british])
            for s in subjects:
                for lv in levels:
                    TutorSubject.objects.create(tutor=t, subject=Subject.objects.get(slug=s), level=Level.objects.get(code=lv), test_score=85, verified=True)
            for a in Area.objects.filter(lga=home.lga):
                TutorArea.objects.get_or_create(tutor=t, area=a)
            TutorArea.objects.get_or_create(tutor=t, area=Area.objects.get(slug="lekki-phase-1"))
            for wd in range(0, 6):
                AvailabilitySlot.objects.create(tutor=t, weekday=wd, start_time=time(15, 0), end_time=time(20, 0))
            AvailabilitySlot.objects.create(tutor=t, weekday=5, start_time=time(9, 0), end_time=time(13, 0))
            for ct in CheckType.values:
                VerificationCheck.objects.update_or_create(tutor=t, check_type=ct, defaults={"status": CheckStatus.PASSED, "provider": "demo"})

        self.stdout.write(self.style.SUCCESS(f"Demo data ready. Every demo account uses the password: {PASSWORD}"))
        self.stdout.write("Staff: admin@ / vetting@ / ops@ / finance@ / finance2@ / safety@ tutorbridge.test (2FA setup required at first sign-in)")
        self.stdout.write("Parent: parent@tutorbridge.test   Tutors: tobi@ / ngozi@ / aisha@ tutorbridge.test")
