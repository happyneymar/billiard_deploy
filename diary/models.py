import mimetypes
import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import FileExtensionValidator, validate_image_file_extension
from django.db import models
from django.utils.deconstruct import deconstructible


# ============ 文件上传安全验证 ============

ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "gif", "webp"]
ALLOWED_VIDEO_EXTENSIONS = ["mp4", "webm", "mov", "avi"]
ALLOWED_MEDIA_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS + ALLOWED_VIDEO_EXTENSIONS

MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB
MAX_IMAGE_DIMENSION = 4096  # 像素


@deconstructible
class MediaFileValidator:
    """验证上传的媒体文件"""

    ALLOWED_EXTENSIONS = ALLOWED_MEDIA_EXTENSIONS
    ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
    MAX_SIZE = MAX_UPLOAD_SIZE

    def __init__(self, allowed_types=None):
        self.allowed_types = allowed_types or (self.ALLOWED_IMAGE_TYPES | self.ALLOWED_VIDEO_TYPES)

    def __call__(self, file):
        # 检查文件大小
        if file.size > self.MAX_SIZE:
            raise models.ValidationError(
                f"文件大小不能超过 {self.MAX_SIZE // (1024 * 1024)}MB"
            )

        # 检查文件扩展名
        ext = Path(file.name).suffix.lower().lstrip(".")
        if ext not in self.ALLOWED_EXTENSIONS:
            raise models.ValidationError(
                f"不支持的文件类型。允许的类型: {', '.join(self.ALLOWED_EXTENSIONS)}"
            )

        # 验证 MIME 类型
        content_type = getattr(file, "content_type", None)
        if content_type:
            # 严格验证 MIME 类型与扩展名匹配
            expected_types = {
                "jpg": {"image/jpeg"},
                "jpeg": {"image/jpeg"},
                "png": {"image/png"},
                "gif": {"image/gif"},
                "webp": {"image/webp", "image/webp"},
                "mp4": {"video/mp4", "video/mpeg"},
                "webm": {"video/webm"},
                "mov": {"video/quicktime", "video/mp4"},
                "avi": {"video/x-msvideo"},
            }
            allowed_mimes = expected_types.get(ext, set())
            if content_type not in allowed_mimes:
                raise models.ValidationError(
                    f"文件扩展名与内容类型不匹配"
                )


def validate_secure_filename(filename: str) -> str:
    """清理文件名，移除危险字符"""
    import re
    # 移除路径遍历和危险字符
    safe_name = re.sub(r"[^\w\s\-\.]", "", filename)
    safe_name = re.sub(r"\.+", ".", safe_name)  # 防止 .. 路径遍历
    return safe_name[: 255]  # 限制长度


def daily_media_upload_to(instance: "DailyMedia", filename: str) -> str:
    ext = Path(validate_secure_filename(filename)).suffix.lower()
    if ext not in [f".{e}" for e in ALLOWED_MEDIA_EXTENSIONS]:
        ext = ".bin"  # 默认不安全扩展名会被拒绝
    return (
        f"users/{instance.record.user_id}/"
        f"records/{instance.record.date:%Y-%m-%d}/"
        f"{uuid.uuid4().hex}{ext}"
    )


def moment_media_upload_to(instance: "MomentMedia", filename: str) -> str:
    ext = Path(validate_secure_filename(filename)).suffix.lower()
    if ext not in [f".{e}" for e in ALLOWED_MEDIA_EXTENSIONS]:
        ext = ".bin"
    return (
        f"users/{instance.moment.user_id}/"
        f"moments/{instance.moment.created_at:%Y-%m-%d}/"
        f"{uuid.uuid4().hex}{ext}"
    )


