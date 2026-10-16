from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from backoffice import views as bo
from bookings import views as bookings
from matching import views as matching
from messaging import views as messaging
from parents import views as parents
from payments import views as payments
from trust import views as trust
from tutors import views as tutors
from vetting import views as vetting
from website import views as website

router = DefaultRouter(trailing_slash=True)
router.register("parent/children", parents.ChildViewSet, basename="children")
router.register("requests", matching.LessonRequestViewSet, basename="requests")
router.register("bookings", bookings.BookingViewSet, basename="bookings")
router.register("lessons", bookings.LessonViewSet, basename="lessons")


def health(request):
    from django.db import connection
    from django.utils import timezone

    from core.models import CronHeartbeat

    with connection.cursor() as c:
        c.execute("SELECT 1")
    hb = CronHeartbeat.objects.filter(name="process_jobs").values_list("last_finished_at", flat=True).first()
    cron_ok = bool(hb and (timezone.now() - hb).total_seconds() < 600)
    return JsonResponse({"db": "ok", "cron_ok": cron_ok, "cron_last_run": hb}, status=200 if cron_ok or settings.DEBUG else 503)


def spa(request, path=""):
    """Serve the compiled React client for any non-API route (production: client/dist)."""
    index = settings.CLIENT_DIST_DIR / "index.html"
    if not index.exists():
        raise Http404("Client not built. Run `npm run build` in client/.")
    return FileResponse(open(index, "rb"), content_type="text/html")


def service_worker(request):
    """The PWA service worker must be served from the site root to control every page."""
    sw = settings.CLIENT_DIST_DIR / "sw.js"
    if not sw.exists():
        raise Http404
    resp = FileResponse(open(sw, "rb"), content_type="application/javascript")
    resp["Cache-Control"] = "no-cache"
    return resp


