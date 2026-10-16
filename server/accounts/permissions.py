"""
AUTH-08: role-based access control with granular staff permissions.
Each role gets a default permission set; individual staff can be granted extras.
"""
from rest_framework.permissions import BasePermission

from accounts.models import Role

ROLE_PERMISSIONS = {
    Role.VETTING: {"vetting.view", "vetting.review", "vetting.decide", "users.view"},
    Role.OPS: {"requests.view", "requests.match", "bookings.view", "bookings.manage", "users.view", "messages.view"},
    Role.FINANCE: {
        "finance.view",
        "payouts.create",
        "payouts.approve",
        "refunds.process",
        "users.view",
        "reports.export",
        "promos.manage",
    },
    Role.SAFETY: {"safety.view", "safety.act", "disputes.view", "disputes.resolve", "users.view", "users.suspend", "messages.view"},
}

ALL_PERMISSIONS = set().union(*ROLE_PERMISSIONS.values()) | {"settings.manage", "staff.manage", "reviews.moderate", "audit.view"}


def role_permissions(role):
    if role == Role.SUPER:
        return ALL_PERMISSIONS
    return ROLE_PERMISSIONS.get(role, set())


class IsParent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == Role.PARENT


class IsTutor(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == Role.TUTOR


class IsVerifiedUser(BasePermission):
    """AUTH-02: email and phone must be verified before booking or applying."""

    message = "Verify your email and phone number first."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_verified


def staff_perm(code):
    """Permission class factory: staff member with 2FA enabled and the given permission code."""

    class _StaffPerm(BasePermission):
        message = "You do not have permission for this action."

        def has_permission(self, request, view):
            user = request.user
            if not (user.is_authenticated and user.is_staff_member):
                return False
            if not request.session.get("2fa_ok"):  # AUTH-06: staff must have passed 2FA this session
                self.message = "Two-factor authentication required."
                return False
            return user.has_perm_code(code)

    _StaffPerm.__name__ = f"StaffPerm_{code.replace('.', '_')}"
    return _StaffPerm
