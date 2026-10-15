"""
Real concurrency against MySQL/MariaDB (skipped on SQLite, which serialises writers).

Each test races two threads, each with its own DB connection, through the same
critical section and checks that the database-level locking keeps money and
schedules consistent.
"""
import threading
import time
import unittest
from unittest import mock

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from bookings import services as bs
from bookings.models import Booking, Lesson, LessonStatus
from core.models import Subject
from payments import ledger
from payments.models import AccountKind
from tests.factories import fund_wallet, make_parent, make_tutor, next_weekday, seed


def race(fn, n=2):
    """Run fn(i) in n threads released at the same instant; return list of results or exceptions."""
    barrier = threading.Barrier(n)
    results = [None] * n

    def worker(i):
        close_old_connections()
        try:
            barrier.wait()
            results[i] = fn(i)
        except Exception as e:  # noqa: BLE001
            results[i] = e
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


@unittest.skipIf(connection.vendor == "sqlite", "needs a real database server with row locks")
@override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
class ConcurrencyTests(TransactionTestCase):
    def setUp(self):
        seed()

    def test_two_debits_cannot_overdraw_wallet(self):
        parent, _ = make_parent()
        fund_wallet(parent, 600_000)
        tutor = make_tutor()
        earn = ledger.earnings(tutor)
        wallet = ledger.wallet(parent)

        def spend(i):
            return ledger.transfer(f"race-spend-{i}", "test", "race", wallet, earn, 500_000)

        results = race(spend)
        ok = [r for r in results if not isinstance(r, Exception)]
        failed = [r for r in results if isinstance(r, ledger.InsufficientFunds)]
        self.assertEqual((len(ok), len(failed)), (1, 1), results)
        self.assertEqual(ledger.balance(wallet), 100_000)

    def test_same_reference_posted_once(self):
        parent, _ = make_parent()
        clearing = ledger.platform(AccountKind.GATEWAY_CLEARING)
        wallet = ledger.wallet(parent)
        results = race(lambda i: ledger.transfer("webhook-dup", "payment", "dup", clearing, wallet, 900_000), n=3)
        self.assertFalse([r for r in results if isinstance(r, Exception) and not _is_dup(r)], results)
        self.assertEqual(ledger.balance(wallet), 900_000)

    def test_two_parents_cannot_book_the_same_tutor_slot(self):
        tutor = make_tutor()
        maths = Subject.objects.get(slug="mathematics")
        families = [make_parent() for _ in range(2)]
        for p, _ in families:
            fund_wallet(p, 10_000_000)
        start = next_weekday(2)

        def book(i):
            parent, child = families[i]
            return bs.create_booking(parent=parent, tutor=tutor, child=child, subjects=[maths], package_size=1, lesson_minutes=60,
                                     schedule=[{"weekday": 2, "start": "16:00"}], start_date=start)

        from core import config

        config.all_settings()  # warm the settings cache, as in production; a cold cache write happens to serialise requests
        real = bs.find_conflicts

        def slow_find_conflicts(*a, **k):
            out = real(*a, **k)
            time.sleep(0.5)  # widen the check-then-insert window so both threads are inside it together
            return out

        with mock.patch.object(bs, "find_conflicts", slow_find_conflicts):
            results = race(book)
        created = [r for r in results if isinstance(r, Booking)]
        self.assertEqual(len(created), 1, results)
        self.assertEqual(Lesson.objects.filter(tutor=tutor, status=LessonStatus.SCHEDULED).count(), 1)
        loser = next(r for r in results if not isinstance(r, Booking))
        self.assertIn("already booked", str(loser))  # rejected by the conflict check, not by a deadlock or error

    def test_lesson_released_once_under_concurrent_confirms(self):
        from tests.factories import deliver, make_active_booking

        parent, child = make_parent()
        tutor = make_tutor(rate_kobo=600_000)
        booking = make_active_booking(parent, child, tutor, package_size=1)
        lesson = deliver(booking.lessons.get(), tutor)
        race(lambda i: bs.confirm_lesson(Lesson.objects.get(pk=lesson.pk), auto=True), n=3)
        self.assertEqual(ledger.balance(ledger.earnings(tutor)), 480_000)
        tutor.refresh_from_db()
        self.assertEqual(tutor.lessons_completed, 1)


def _is_dup(e):
    # The losing thread of a duplicate-reference race may see the unique-constraint violation.
    from django.db import IntegrityError

    return isinstance(e, IntegrityError)