class DailyRecord(models.Model):
    TYPE_8BALL = "8ball"
    TYPE_SCORE = "score"

    TYPE_CHOICES = [
        (TYPE_8BALL, "黑八"),
        (TYPE_SCORE, "追分"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="daily_records",
    )
    date = models.DateField()
    game_type = models.CharField(max_length=8, choices=TYPE_CHOICES, default=TYPE_8BALL)

    # 黑八专用字段
    opponent_name = models.CharField("对手名（可选）", max_length=64, blank=True)
    score_for = models.PositiveIntegerField("我方得分", default=0)
    score_against = models.PositiveIntegerField("对方得分", default=0)
    clear_in_count = models.PositiveIntegerField("接清局数", default=0)
    clear_boom_count = models.PositiveIntegerField("炸清局数", default=0)

    # 追分专用字段
    score = models.IntegerField("得分/积分", default=0)
    big_jin = models.PositiveIntegerField("大金数", default=0)
    small_jin = models.PositiveIntegerField("小金数", default=0)
    golden_nine = models.PositiveIntegerField("黄金九数", default=0)
    foul_count = models.PositiveIntegerField("犯规数", default=0)

    comment = models.TextField("当天评论", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.user_id} - {self.date} ({self.score_for}:{self.score_against})"


class DailyMedia(models.Model):
    MEDIA_TYPE_IMAGE = "image"
    MEDIA_TYPE_VIDEO = "video"

    MEDIA_TYPE_CHOICES = [
        (MEDIA_TYPE_IMAGE, "图片"),
        (MEDIA_TYPE_VIDEO, "视频"),
    ]

    record = models.ForeignKey(
        DailyRecord,
        on_delete=models.CASCADE,
        related_name="media_items",
    )
    file = models.FileField(upload_to=daily_media_upload_to)
    media_type = models.CharField(max_length=5, choices=MEDIA_TYPE_CHOICES)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def guess_media_type(uploaded_file) -> str:
        content_type = getattr(uploaded_file, "content_type", None) or ""
        if content_type.startswith("image/"):
            return DailyMedia.MEDIA_TYPE_IMAGE
        if content_type.startswith("video/"):
            return DailyMedia.MEDIA_TYPE_VIDEO

        # Fallback: guess by filename
        guessed_type, _ = mimetypes.guess_type(getattr(uploaded_file, "name", ""))
        if (guessed_type or "").startswith("image/"):
            return DailyMedia.MEDIA_TYPE_IMAGE
        return DailyMedia.MEDIA_TYPE_VIDEO

    def __str__(self) -> str:
        return f"{self.record_id} - {self.media_type}"


class Moment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="moments",
    )
    text = models.TextField("文字内容", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        preview = self.text[:24] if self.text else "媒体动态"
        return f"{self.user_id} - {preview}"


class MomentMedia(models.Model):
    moment = models.ForeignKey(
        Moment,
        on_delete=models.CASCADE,
        related_name="media_items",
    )
    file = models.FileField(upload_to=moment_media_upload_to)
    media_type = models.CharField(max_length=5, choices=DailyMedia.MEDIA_TYPE_CHOICES)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def guess_media_type(uploaded_file) -> str:
        return DailyMedia.guess_media_type(uploaded_file)

    def __str__(self) -> str:
        return f"{self.moment_id} - {self.media_type}"


class MomentLike(models.Model):
    moment = models.ForeignKey(Moment, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="moment_likes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["moment", "user"], name="unique_moment_like")
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user_id} likes {self.moment_id}"


class MomentComment(models.Model):
    moment = models.ForeignKey(Moment, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="moment_comments",
    )
    text = models.TextField("评论内容")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.user_id} - {self.text[:24]}"

class BattleRequest(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="battle_requests",
    )
    battle_time = models.DateTimeField("约战时间")
    location = models.CharField("地点", max_length=120)
    player_count = models.PositiveIntegerField("寻找人数", default=1)
    note = models.TextField("备注", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["battle_time", "-created_at"]

    def __str__(self) -> str:
        return f"{self.user_id} - {self.battle_time:%Y-%m-%d %H:%M} @ {self.location}"


class BattleResponse(models.Model):
    battle = models.ForeignKey(
        BattleRequest,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="battle_responses",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["battle", "user"], name="unique_battle_response")
        ]
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.user_id} joins {self.battle_id}"
