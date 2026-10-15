"""PDF documents: receipts (PAY-07), earnings statements (OUT-06), progress reports (LSN-06)."""
import calendar
import io
from datetime import date

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BRAND = colors.HexColor("#0f5132")


def _ngn(kobo):
    # Built-in PDF fonts have no ₦ glyph; use the ISO code.
    return f"NGN {kobo / 100:,.2f}"


def _doc(title, story_fn):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title=title)
    styles = getSampleStyleSheet()
    styles["Title"].textColor = BRAND
    story = [Paragraph("TutorBridge", styles["Title"]), Paragraph(title, styles["Heading2"]), Spacer(1, 6 * mm)]
    story += story_fn(styles)
    story += [Spacer(1, 10 * mm), Paragraph(f"Generated {timezone.localtime():%d %b %Y %H:%M} WAT", styles["Italic"])]
    doc.build(story)
    return buf.getvalue()


def _table(rows, widths=None):
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7f5")]),
    ]))
    return t


def receipt_pdf(payment):
    def story(styles):
        p = payment
        rows = [
            ["Item", "Detail"],
            ["Receipt number", p.reference],
            ["Date", f"{timezone.localtime(p.verified_at or p.created_at):%d %b %Y %H:%M}"],
            ["Paid by", p.parent.user.get_full_name()],
            ["Email", p.parent.user.email],
            ["Payment method", (p.channel or p.gateway).title()],
            ["Amount", _ngn(p.amount_kobo)],
            ["Status", p.get_status_display()],
        ]
        if p.booking_id:
            b = p.booking
            rows += [
                ["Booking", f"#{b.pk} — {b.package_size} lesson(s) x {b.lesson_minutes} min for {b.child.first_name}"],
                ["Lessons subtotal", _ngn(b.lesson_price_kobo * b.package_size)],
            ]
            if b.matching_fee_kobo:
                rows.append(["Matching fee", _ngn(b.matching_fee_kobo)])
            if b.matching_credit_kobo:
                rows.append(["Matching fee credit", "-" + _ngn(b.matching_credit_kobo)])
        return [_table(rows, [50 * mm, 120 * mm])]

    return _doc("Payment receipt", story)


def statement_pdf(tutor, year, month):
    from bookings.models import Lesson, LessonStatus
    from core.money import split_commission
    from payments.models import PayoutItem

    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])

    def story(styles):
        lessons = Lesson.objects.filter(tutor=tutor, confirmed_at__date__gte=start, confirmed_at__date__lte=end, status=LessonStatus.CONFIRMED).select_related("booking__child")
        rows = [["Date", "Student", "Hours", "Lesson value", "Commission", "Your earnings"]]
        tot_gross = tot_net = 0
        for l in lessons:
            net, comm = split_commission(l.amount_kobo, l.booking.commission_pct)
            tot_gross += l.amount_kobo
            tot_net += net
            rows.append([f"{timezone.localtime(l.scheduled_start):%d %b}", l.booking.child.first_name, f"{l.duration_hours:.1f}", _ngn(l.amount_kobo), _ngn(comm), _ngn(net)])
        rows.append(["Total", "", "", _ngn(tot_gross), _ngn(tot_gross - tot_net), _ngn(tot_net)])
        payouts = PayoutItem.objects.filter(tutor=tutor, status=PayoutItem.Status.SUCCESS, updated_at__date__gte=start, updated_at__date__lte=end)
        prow = [["Payout date", "Bank", "Amount"]] + [[f"{timezone.localtime(p.updated_at):%d %b %Y}", f"{p.bank_snapshot.get('bank_name')} ****{p.bank_snapshot.get('last4')}", _ngn(p.amount_kobo)] for p in payouts]
        return [
            Paragraph(f"{tutor.user.get_full_name()} — {start:%B %Y}", styles["Normal"]), Spacer(1, 4 * mm),
            _table(rows), Spacer(1, 8 * mm), Paragraph("Payouts", styles["Heading3"]), _table(prow),
        ]

    return _doc("Monthly earnings statement", story)


def progress_report_pdf(booking, year, month):
    from bookings.models import LessonStatus

    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])

    def story(styles):
        lessons = booking.lessons.filter(scheduled_start__date__gte=start, scheduled_start__date__lte=end).order_by("scheduled_start")
        attended = [l for l in lessons if l.checkin_at]
        on_time = [l for l in attended if l.late_minutes <= 10]
        summary = [
            ["Student", f"{booking.child.first_name} ({booking.child.class_name})"],
            ["Tutor", booking.tutor.user.display_name],
            ["Subjects", ", ".join(s.name for s in booking.subjects.all())],
            ["Lessons scheduled", str(len(lessons))],
            ["Lessons delivered", str(len(attended))],
            ["On time", f"{len(on_time)} of {len(attended)}"],
            ["Missed / cancelled", str(sum(1 for l in lessons if l.status in (LessonStatus.NO_SHOW, LessonStatus.CANCELLED)))],
        ]
        body = styles["BodyText"]
        notes = [["Date", "Topics covered", "Homework", "Observations"]] + [
            [f"{timezone.localtime(l.scheduled_start):%d %b}", Paragraph(l.note_topics or "-", body), Paragraph(l.note_homework or "-", body), Paragraph(l.note_observations or "-", body)]
            for l in attended
        ]
        return [
            Paragraph(f"{start:%B %Y}", styles["Normal"]), Spacer(1, 4 * mm),
            _table([["Summary", ""]] + summary, [50 * mm, 120 * mm]), Spacer(1, 8 * mm),
            Paragraph("Lesson notes", styles["Heading3"]), _table(notes, [18 * mm, 55 * mm, 45 * mm, 56 * mm]),
        ]

    return _doc("Monthly progress report", story)
