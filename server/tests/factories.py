"""Small helpers to build test data without fixtures."""
import itertools
from datetime import date, time, timedelta

from django.core.management import call_command
from django.utils import timezone

from accounts.models import Role, User
from core.models import Area, Curriculum, Level, Subject
from parents.models import Child, ParentProfile
from tutors.models import AvailabilitySlot, TutorArea, TutorProfile, TutorStatus, TutorSubject
from vetting.models import CheckStatus, CheckType, VerificationCheck

PASSWORD = "Sup3r-Secret-Pass"
_seq = itertools.count(1)


def seed():
    call_command("seed_reference", verbosity=0)


def make_user(role, **kw):
    n = next(_seq)
    now = timezone.now()
    defaults = dict(first_name=f"First{n}", last_name=f"Last{n}", role=role, email_verified_at=now, phone_verified_at=now)
    defaults.update(kw)
    return User.objects.create_user(email=f"user{n}@example.com", phone=f"+2348{n:09d}", password=PASSWORD, **defaults)


def make_staff(role, totp=True):
    import pyotp

    u = make_user(role)
    if totp:
        u.totp_secret = pyotp.random_base32()
        u.totp_enabled = True
        u.save()
    return u


def staff_client(client, user):
    """Log a staff user in with a 2FA-verified session."""
    client.force_login(user)
    s = client.session
    s["2fa_ok"] = True
    s.save()
    return client


def make_parent(area_slug="lekki-phase-1"):
    u = make_user(Role.PARENT, consent_terms_at=timezone.now())
    p = ParentProfile.objects.create(user=u, address="1 Test Street", area=Area.objects.get(slug=area_slug))
    child = Child.objects.create(parent=p, first_name="Kid", class_name="JSS2", level=Level.objects.get(code="jss"),
                                 curriculum=Curriculum.objects.get(code="nigerian"), parental_consent_at=timezone.now())
    return p, child


def make_tutor(area_slug="lekki-phase-1", rate_kobo=600_000, subjects=("mathematics",), level="jss", gender="female"):
    u = make_user(Role.TUTOR, gender=gender)
    home = Area.objects.get(slug=area_slug)
    t = TutorProfile.objects.create(user=u, status=TutorStatus.ACTIVE, hourly_rate_kobo=rate_kobo, home_area=home, max_travel_km=15,
                                    background_valid_until=date.today() + timedelta(days=300), location_consent=True)
    t.curricula.add(Curriculum.objects.get(code="nigerian"))
    for s in subjects:
        TutorSubject.objects.create(tutor=t, subject=Subject.objects.get(slug=s), level=Level.objects.get(code=level), test_score=80, verified=True)
    TutorArea.objects.create(tutor=t, area=home)
    for wd in range(7):
        AvailabilitySlot.objects.create(tutor=t, weekday=wd, start_time=time(8, 0), end_time=time(21, 0))
    for ct in CheckType.values:
        VerificationCheck.objects.create(tutor=t, check_type=ct, status=CheckStatus.PASSED)
    return t


def next_weekday(wd, days_ahead=2):
    d = timezone.localdate() + timedelta(days=days_ahead)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d
