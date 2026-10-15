from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsParent
from parents.serializers import ChildSerializer, ParentProfileSerializer


@api_view(["GET", "PATCH"])
@permission_classes([IsParent])
def profile(request):
    p = request.user.parent_profile
    if request.method == "PATCH":
        s = ParentProfileSerializer(p, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
    return Response(ParentProfileSerializer(p).data)


class ChildViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = ChildSerializer
    permission_classes = [IsParent]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        return self.request.user.parent_profile.children.filter(is_active=True).select_related("level", "curriculum")

    def perform_create(self, serializer):
        serializer.save(parent=self.request.user.parent_profile)

    def destroy(self, request, *args, **kwargs):
        child = self.get_object()
        child.is_active = False  # soft-delete: bookings and lesson history must stay intact
        child.save(update_fields=["is_active"])
        return Response(status=204)
