"""ADM-06: staff content management for FAQs and blog posts."""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import staff_perm
from core.audit import audit
from website.models import FAQ, BlogPost

CanEdit = staff_perm("content.manage")


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ["id", "audience", "question", "answer", "order", "is_published"]


class BlogPostSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(required=False, allow_blank=True)

    class Meta:
        model = BlogPost
        fields = ["id", "slug", "title", "excerpt", "body", "is_published", "published_at", "created_at"]
        read_only_fields = ["published_at", "created_at"]

    def validate(self, attrs):
        title = attrs.get("title") or (self.instance.title if self.instance else "")
        slug = attrs.get("slug") or (self.instance.slug if self.instance else "") or slugify(title)[:50]
        if not slug:
            raise serializers.ValidationError({"slug": "Give the post a title or a URL slug."})
        clash = BlogPost.objects.filter(slug=slug)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            if attrs.get("slug"):
                raise serializers.ValidationError({"slug": "Another post already uses this URL."})
            base, n = slug, 2
            while BlogPost.objects.filter(slug=f"{base}-{n}").exists():
                n += 1
            slug = f"{base}-{n}"
        attrs["slug"] = slug
        # Set the publish date the first time a post goes live.
        if attrs.get("is_published") and not (self.instance and self.instance.published_at):
            attrs["published_at"] = timezone.now()
        return attrs


def _crud(request, model, serializer_cls, pk, entity):
    if pk is None:
        if request.method == "POST":
            s = serializer_cls(data=request.data)
            s.is_valid(raise_exception=True)
            obj = s.save()
            audit(request.user, f"{entity}.create", entity, obj.pk, after={"title": str(getattr(obj, "title", getattr(obj, "question", "")))[:100]}, request=request)
            return Response(serializer_cls(obj).data, status=201)
        return Response(serializer_cls(model.objects.all(), many=True).data)
    obj = get_object_or_404(model, pk=pk)
    if request.method == "DELETE":
        audit(request.user, f"{entity}.delete", entity, obj.pk, before={"title": str(getattr(obj, "title", getattr(obj, "question", "")))[:100]}, request=request)
        obj.delete()
        return Response(status=204)
    s = serializer_cls(obj, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    obj = s.save()
    audit(request.user, f"{entity}.update", entity, obj.pk, after={k: str(v)[:100] for k, v in request.data.items() if k != "body"}, request=request)
    return Response(serializer_cls(obj).data)


@api_view(["GET", "POST"])
@permission_classes([CanEdit])
def faqs(request):
    return _crud(request, FAQ, FAQSerializer, None, "faq")


@api_view(["PATCH", "DELETE"])
@permission_classes([CanEdit])
def faq_detail(request, pk):
    return _crud(request, FAQ, FAQSerializer, pk, "faq")


@api_view(["GET", "POST"])
@permission_classes([CanEdit])
def posts(request):
    return _crud(request, BlogPost, BlogPostSerializer, None, "blog_post")


@api_view(["PATCH", "DELETE"])
@permission_classes([CanEdit])
def post_detail(request, pk):
    return _crud(request, BlogPost, BlogPostSerializer, pk, "blog_post")
