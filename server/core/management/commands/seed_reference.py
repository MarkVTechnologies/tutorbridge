"""Load reference data. Safe to run repeatedly (idempotent)."""
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from core.models import LGA, Area, Curriculum, Level, State, Subject

N = 100  # kobo per naira

LEVELS = [
    ("nursery", "Nursery", 3_000, 8_000),
    ("primary", "Primary", 3_500, 10_000),
    ("jss", "JSS", 4_000, 12_000),
    ("sss", "SSS", 5_000, 15_000),
    ("a_level", "A-Level / IB", 7_000, 20_000),
    ("university", "University", 8_000, 25_000),
]
CURRICULA = [("nigerian", "Nigerian"), ("british", "British"), ("american", "American"), ("montessori", "Montessori")]
SUBJECTS = [
    "Mathematics", "English Language", "Phonics", "Verbal Reasoning", "Quantitative Reasoning", "Basic Science", "Basic Technology",
    "Physics", "Chemistry", "Biology", "Further Mathematics", "Economics", "Accounting", "Commerce", "Geography", "Government",
    "Literature in English", "Civic Education", "CRS", "IRS", "French", "Yoruba", "Igbo", "Hausa", "Computer Studies", "Coding",
    "Agricultural Science", "History", "Music", "Special Needs Support",
]
# state -> lga -> [(area, lat, lng)]
AREAS = {
    "Lagos": {
        "Eti-Osa": [("Lekki Phase 1", 6.4478, 3.4723), ("Ajah", 6.4698, 3.5852), ("Ikoyi", 6.4550, 3.4350), ("Victoria Island", 6.4281, 3.4219),
                    ("Chevron", 6.4405, 3.5276), ("Oniru", 6.4339, 3.4524)],
        "Ibeju-Lekki": [("Sangotedo", 6.4708, 3.6255), ("Awoyaya", 6.4697, 3.6656)],
        "Ikeja": [("Ikeja GRA", 6.5833, 3.3500), ("Opebi", 6.5958, 3.3600), ("Maryland", 6.5714, 3.3667)],
        "Kosofe": [("Magodo", 6.6150, 3.3814), ("Gbagada", 6.5537, 3.3880), ("Ogudu", 6.5751, 3.3933), ("Ojota", 6.5850, 3.3800)],
        "Surulere": [("Surulere", 6.5000, 3.3500), ("Aguda", 6.4930, 3.3460)],
        "Lagos Mainland": [("Yaba", 6.5095, 3.3711), ("Ebute Metta", 6.4870, 3.3790)],
        "Ikorodu": [("Ikorodu", 6.6194, 3.5105)],
        "Alimosho": [("Egbeda", 6.5925, 3.2900), ("Ikotun", 6.5490, 3.2650)],
    },
}

QUESTIONS = {
    ("mathematics", "jss"): [
        ("Simplify 3x + 5x - 2x.", ["6x", "10x", "8x", "4x"], 0),
        ("What is 15% of 240?", ["24", "36", "30", "40"], 1),
        ("Solve for x: 2x + 7 = 19.", ["5", "6", "7", "12"], 1),
        ("The sum of the interior angles of a triangle is:", ["90°", "360°", "180°", "270°"], 2),
        ("Express 0.375 as a fraction in its lowest terms.", ["3/8", "37/100", "375/100", "3/4"], 0),
        ("What is the HCF of 24 and 36?", ["6", "12", "18", "72"], 1),
        ("A car travels 150 km in 2.5 hours. What is its average speed?", ["50 km/h", "55 km/h", "60 km/h", "65 km/h"], 2),
        ("Which of these is a prime number?", ["21", "27", "29", "33"], 2),
    ],
    ("mathematics", "primary"): [
        ("What is 7 × 8?", ["54", "56", "64", "48"], 1),
        ("Which fraction is the largest?", ["1/2", "1/3", "1/4", "1/5"], 0),
        ("What is 1,000 - 375?", ["625", "725", "635", "675"], 0),
        ("How many minutes are in 2 hours?", ["100", "120", "140", "60"], 1),
        ("Round 4,682 to the nearest hundred.", ["4,600", "4,700", "4,680", "5,000"], 1),
        ("What is the perimeter of a square with sides of 5 cm?", ["10 cm", "20 cm", "25 cm", "15 cm"], 1),
    ],
    ("english-language", "jss"): [
        ("Choose the correct option: She ___ to school every day.", ["go", "goes", "going", "gone"], 1),
        ("Which word is a synonym of 'happy'?", ["sad", "joyful", "angry", "tired"], 1),
        ("Identify the noun in: 'The boy kicked the ball.'", ["kicked", "the", "boy", "quickly"], 2),
        ("The plural of 'child' is:", ["childs", "childes", "children", "childrens"], 2),
        ("Choose the correctly punctuated sentence.", ["its raining.", "It's raining.", "Its' raining.", "it's raining"], 1),
        ("Which is an antonym of 'generous'?", ["kind", "mean", "giving", "liberal"], 1),
    ],
    ("physics", "sss"): [
        ("The SI unit of force is the:", ["Joule", "Watt", "Newton", "Pascal"], 2),
        ("Speed is a ___ quantity.", ["vector", "scalar", "derived vector", "dimensionless"], 1),
        ("Acceleration due to gravity near Earth's surface is approximately:", ["9.8 m/s²", "8.9 m/s²", "10.8 m/s²", "98 m/s²"], 0),
        ("Ohm's law relates:", ["force and mass", "voltage, current and resistance", "pressure and volume", "work and power"], 1),
        ("Which of these is a renewable energy source?", ["Coal", "Natural gas", "Solar", "Diesel"], 2),
        ("The work done when a 10 N force moves an object 5 m in its direction is:", ["2 J", "15 J", "50 J", "500 J"], 2),
    ],
}

