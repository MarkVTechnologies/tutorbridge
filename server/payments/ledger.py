"""
Append-only double-entry ledger (PAY-03, section 14).

- Every movement is a LedgerTransaction with balanced LedgerEntry rows.
- `reference` makes each posting idempotent: posting the same reference twice is a no-op.
- Balances are always derived from entries; nothing stores a running balance.
- Postings run inside a DB transaction and lock the affected accounts (SELECT ... FOR UPDATE).
"""
from django.db import transaction
from django.db.models import Sum

from payments.models import DEBIT_NORMAL, AccountKind, LedgerAccount, LedgerEntry, LedgerTransaction


class LedgerError(Exception):
    pass


class InsufficientFunds(LedgerError):
    pass


def account(kind, parent=None, tutor=None, booking=None):
    acc, _ = LedgerAccount.objects.get_or_create(kind=kind, parent=parent, tutor=tutor, booking=booking)
    return acc


def platform(kind):
    return account(kind)


def wallet(parent):
    return account(AccountKind.PARENT_WALLET, parent=parent)


def escrow(booking):
    return account(AccountKind.ESCROW, booking=booking)


def earnings(tutor):
    return account(AccountKind.TUTOR_EARNINGS, tutor=tutor)


def balance(acc) -> int:
    totals = LedgerEntry.objects.filter(account=acc).aggregate(d=Sum("debit_kobo"), c=Sum("credit_kobo"))
    d, c = totals["d"] or 0, totals["c"] or 0
    return d - c if acc.kind in DEBIT_NORMAL else c - d


# Accounts that must never go below zero.
NON_NEGATIVE = {AccountKind.PARENT_WALLET, AccountKind.ESCROW, AccountKind.TUTOR_EARNINGS, AccountKind.PAYOUTS_IN_TRANSIT}


def post(reference, kind, description, lines, user=None, **links):
    """
    lines: list of (account, debit_kobo, credit_kobo). Returns (transaction, created).
    """
    if not lines:
        raise LedgerError("No lines")
    total_d = sum(int(d) for _, d, _ in lines)
    total_c = sum(int(c) for _, _, c in lines)
    if total_d != total_c:
        raise LedgerError(f"Unbalanced transaction {reference}: {total_d} != {total_c}")
    if total_d <= 0:
        raise LedgerError("Transaction amount must be positive")
    if any(int(d) < 0 or int(c) < 0 for _, d, c in lines):
        raise LedgerError("Negative amounts are not allowed; post a reversing transaction instead")

    with transaction.atomic():
        existing = LedgerTransaction.objects.filter(reference=reference).first()
        if existing:
            return existing, False
        ids = sorted({acc.pk for acc, _, _ in lines})
        list(LedgerAccount.objects.select_for_update().filter(pk__in=ids).order_by("pk"))  # lock in stable order

        # Overdraft protection on accounts that hold someone's money.
        net = {}
        for acc, d, c in lines:
            delta = (d - c) if acc.kind in DEBIT_NORMAL else (c - d)
            net[acc] = net.get(acc, 0) + delta
        for acc, delta in net.items():
            if acc.kind in NON_NEGATIVE and delta < 0 and balance(acc) + delta < 0:
                raise InsufficientFunds(f"Insufficient balance in {acc}")

        txn = LedgerTransaction.objects.create(reference=reference, kind=kind, description=description[:255], created_by=user, **links)
        LedgerEntry.objects.bulk_create(
            [LedgerEntry(transaction=txn, account=acc, debit_kobo=int(d), credit_kobo=int(c)) for acc, d, c in lines if d or c]
        )
        return txn, True


def transfer(reference, kind, description, debit_acc, credit_acc, amount, user=None, **links):
    """Two-line posting: debit one account, credit another."""
    return post(reference, kind, description, [(debit_acc, amount, 0), (credit_acc, 0, amount)], user=user, **links)


def trial_balance():
    """Sum of all debits must equal sum of all credits."""
    t = LedgerEntry.objects.aggregate(d=Sum("debit_kobo"), c=Sum("credit_kobo"))
    return (t["d"] or 0), (t["c"] or 0)
