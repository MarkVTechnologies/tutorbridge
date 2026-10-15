"""
Admin-configurable business settings (section 3.2: every fee and percentage
must be configurable without code changes). Values live in the Setting table;
DEFAULTS apply until an administrator overrides them.
"""
from django.core.cache import cache

DEFAULTS = {
    # Revenue
    "commission_pct_standard": 20,
    "commission_pct_by_tier": {"verified": 20, "gold": 18, "elite": 15},
    "matching_fee_kobo": 500_000,  # ₦5,000, credited against first package
    "vetting_fee_kobo": 500_000,
    "vetting_fee_deduct_from_earnings": True,
    "pass_gateway_fee_to_parent": False,
    # Packages & booking
    "package_sizes": [1, 4, 8, 12, 24],
    "lesson_durations_minutes": [60, 90, 120],
    "booking_accept_hours": 12,  # BKG-03
    "travel_buffer_minutes": 30,  # BKG-02
    # Lessons & disputes (section 4.4)
    "dispute_window_hours": 48,
    "late_cancel_notice_hours": 24,
    "late_cancel_tutor_pct": 50,
    "late_arrival_minutes": 15,
    "no_show_minutes": 45,
    "strikes_for_review": 3,
    # Payouts
    "payout_min_kobo": 500_000,
    "bank_change_hold_hours": 48,
    # Vetting
    "test_pass_mark_pct": 70,
    "test_duration_minutes": 30,
    "reverification_months": 12,
    # Matching (section 12)
    "match_weights": {
        "availability": 25,
        "distance": 20,
        "rating": 20,
        "reliability": 15,
        "rate_fit": 10,
        "test_score": 10,
    },
    "match_min_availability_pct": 80,
    "match_shortlist_size": 3,
    "new_tutor_boost": 8,
    "new_tutor_boost_lessons": 10,
    "request_sla_hours": 24,
    # Tiers (TUT-15)
    "tier_rules": {
        "gold": {"min_hours": 100, "min_rating": 4.5, "min_reliability": 85},
        "elite": {"min_hours": 300, "min_rating": 4.8, "min_reliability": 95},
    },
    # Payments
    "active_gateway": "paystack",
}

CACHE_PREFIX = "setting:"


def get(key):
    from core.models import Setting

    cached = cache.get(CACHE_PREFIX + key)
    if cached is not None:
        return cached
    row = Setting.objects.filter(key=key).first()
    value = row.value if row else DEFAULTS.get(key)
    cache.set(CACHE_PREFIX + key, value, 300)
    return value


def set_value(key, value, user=None):
    from core.audit import audit
    from core.models import Setting

    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting {key}")
    before = get(key)
    Setting.objects.update_or_create(key=key, defaults={"value": value, "updated_by": user})
    cache.delete(CACHE_PREFIX + key)
    audit(user, "setting.update", "setting", key, before={"value": before}, after={"value": value})


def all_settings():
    return {key: get(key) for key in DEFAULTS}