FAQS = [
    ("parent", "How do you vet tutors?", "Every tutor passes an 11-stage check: NIN and selfie verification, bank account name match, credential review, a timed subject test, a video interview, two references, a guarantor, address verification, a police character certificate and safeguarding training."),
    ("parent", "How do I know the lesson actually happened?", "On lesson day your app shows a 6-digit check-in code and a check-out code. The tutor can only start and finish the lesson by entering them, so every lesson is timestamped. You also get the tutor's lesson note."),
    ("parent", "When is the tutor paid?", "Your payment is held safely by TutorBridge. A lesson is paid to the tutor only after it is confirmed — by you, or automatically 48 hours after it ends if you haven't raised a problem."),
    ("parent", "What if I need to cancel?", "Cancel at least 24 hours before and the full lesson fee goes back to your wallet. With less notice, 50% is paid to the tutor for their time."),
    ("parent", "What if the tutor isn't a good fit?", "Tell us after the trial and we'll find a replacement at no extra cost. Any unused package balance moves to the new tutor."),
    ("tutor", "How and when do I get paid?", "Every week. Confirmed lessons become cleared earnings, and we transfer them to your verified bank account in the weekly payout run."),
    ("tutor", "What does TutorBridge charge?", "A commission on each lesson — 20% as standard, falling as you reach Gold and Elite tiers through hours taught, ratings and reliability."),
    ("tutor", "Why can't I share my phone number with families?", "All contact stays on-platform so that our payment guarantee, dispute support and safety protections cover you. Messages are filtered for contact details."),
    ("general", "Which areas do you cover?", "We're launching in Lagos — Lekki, Ajah, Ikoyi, VI, Ikeja GRA, Magodo, Gbagada, Surulere and Yaba — with Abuja and Port Harcourt to follow."),
]


class Command(BaseCommand):
    help = "Seed levels, curricula, subjects, areas, starter question bank and FAQs"

    def handle(self, **opts):
        for i, (code, name, lo, hi) in enumerate(LEVELS):
            Level.objects.update_or_create(code=code, defaults={"name": name, "order": i, "min_rate_kobo": lo * N, "max_rate_kobo": hi * N})
        for code, name in CURRICULA:
            Curriculum.objects.get_or_create(code=code, defaults={"name": name})
        for name in SUBJECTS:
            Subject.objects.get_or_create(slug=slugify(name), defaults={"name": name})
        for state_name, lgas in AREAS.items():
            state, _ = State.objects.get_or_create(name=state_name)
            for lga_name, areas in lgas.items():
                lga, _ = LGA.objects.get_or_create(state=state, name=lga_name)
                for area_name, lat, lng in areas:
                    Area.objects.update_or_create(slug=slugify(area_name), defaults={"lga": lga, "name": area_name, "lat": lat, "lng": lng})

        from vetting.models import Question

        for (subject_slug, level_code), items in QUESTIONS.items():
            subject, level = Subject.objects.get(slug=subject_slug), Level.objects.get(code=level_code)
            for text, options, correct in items:
                Question.objects.get_or_create(subject=subject, level=level, text=text, defaults={"options": options, "correct_index": correct})

        from website.models import FAQ

        for i, (aud, q, a) in enumerate(FAQS):
            FAQ.objects.get_or_create(question=q, defaults={"audience": aud, "answer": a, "order": i})
        self.stdout.write(self.style.SUCCESS("Reference data loaded."))
