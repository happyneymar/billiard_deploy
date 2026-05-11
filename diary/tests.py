from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import AnonymousUser, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from diary.models import (
    BattleRequest,
    BattleResponse,
    DailyRecord,
    DirectBattleRequest,
    FriendRequest,
    Friendship,
    Moment,
    MomentComment,
    MomentLike,
    MomentMedia,
    PrivateMessage,
)
from diary.middleware import RateLimitMiddleware, RateLimitStore


class RateLimitMiddlewareTests(TestCase):
    def setUp(self):
        self.store = RateLimitStore()
        self.store._data.clear()
        self.factory = RequestFactory()
        self.middleware = RateLimitMiddleware(lambda request: HttpResponse("ok"))

    def tearDown(self):
        self.store._data.clear()

    def _request(self, path, user=None):
        request = self.factory.get(path, REMOTE_ADDR="127.0.0.1")
        request.user = user or AnonymousUser()
        return request

    def test_rate_limit_buckets_are_separate_by_request_type(self):
        for _ in range(30):
            response = self.middleware(self._request("/login/"))
            self.assertEqual(response.status_code, 200)

        self.assertEqual(self.middleware(self._request("/login/")).status_code, 429)
        self.assertEqual(self.middleware(self._request("/")).status_code, 200)

    def test_authenticated_default_limit_is_higher_than_anonymous_limit(self):
        user = User.objects.create_user(username="active", password="pass12345")

        for _ in range(121):
            response = self.middleware(self._request("/", user=user))

        self.assertEqual(response.status_code, 200)


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

    def test_reply_to_self_is_saved_as_plain_comment(self):
        self.client.force_login(self.author)

        response = self.client.post(
            reverse("diary:moment_comment", kwargs={"pk": self.moment.pk}),
            {"text": "不回复自己", "reply_to_username": self.author.username},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        comment = MomentComment.objects.get()
        self.assertEqual(comment.text, "不回复自己")
        self.assertEqual(response.json()["comment"]["text"], "不回复自己")

    def test_comment_author_can_delete_own_comment(self):
        comment = MomentComment.objects.create(
            moment=self.moment,
            user=self.author,
            text="我要删除",
        )
        self.client.force_login(self.author)

        response = self.client.post(
            reverse("diary:moment_comment_delete", kwargs={"pk": comment.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], True)
        self.assertFalse(MomentComment.objects.filter(pk=comment.pk).exists())

    def test_user_cannot_delete_someone_elses_comment(self):
        comment = MomentComment.objects.create(
            moment=self.moment,
            user=self.reply_target,
            text="别人的评论",
        )
        self.client.force_login(self.author)

        response = self.client.post(
            reverse("diary:moment_comment_delete", kwargs={"pk": comment.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(MomentComment.objects.filter(pk=comment.pk).exists())

    def test_moment_media_upload_failure_shows_form_error(self):
        self.client.force_login(self.author)
        uploaded = SimpleUploadedFile(
            "shot.jpg",
            b"fake-image",
            content_type="image/jpeg",
        )
        storage = MomentMedia._meta.get_field("file").storage

        with mock.patch.object(storage, "save", side_effect=RuntimeError("cloudinary failed")):
            response = self.client.post(
                reverse("diary:moments"),
                {"text": "带图朋友圈", "media_files": uploaded},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "媒体文件上传失败")
        self.assertFalse(Moment.objects.filter(text="带图朋友圈").exists())

    def test_moment_media_delete_failure_does_not_500(self):
        self.client.force_login(self.author)
        media = MomentMedia.objects.create(
            moment=self.moment,
            file="users/1/moments/2026-05-11/missing.jpg",
            media_type="image",
        )
        storage = MomentMedia._meta.get_field("file").storage

        with mock.patch.object(storage, "delete", side_effect=RuntimeError("cloudinary failed")):
            response = self.client.post(reverse("diary:moment_delete", kwargs={"pk": self.moment.pk}))

        self.assertRedirects(response, reverse("diary:moments"), fetch_redirect_response=False)
        self.assertFalse(Moment.objects.filter(pk=self.moment.pk).exists())
        self.assertFalse(MomentMedia.objects.filter(pk=media.pk).exists())

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
        self.assertContains(response, "js-comment-action")
        self.assertContains(response, "data-delete-url=")

    def test_profile_from_moments_returns_to_moment_anchor(self):
        self.client.force_login(self.author)

        response = self.client.get(
            reverse("diary:public_profile", kwargs={"username": self.reply_target.username}),
            {"from": "moments", "moment": str(self.moment.pk)},
        )

        self.assertContains(response, "返回朋友圈")
        self.assertContains(response, f"{reverse('diary:moments')}#moment-{self.moment.pk}")
        self.assertContains(
            response,
            f"{reverse('diary:user_moments', kwargs={'username': self.reply_target.username})}?from=moments&amp;moment={self.moment.pk}",
        )
        self.assertNotContains(response, "返回我的记录")

    def test_profile_from_search_keeps_record_back_button(self):
        self.client.force_login(self.author)

        response = self.client.get(
            reverse("diary:public_profile", kwargs={"username": self.reply_target.username})
        )

        self.assertContains(response, "返回我的记录")
        self.assertContains(response, reverse("diary:record_list"))
        self.assertContains(response, reverse("diary:user_moments", kwargs={"username": self.reply_target.username}))
        self.assertNotContains(response, f"{reverse('diary:user_moments', kwargs={'username': self.reply_target.username})}?from=moments")
        self.assertNotContains(response, "返回朋友圈")

    def test_user_moments_preserves_moments_source_when_returning_to_profile(self):
        self.client.force_login(self.author)

        response = self.client.get(
            reverse("diary:user_moments", kwargs={"username": self.reply_target.username}),
            {"from": "moments", "moment": str(self.moment.pk)},
        )

        self.assertContains(response, "返回TA的主页")
        self.assertContains(
            response,
            f"{reverse('diary:public_profile', kwargs={'username': self.reply_target.username})}?from=moments&amp;moment={self.moment.pk}",
        )

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
        self.assertContains(response, "我的朋友圈")
        self.assertContains(response, reverse("diary:user_moments", kwargs={"username": self.author.username}))
        self.assertContains(response, "data-toggle-composer")
        self.assertContains(response, "id=\"moments-composer\"")
        self.assertContains(response, "display:none")

    def test_main_moments_feed_sets_scroll_offset_for_fixed_topbar(self):
        self.client.force_login(self.author)

        response = self.client.get(reverse("diary:moments"))

        self.assertContains(response, "scroll-padding-top: 96px")
        self.assertContains(response, "scroll-margin-top: 96px")
        self.assertContains(response, "scrollToWithMomentsOffset")

    def test_my_moments_page_shows_delete_button_for_own_moments(self):
        self.client.force_login(self.author)

        response = self.client.get(reverse("diary:user_moments", kwargs={"username": self.author.username}))

        self.assertContains(response, "我的朋友圈")
        self.assertContains(response, "删除")
        self.assertContains(response, reverse("diary:moment_delete", kwargs={"pk": self.moment.pk}))

    def test_moment_author_can_delete_own_moment_with_comments_and_likes(self):
        MomentComment.objects.create(moment=self.moment, user=self.reply_target, text="评论")
        MomentLike.objects.create(moment=self.moment, user=self.reply_target)
        self.client.force_login(self.author)

        response = self.client.post(reverse("diary:moment_delete", kwargs={"pk": self.moment.pk}))

        self.assertRedirects(response, reverse("diary:moments"))
        self.assertFalse(Moment.objects.filter(pk=self.moment.pk).exists())
        self.assertFalse(MomentComment.objects.filter(moment_id=self.moment.pk).exists())
        self.assertFalse(MomentLike.objects.filter(moment_id=self.moment.pk).exists())

    def test_user_cannot_delete_someone_elses_moment(self):
        self.client.force_login(self.reply_target)

        response = self.client.post(reverse("diary:moment_delete", kwargs={"pk": self.moment.pk}))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Moment.objects.filter(pk=self.moment.pk).exists())


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
        self.assertContains(response, reverse("diary:record_list"))
        self.assertContains(response, "返回")
        self.assertContains(response, reverse("diary:battle_history"))
        self.assertContains(response, "约战记录")
        self.assertContains(response, reverse("diary:battle_created"))
        self.assertContains(response, "我发起的")

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
        self.assertNotContains(response, "今日")
        self.assertNotContains(response, "在球厅地方")

    def test_created_battles_page_lists_public_and_direct_battles_i_started(self):
        Friendship.create_pair(self.user, self.other)
        public_battle = BattleRequest.objects.create(
            user=self.user,
            battle_time=self.now + timedelta(hours=2),
            location="大厅球厅",
            player_count=2,
        )
        direct_battle = DirectBattleRequest.objects.create(
            from_user=self.user,
            to_user=self.other,
            battle_time=self.now + timedelta(hours=3),
            location="好友球厅",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("diary:battle_created"))

        self.assertContains(response, "大厅球厅")
        self.assertContains(response, "好友球厅")
        self.assertContains(response, self.other.username)
        self.assertContains(response, reverse("diary:battles"))
        self.assertEqual(public_battle.user, self.user)
        self.assertEqual(direct_battle.from_user, self.user)


class FriendViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="frienduser", password="pass12345")
        self.other = User.objects.create_user(username="otherfriend", password="pass12345")
        self.third = User.objects.create_user(username="thirdfriend", password="pass12345")

    def test_topbar_replaces_user_search_with_friend_button(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("diary:record_list"))

        self.assertContains(response, reverse("diary:friends"))
        self.assertContains(response, reverse("diary:messages"))
        self.assertContains(response, "好友")
        self.assertContains(response, "消息")
        self.assertNotContains(response, "消息（")
        self.assertNotContains(response, "查看他人记录")
        self.assertNotContains(response, "查询")

    def test_topbar_message_button_shows_pending_message_count(self):
        for offset in (1, 2):
            DirectBattleRequest.objects.create(
                from_user=self.other,
                to_user=self.user,
                battle_time=timezone.now() + timedelta(days=offset),
                location=f"球厅{offset}",
            )
        DirectBattleRequest.objects.create(
            from_user=self.third,
            to_user=self.user,
            battle_time=timezone.now() + timedelta(days=3),
            location="已处理球厅",
            status=DirectBattleRequest.STATUS_ACCEPTED,
        )
        PrivateMessage.objects.create(
            from_user=self.third,
            to_user=self.user,
            text="一条未读私信",
        )
        PrivateMessage.objects.create(
            from_user=self.third,
            to_user=self.user,
            text="一条已读私信",
            is_read=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("diary:record_list"))

        self.assertContains(response, "消息（3）")
        self.assertNotContains(response, "消息（4）")

    def test_friends_page_shows_friend_request_count_and_friend_links(self):
        Friendship.create_pair(self.user, self.other)
        FriendRequest.objects.create(from_user=self.third, to_user=self.user)
        self.client.force_login(self.user)

        response = self.client.get(reverse("diary:friends"))

        self.assertContains(response, "添加好友")
        self.assertContains(response, "收到的好友申请：（1）")
        self.assertContains(response, reverse("diary:friend_add"))
        self.assertContains(response, reverse("diary:friend_requests"))
        self.assertContains(response, f"{reverse('diary:public_profile', kwargs={'username': self.other.username})}?from=friends")
        self.assertContains(response, reverse("diary:private_message_new", kwargs={"username": self.other.username}))
        self.assertContains(response, reverse("diary:friend_history", kwargs={"username": self.other.username}))
        self.assertContains(response, reverse("diary:direct_battle_new", kwargs={"username": self.other.username}))
        self.assertContains(response, self.other.username)

    def test_friend_history_filters_records_and_shows_relative_stats(self):
        Friendship.create_pair(self.user, self.other)
        today = timezone.localdate()
        DailyRecord.objects.create(
            user=self.user,
            date=today,
            opponent_name=self.other.username,
            game_type=DailyRecord.TYPE_8BALL,
            score_for=3,
            score_against=0,
        )
        DailyRecord.objects.create(
            user=self.user,
            date=today,
            opponent_name=self.other.username,
            game_type=DailyRecord.TYPE_8BALL,
            score_for=1,
            score_against=4,
        )
        DailyRecord.objects.create(
            user=self.user,
            date=today,
            opponent_name=self.other.username,
            game_type=DailyRecord.TYPE_SCORE,
            score=12,
        )
        DailyRecord.objects.create(
            user=self.user,
            date=today,
            opponent_name=self.third.username,
            game_type=DailyRecord.TYPE_SCORE,
            score=99,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("diary:friend_history", kwargs={"username": self.other.username}),
            {"period": "all"},
        )

        selected_stats = response.context["selected_stats"]
        self.assertEqual(selected_stats["total_matches"], 3)
        self.assertEqual(selected_stats["eight_ball_matches"], 2)
        self.assertEqual(selected_stats["eight_ball_win_rate"], 50)
        self.assertEqual(selected_stats["score_matches"], 1)
        self.assertEqual(selected_stats["score_win_rate"], 100)
        self.assertContains(response, "和 ")
        self.assertContains(response, self.other.username)
        self.assertContains(response, reverse("diary:direct_battle_new", kwargs={"username": self.other.username}))
        self.assertNotContains(response, self.third.username)

    def test_profile_from_friends_returns_to_friends_page(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("diary:public_profile", kwargs={"username": self.other.username}),
            {"from": "friends"},
        )

        self.assertContains(response, "返回我的好友界面")
        self.assertContains(response, reverse("diary:friends"))
        self.assertContains(
            response,
            f"{reverse('diary:user_moments', kwargs={'username': self.other.username})}?from=friends",
        )
        self.assertContains(response, "?period=half_year&amp;from=friends")
        self.assertNotContains(response, "返回我的记录")

    def test_friend_profile_to_user_moments_returns_to_friend_context(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("diary:user_moments", kwargs={"username": self.other.username}),
            {"from": "friends"},
        )

        self.assertContains(response, "返回TA的主页")
        self.assertContains(
            response,
            f"{reverse('diary:public_profile', kwargs={'username': self.other.username})}?from=friends",
        )

    def test_send_friend_request_by_username(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("diary:friend_add"), {"username": self.other.username})

        self.assertRedirects(response, reverse("diary:friends"))
        self.assertTrue(
            FriendRequest.objects.filter(
                from_user=self.user,
                to_user=self.other,
                status=FriendRequest.STATUS_PENDING,
            ).exists()
        )

    def test_received_friend_requests_can_be_accepted(self):
        friend_request = FriendRequest.objects.create(from_user=self.other, to_user=self.user)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("diary:friend_request_accept", kwargs={"pk": friend_request.pk})
        )

        self.assertRedirects(response, reverse("diary:friend_requests"))
        friend_request.refresh_from_db()
        self.assertEqual(friend_request.status, FriendRequest.STATUS_ACCEPTED)
        self.assertTrue(Friendship.are_friends(self.user, self.other))

    def test_received_friend_requests_can_be_declined(self):
        friend_request = FriendRequest.objects.create(from_user=self.other, to_user=self.user)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("diary:friend_request_decline", kwargs={"pk": friend_request.pk})
        )

        self.assertRedirects(response, reverse("diary:friend_requests"))
        friend_request.refresh_from_db()
        self.assertEqual(friend_request.status, FriendRequest.STATUS_DECLINED)
        self.assertFalse(Friendship.are_friends(self.user, self.other))

    def test_friend_can_receive_direct_battle_request_and_accept_it(self):
        Friendship.create_pair(self.user, self.other)
        battle_time = timezone.now() + timedelta(days=1)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("diary:direct_battle_new", kwargs={"username": self.other.username}),
            {
                "battle_time": battle_time.strftime("%Y-%m-%dT%H:%M"),
                "location": "单独球厅",
                "note": "点对点约战",
            },
        )

        self.assertRedirects(response, reverse("diary:friends"))
        direct_battle = DirectBattleRequest.objects.get(
            from_user=self.user,
            to_user=self.other,
        )
        self.assertEqual(direct_battle.status, DirectBattleRequest.STATUS_PENDING)

        self.client.force_login(self.other)
        response = self.client.get(reverse("diary:messages"))
        self.assertContains(response, "单独球厅")
        self.assertContains(response, self.user.username)
        self.assertContains(response, reverse("diary:direct_battle_accept", kwargs={"pk": direct_battle.pk}))

        response = self.client.post(
            reverse("diary:direct_battle_accept", kwargs={"pk": direct_battle.pk})
        )

        self.assertRedirects(response, reverse("diary:messages"))
        direct_battle.refresh_from_db()
        self.assertEqual(direct_battle.status, DirectBattleRequest.STATUS_ACCEPTED)

        response = self.client.get(reverse("diary:record_list"))
        self.assertContains(response, "单独球厅")
        self.assertContains(response, self.user.username)
        self.assertContains(response, "约战")

        response = self.client.get(reverse("diary:battles"))
        self.assertContains(response, "单独球厅")
        self.assertContains(response, self.user.username)

    def test_direct_battle_requires_friendship(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("diary:direct_battle_new", kwargs={"username": self.other.username}),
            {
                "battle_time": (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "location": "陌生人球厅",
            },
        )

        self.assertRedirects(response, reverse("diary:friends"))
        self.assertFalse(DirectBattleRequest.objects.exists())

    def test_friend_can_receive_private_message_in_messages_page(self):
        Friendship.create_pair(self.user, self.other)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("diary:private_message_new", kwargs={"username": self.other.username}),
            {"text": "今晚练球吗？"},
        )

        self.assertRedirects(response, reverse("diary:friends"))
        private_message = PrivateMessage.objects.get(
            from_user=self.user,
            to_user=self.other,
        )
        self.assertEqual(private_message.text, "今晚练球吗？")
        self.assertFalse(private_message.is_read)

        self.client.force_login(self.other)
        response = self.client.get(reverse("diary:record_list"))
        self.assertContains(response, "消息（1）")

        response = self.client.get(reverse("diary:messages"))
        self.assertContains(response, self.user.username)
        self.assertContains(response, "今晚练球吗？")
        private_message.refresh_from_db()
        self.assertTrue(private_message.is_read)

        response = self.client.get(reverse("diary:record_list"))
        self.assertNotContains(response, "消息（")

    def test_private_message_requires_friendship(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("diary:private_message_new", kwargs={"username": self.other.username}),
            {"text": "不能发给非好友"},
        )

        self.assertRedirects(response, reverse("diary:friends"))
        self.assertFalse(PrivateMessage.objects.exists())


