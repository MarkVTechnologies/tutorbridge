"""ADM-06: staff content management."""
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Role
from core.models import AuditLog
from tests.factories import make_parent, make_staff, seed, staff_client
from website.models import FAQ, BlogPost


class ContentManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.c = staff_client(APIClient(), make_staff(Role.OPS))

    def test_faq_crud_and_public_visibility(self):
        r = self.c.post("/api/staff/content/faqs/", {"audience": "parent", "question": "Do you cover Ikorodu?", "answer": "Yes.", "order": 1}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        fid = r.json()["id"]
        self.assertIn("Do you cover Ikorodu?", str(APIClient().get("/api/faqs/").json()))
        self.c.patch(f"/api/staff/content/faqs/{fid}/", {"is_published": False}, format="json")
        self.assertNotIn("Do you cover Ikorodu?", str(APIClient().get("/api/faqs/").json()))
        self.assertEqual(self.c.delete(f"/api/staff/content/faqs/{fid}/").status_code, 204)
        self.assertFalse(FAQ.objects.filter(pk=fid).exists())
        self.assertTrue(AuditLog.objects.filter(action="faq.delete").exists())

    def test_blog_slug_publish_and_public(self):
        r = self.c.post("/api/staff/content/posts/", {"title": "WAEC countdown: 8 weeks to go", "excerpt": "Plan", "body": "## Week 1\n\nStart early."}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        post = r.json()
        self.assertEqual(post["slug"], "waec-countdown-8-weeks-to-go")
        self.assertIsNone(post["published_at"])
        self.assertEqual(APIClient().get(f"/api/blog/{post['slug']}/").status_code, 404)  # drafts are private
        published = self.c.patch(f"/api/staff/content/posts/{post['id']}/", {"is_published": True}, format="json").json()
        self.assertIsNotNone(published["published_at"])
        self.assertEqual(APIClient().get(f"/api/blog/{post['slug']}/").json()["title"], "WAEC countdown: 8 weeks to go")
        # Same title again gets a unique slug; an explicit clashing slug is rejected.
        again = self.c.post("/api/staff/content/posts/", {"title": "WAEC countdown: 8 weeks to go", "body": "x"}, format="json").json()
        self.assertEqual(again["slug"], "waec-countdown-8-weeks-to-go-2")
        clash = self.c.post("/api/staff/content/posts/", {"title": "Other", "slug": "waec-countdown-8-weeks-to-go", "body": "x"}, format="json")
        self.assertEqual(clash.status_code, 400)
        # Re-publishing keeps the original publish date.
        self.c.patch(f"/api/staff/content/posts/{post['id']}/", {"is_published": False}, format="json")
        again_pub = self.c.patch(f"/api/staff/content/posts/{post['id']}/", {"is_published": True}, format="json").json()
        self.assertEqual(again_pub["published_at"], published["published_at"])
        self.assertEqual(BlogPost.objects.count(), 2)

    def test_permissions(self):
        fin = staff_client(APIClient(), make_staff(Role.FINANCE))
        self.assertEqual(fin.get("/api/staff/content/faqs/").status_code, 403)
        parent, _ = make_parent()
        p = APIClient()
        p.force_login(parent.user)
        self.assertEqual(p.post("/api/staff/content/posts/", {"title": "x", "body": "x"}, format="json").status_code, 403)
