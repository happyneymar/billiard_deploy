from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from diary.models import Moment, MomentComment


class MomentCommentTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="higgins", password="pass12345")
        self.reply_target = User.objects.create_user(username="Wizard", password="pass12345")
        self.moment = Moment.objects.create(user=self.author, text="我是巫师")

    def test_reply_to_comment_prefixes_target_username(self):
        self.client.force_login(self.author)

        response = self.client.post(
            reverse("diary:moment_comment", kwargs={"pk": self.moment.pk}),
            {"text": "你好", "reply_to_username": self.reply_target.username},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        comment = MomentComment.objects.get()
        self.assertEqual(comment.text, "回复Wizard: 你好")
        self.assertEqual(response.json()["comment"]["text"], "回复Wizard: 你好")

    def test_comment_username_links_to_public_profile(self):
        MomentComment.objects.create(
            moment=self.moment,
            user=self.reply_target,
            text="我是Wizard",
        )
        self.client.force_login(self.author)

        response = self.client.get(reverse("diary:moments"))

        self.assertContains(
            response,
            reverse("diary:public_profile", kwargs={"username": self.reply_target.username}),
        )
        self.assertContains(response, "data-reply-username=\"Wizard\"")

    def test_profile_from_moments_returns_to_moment_anchor(self):
        self.client.force_login(self.author)

        response = self.client.get(
            reverse("diary:public_profile", kwargs={"username": self.reply_target.username}),
            {"from": "moments", "moment": str(self.moment.pk)},
        )

        self.assertContains(response, "返回朋友圈")
        self.assertContains(response, f"{reverse('diary:moments')}#moment-{self.moment.pk}")
        self.assertNotContains(response, "返回我的记录")

    def test_profile_from_search_keeps_record_back_button(self):
        self.client.force_login(self.author)

        response = self.client.get(
            reverse("diary:public_profile", kwargs={"username": self.reply_target.username})
        )

        self.assertContains(response, "返回我的记录")
        self.assertContains(response, reverse("diary:record_list"))
        self.assertNotContains(response, "返回朋友圈")

    def test_posting_moment_redirects_to_top_marker(self):
        self.client.force_login(self.author)

        response = self.client.post(reverse("diary:moments"), {"text": "新朋友圈"})

        self.assertRedirects(
            response,
            f"{reverse('diary:moments')}?posted=1#moments-top",
            fetch_redirect_response=False,
        )