class GameStartViewTests(TestCase):
    def test_game_start_has_back_button_to_record_list(self):
        user = User.objects.create_user(username="gameuser", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("diary:game_start"))

        self.assertContains(response, "返回")
        self.assertContains(response, reverse("diary:record_list"))


class RecordListStatsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="statsuser", password="pass12345")

    def test_record_list_shows_match_counts_and_win_rates(self):
        today = timezone.localdate()
        DailyRecord.objects.create(
            user=self.user,
            date=today,
            game_type=DailyRecord.TYPE_8BALL,
            score_for=3,
            score_against=0,
        )
        DailyRecord.objects.create(
            user=self.user,
            date=today,
            game_type=DailyRecord.TYPE_8BALL,
            score_for=1,
            score_against=4,
        )
        DailyRecord.objects.create(
            user=self.user,
            date=today,
            game_type=DailyRecord.TYPE_SCORE,
            score=12,
        )
        DailyRecord.objects.create(
            user=self.user,
            date=today,
            game_type=DailyRecord.TYPE_SCORE,
            score=-3,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("diary:record_list"))

        self.assertContains(response, "总场数")
        self.assertContains(response, ">4</div>")
        self.assertContains(response, "黑八场数")
        self.assertContains(response, "黑八胜率")
        self.assertContains(response, "追分场数")
        self.assertContains(response, "追分胜率")
        self.assertContains(response, ">50%</div>", count=2)


class RecordDetailViewTests(TestCase):
    def test_8ball_score_is_shown_inside_detail_card(self):
        user = User.objects.create_user(username="recorduser", password="pass12345")
        record = DailyRecord.objects.create(
            user=user,
            date=timezone.localdate(),
            game_type=DailyRecord.TYPE_8BALL,
            opponent_name="对手",
            score_for=3,
            score_against=2,
            clear_in_count=1,
            clear_boom_count=0,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("diary:record_detail", kwargs={"pk": record.pk}))
        content = response.content.decode()
        subtitle = content.split("</p>", 1)[0]

        self.assertContains(response, "接清局数")
        self.assertContains(response, "炸清局数")
        self.assertContains(response, "比分")
        self.assertContains(response, "3:2")
        self.assertContains(response, "返回")
        self.assertContains(response, reverse("diary:record_list"))
        self.assertNotContains(response, "返回历史记录")
        self.assertNotIn("比分 3:2", subtitle)