api = [
    path("auth/", include("accounts.urls")),
    path("health/", health),
    # Public website & reference data
    path("ref/", website.reference_data),
    path("faqs/", website.faqs),
    path("blog/", website.blog),
    path("blog/<slug:slug>/", website.blog_post),
    path("contact/", website.contact),
    path("seo/", website.seo_index),
    path("seo/<slug:subject_slug>/<slug:area_slug>/", website.seo_page),
    # Parent
    path("parent/profile/", parents.profile),
    # Tutors
    path("tutors/", tutors.search),
    path("tutors/<int:pk>/", tutors.public_profile),
    path("tutors/<int:pk>/photo/", tutors.photo),
    path("tutor/profile/", tutors.my_profile),
    path("tutor/profile/photo/", tutors.upload_photo),
    path("tutor/profile/subjects/", tutors.set_subjects),
    path("tutor/profile/areas/", tutors.set_areas),
    path("tutor/profile/availability/", tutors.set_availability),
    path("tutor/blocked-dates/", tutors.BlockedDateList.as_view()),
    path("tutor/blocked-dates/<int:pk>/", tutors.BlockedDateDetail.as_view()),
    path("tutor/submit/", tutors.submit),
    path("tutor/invitations/", matching.invitations),
    path("tutor/invitations/<int:pk>/respond/", matching.respond_invitation),
    # Vetting (tutor side)
    path("vetting/documents/", vetting.documents),
    path("vetting/documents/<int:pk>/", vetting.delete_document),
    path("vetting/documents/<int:pk>/file/", vetting.download_document),
    path("vetting/identity/", vetting.identity),
    path("vetting/tests/", vetting.tests),
    path("vetting/tests/start/", vetting.start_test),
    path("vetting/tests/<int:pk>/submit/", vetting.submit_test),
    path("vetting/interview-slots/", vetting.interview_slots),
    path("vetting/interview-slots/<int:pk>/book/", vetting.book_interview),
    path("vetting/references/", vetting.references),
    path("vetting/reference-form/<str:token>/", vetting.reference_form),
    path("vetting/safeguarding/", vetting.safeguarding),
    # Bookings
    path("bookings-quote/", bookings.quote),
    # Payments
    path("payments/", payments.payments_list),
    path("payments/topup/", payments.topup),
    path("payments/dev/fake-complete/", payments.fake_complete),
    path("payments/webhooks/<str:gateway>/", payments.webhook),
    path("payments/<str:reference>/", payments.payment_status),
    path("payments/<str:reference>/receipt/", payments.receipt),
    path("wallet/", payments.wallet),
    path("saved-cards/<int:pk>/", payments.remove_saved_card),
    path("earnings/", payments.earnings),
    path("earnings/statement/", payments.statement),
    path("banks/", payments.banks),
    path("bank-account/", payments.bank_account),
    path("bank-account/otp/", payments.bank_change_otp),
    # Messaging & notifications
    path("threads/", messaging.threads),
    path("threads/<int:pk>/messages/", messaging.messages),
    path("notifications/", messaging.notifications),
    path("notifications/read/", messaging.notifications_read),
    # Trust
    path("reviews/", trust.reviews),
    path("incidents/", trust.incident),
    path("disputes/", trust.my_disputes),
    # Staff console
    path("staff/dashboard/", bo.dashboard),
    path("staff/vetting/", bo.vetting_queue),
    path("staff/vetting/<int:pk>/", bo.vetting_detail),
    path("staff/vetting/<int:pk>/check/", bo.vetting_check),
    path("staff/vetting/<int:pk>/decision/", bo.vetting_decision),
    path("staff/documents/<int:pk>/review/", bo.review_document),
    path("staff/references/<int:pk>/verify/", bo.reference_verify),
    path("staff/interview-slots/", bo.interview_slots),
    path("staff/interview-slots/<int:pk>/outcome/", bo.interview_outcome),
    path("staff/questions/", bo.questions),
    path("staff/questions/<int:pk>/", bo.question_detail),
    path("staff/requests/", bo.requests_list),
    path("staff/requests/<int:pk>/", bo.request_detail),
    path("staff/requests/<int:pk>/rematch/", bo.request_rematch),
    path("staff/requests/<int:pk>/add-tutor/", bo.request_add_tutor),
    path("staff/requests/<int:pk>/publish/", bo.request_publish),
    path("staff/matches/<int:pk>/", bo.match_update),
    path("staff/matches/<int:pk>/invite/", bo.match_invite),
    path("staff/bookings/", bo.bookings_list),
    path("staff/bookings/<int:pk>/", bo.booking_detail),
    path("staff/bookings/<int:pk>/<str:op>/", bo.booking_action),
    path("staff/lessons/<int:pk>/no-show/", bo.lesson_no_show),
    path("staff/lessons/<int:pk>/unlock-codes/", bo.lesson_unlock_codes),
    path("staff/finance/", bo.finance_summary),
    path("staff/finance/payments/", bo.finance_payments),
    path("staff/finance/reconcile/", bo.run_reconciliation),
    path("staff/payouts/", bo.payouts),
    path("staff/payouts/<int:pk>/", bo.payout_detail),
    path("staff/payouts/<int:pk>/approve/", bo.payout_approve),
    path("staff/payout-items/<int:pk>/<str:op>/", bo.payout_item_action),
    path("staff/parents/<int:parent_id>/wallet-refund/", bo.wallet_refund),
    path("staff/incidents/", bo.incidents),
    path("staff/incidents/<int:pk>/", bo.incident_update),
    path("staff/disputes/", bo.disputes),
    path("staff/disputes/<int:pk>/", bo.dispute_action),
    path("staff/users/", bo.users_list),
    path("staff/users/<int:pk>/", bo.user_detail),
    path("staff/users/<int:pk>/suspend/", bo.user_suspend),
    path("staff/tutors/<int:tutor_id>/strikes/", bo.strike_add),
    path("staff/threads/<int:pk>/", bo.thread_view),
    path("staff/flagged-messages/", bo.flagged_messages),
    path("staff/reviews/", bo.reviews_list),
    path("staff/reviews/<int:pk>/visibility/", bo.review_visibility),
    path("staff/staff-accounts/", bo.staff_accounts),
    path("staff/staff-accounts/<int:pk>/", bo.staff_update),
    path("staff/settings/", bo.settings_view),
    path("staff/levels/<int:pk>/", bo.level_update),
    path("staff/subjects/", bo.subject_create),
    path("staff/areas/", bo.area_create),
    path("staff/audit/", bo.audit_log),
    path("staff/exports/<str:name>/", bo.export_csv),
    path("", include(router.urls)),
]

urlpatterns = [
    path("api/", include(api)),
    path("sw.js", service_worker),
    re_path(r"^(?!api/|static/).*$", spa),
]
