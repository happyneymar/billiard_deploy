from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from diary.models import BattleRequest, BattleResponse, Moment, MomentComment


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

    def test_main_moments_feed_uses_fixed_publish_topbar(self):
        self.client.force_login(self.author)

        response = self.client.get(reverse("diary:moments"))

        self.assertContains(response, "moments-fixed-topbar")
        self.assertContains(response, "data-toggle-composer")
        self.assertContains(response, "id=\"moments-composer\"")
        self.assertContains(response, "display:none")

    def test_main_moments_feed_sets_scroll_offset_for_fixed_topbar(self):
        self.client.force_login(self.author)

        response = self.client.get(reverse("diary:moments"))

        self.assertContains(response, "scroll-padding-top: 78px")
        self.assertContains(response, "scroll-margin-top: 78px")
        self.assertContains(response, "scrollToWithMomentsOffset")


class BattleViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="player1", password="pass12345")
        self.other = User.objects.create_user(username="player2", password="pass12345")
        self.now = timezone.now()

    def test_battles_page_hides_finished_battles_and_shows_future_battles(self):
        BattleRequest.objects.create(
            user=self.other,
            battle_time=self.now - timedelta(hours=1),
            location="过去球厅",
            player_count=1,
        )
        BattleRequest.objects.create(
            user=self.other,
            battle_time=self.now + timedelta(hours=1),
            location="未来球厅",
            player_count=1,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("diary:battles"))

        self.assertContains(response, "未来球厅")
        self.assertNotContains(response, "过去球厅")
        self.assertContains(response, reverse("diary:battle_history"))
        self.assertContains(response, "约战记录")

    def test_battle_history_lists_finished_battles_i_created_or_joined(self):
        created_by_me = BattleRequest.objects.create(
            user=self.user,
            battle_time=self.now - timedelta(days=1),
            location="我发起的过去约战",
            player_count=1,
        )
        joined_by_me = BattleRequest.objects.create(
            user=self.other,
            battle_time=self.now - timedelta(days=2),
            location="我应战的过去约战",
            player_count=1,
        )
        BattleResponse.objects.create(battle=joined_by_me, user=self.user)
        BattleRequest.objects.create(
            user=self.other,
            battle_time=self.now - timedelta(days=3),
            location="无关过去约战",
            player_count=1,
        )
        BattleRequest.objects.create(
            user=self.user,
            battle_time=self.now + timedelta(days=1),
            location="未来约战不进记录",
            player_count=1,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("diary:battle_history"))

        self.assertContains(response, "我发起的过去约战")
        self.assertContains(response, "我应战的过去约战")
        self.assertContains(response, "我发起的")
        self.assertContains(response, "我应战的")
        self.assertContains(response, reverse("diary:battles"))
        self.assertContains(response, "返回")
        self.assertNotContains(response, "无关过去约战")
        self.assertNotContains(response, "未来约战不进记录")

        # Keep the created object referenced so the test clearly documents both paths.
        self.assertEqual(created_by_me.user, self.user)

    def test_cannot_join_finished_battle_directly(self):
        battle = BattleRequest.objects.create(
            user=self.other,
            battle_time=self.now - timedelta(minutes=5),
            location="已经结束",
            player_count=1,
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("diary:battle_join", kwargs={"pk": battle.pk}))

        self.assertRedirects(response, reverse("diary:battles"))
        self.assertFalse(BattleResponse.objects.filter(battle=battle, user=self.user).exists())

    def test_battle_notice_does_not_add_place_suffix(self):
        battle = BattleRequest.objects.create(
            user=self.other,
            battle_time=self.now + timedelta(hours=1),
            location="球厅",
            player_count=1,
        )
        BattleResponse.objects.create(battle=battle, user=self.user)
        self.client.force_login(self.user)

        response = self.client.get(reverse("diary:battles"))

        self.assertContains(response, "在球厅有一场")
        self.assertNotContains(response, "在球厅地方")
