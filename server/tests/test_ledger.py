from django.test import TestCase

from core.money import percent_of, split_commission
from payments import ledger
from payments.models import AccountKind, LedgerEntry
from tests.factories import make_parent, make_tutor, seed


class MoneyTests(TestCase):
    def test_percent_rounds_half_up(self):
        self.assertEqual(percent_of(900_000, 20), 180_000)
        self.assertEqual(percent_of(1, 50), 1)  # 0.5 kobo rounds up
        self.assertEqual(percent_of(333, 20), 67)  # 66.6 → 67

    def test_split_is_exact(self):
        for amount in (1, 7, 999_999, 900_000, 123_457):
            for pct in (15, 18, 20, "17.5"):
                tutor, platform = split_commission(amount, pct)
                self.assertEqual(tutor + platform, amount)

    def test_prd_example_9000_naira_lesson(self):
        self.assertEqual(split_commission(900_000, 20), (720_000, 180_000))


class LedgerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()
        cls.parent, _ = make_parent()
        cls.tutor = make_tutor()

    def test_balanced_posting_and_balances(self):
        clearing, wallet = ledger.platform(AccountKind.GATEWAY_CLEARING), ledger.wallet(self.parent)
        ledger.transfer("t1", "payment", "pay", clearing, wallet, 900_000)
        self.assertEqual(ledger.balance(wallet), 900_000)
        self.assertEqual(ledger.balance(clearing), 900_000)  # debit-normal asset
        d, c = ledger.trial_balance()
        self.assertEqual(d, c)

    def test_unbalanced_rejected(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.post("bad", "x", "x", [(ledger.wallet(self.parent), 100, 0), (ledger.earnings(self.tutor), 0, 99)])

    def test_idempotent_reference(self):
        clearing, wallet = ledger.platform(AccountKind.GATEWAY_CLEARING), ledger.wallet(self.parent)
        _, created1 = ledger.transfer("same-ref", "payment", "pay", clearing, wallet, 500)
        _, created2 = ledger.transfer("same-ref", "payment", "pay", clearing, wallet, 500)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(ledger.balance(wallet), 500)

    def test_overdraft_protection(self):
        with self.assertRaises(ledger.InsufficientFunds):
            ledger.transfer("od", "x", "x", ledger.wallet(self.parent), ledger.earnings(self.tutor), 1)

    def test_entries_are_append_only(self):
        txn, _ = ledger.transfer("ao", "payment", "pay", ledger.platform(AccountKind.GATEWAY_CLEARING), ledger.wallet(self.parent), 100)
        entry = LedgerEntry.objects.filter(transaction=txn).first()
        entry.debit_kobo = 5
        with self.assertRaises(RuntimeError):
            entry.save()
        with self.assertRaises(RuntimeError):
            entry.delete()
        with self.assertRaises(RuntimeError):
            txn.delete()

    def test_negative_amounts_rejected(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.post("neg", "x", "x", [(ledger.wallet(self.parent), -5, 0), (ledger.earnings(self.tutor), 0, -5)])
