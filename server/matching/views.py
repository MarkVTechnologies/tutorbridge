from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsParent, IsTutor, IsVerifiedUser
from core import config
from matching.engine import run_matching
from matching.models import LessonRequest, Match, MatchStatus, RequestStatus
from matching.serializers import LessonRequestSerializer, ShortlistItemSerializer


class LessonRequestViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = LessonRequestSerializer

    def get_permissions(self):
        perms = [IsParent()]
        if self.action == "create":
            perms.append(IsVerifiedUser())
        return perms

    def get_queryset(self):
        return LessonRequest.objects.filter(parent=self.request.user.parent_profile).select_related("child", "area").prefetch_related("subjects")

    def perform_create(self, serializer):
        req = serializer.save(parent=self.request.user.parent_profile, sla_due_at=timezone.now() + timedelta(hours=config.get("request_sla_hours")))
        run_matching(req)

    @action(detail=True)
    def shortlist(self, request, pk=None):
        req = self.get_object()
        if not req.shortlist_published_at:
            return Response({"published": False, "items": []})
        items = req.matches.filter(in_shortlist=True).exclude(status__in=[MatchStatus.WITHDRAWN, MatchStatus.DECLINED]).select_related("tutor__user").order_by("rank")
        return Response({"published": True, "items": ShortlistItemSerializer(items, many=True).data})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        req = self.get_object()
        req.status = RequestStatus.CLOSED
        req.save(update_fields=["status"])
        return Response(self.get_serializer(req).data)


# --- Tutor invitations (REQ-07) -------------------------------------------


@api_view(["GET"])
@permission_classes([IsTutor])
def invitations(request):
    tutor = request.user.tutor_profile
    qs = Match.objects.filter(tutor=tutor, status__in=[MatchStatus.INVITED, MatchStatus.ACCEPTED]).select_related("request__child__level", "request__area").prefetch_related("request__subjects")
    out = []
    for m in qs:
        r = m.request
        out.append({
            "id": m.pk, "status": m.status, "subjects": [s.name for s in r.subjects.all()], "level": r.child.level.name,
            "class_name": r.child.class_name, "area": r.area.name, "schedule": r.schedule, "lesson_minutes": r.lesson_minutes,
            "start_date": r.start_date, "goals": r.goals, "is_online": r.is_online, "special_needs": r.child.special_needs,
        })
    return Response(out)


@api_view(["POST"])
@permission_classes([IsTutor])
def respond_invitation(request, pk):
    m = get_object_or_404(Match, pk=pk, tutor=request.user.tutor_profile, status=MatchStatus.INVITED)
    accept = bool(request.data.get("accept"))
    reason = (request.data.get("reason") or "").strip()
    if not accept and not reason:
        return Response({"reason": "Please give a reason so we can match better next time."}, status=400)
    m.status = MatchStatus.ACCEPTED if accept else MatchStatus.DECLINED
    m.decline_reason, m.responded_at = reason[:255], timezone.now()
    if not accept:
        m.in_shortlist = False
    m.save()
    return Response({"status": m.status})
