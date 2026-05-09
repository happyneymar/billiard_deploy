from datetime import date as date_type, timedelta
import json
import mimetypes
import re
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from diary.forms import DailyRecordForm, MomentForm, PasswordResetVerifyForm, SimpleUserCreationForm, TeacherVerifyForm
from diary.models import (
    ALLOWED_MEDIA_EXTENSIONS,
    MAX_UPLOAD_SIZE,
    DailyMedia,
    DailyRecord,
    MediaFileValidator,
    Moment,
    MomentComment,
    MomentLike,
    MomentMedia,
    validate_secure_filename,
)


# 文件上传验证器实例
media_validator = MediaFileValidator()


def _validate_media_file(uploaded_file):
    """验证媒体文件的安全性"""
    errors = []

    # 检查文件大小
    if uploaded_file.size > MAX_UPLOAD_SIZE:
        errors.append(f"文件大小不能超过 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB")

    # 检查扩展名
    ext = uploaded_file.name.split(".")[-1].lower() if "." in uploaded_file.name else ""
    if f".{ext}" not in [f".{e}" for e in ALLOWED_MEDIA_EXTENSIONS]:
        errors.append(f"不支持的文件类型。允许: {', '.join(ALLOWED_MEDIA_EXTENSIONS)}")

    # 检查 MIME 类型
    content_type = getattr(uploaded_file, "content_type", "")
    allowed_types = {
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "video/mp4", "video/webm", "video/quicktime"
    }
    if content_type not in allowed_types:
        errors.append("文件内容类型不被允许")

    return errors


def _sanitize_input(value, max_length=255, pattern=None):
    """清理用户输入"""
    if not value:
        return value
    value = str(value).strip()
    if max_length:
        value = value[:max_length]
    if pattern:
        value = re.sub(pattern, "", value)
    return value


def register(request):
    if request.method == "POST":
        form = SimpleUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("diary:record_list")
    else:
        form = SimpleUserCreationForm()
    return render(request, "diary/register.html", {"form": form})


def user_login(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect("diary:record_list")
    else:
        form = AuthenticationForm()
    return render(request, "diary/login.html", {"form": form})


def user_logout(request):
    logout(request)
    return redirect("diary:login")


def password_reset(request):
    """第一步：输入用户名和台协老师姓名验证"""
    if request.method == "POST":
        form = TeacherVerifyForm(request.POST)
        if form.is_valid():
            # 验证通过，将用户ID存入session
            request.session["password_reset_user_id"] = form.cleaned_data["user"].id
            return redirect("diary:password_reset_set")
    else:
        form = TeacherVerifyForm()
    return render(request, "diary/password_reset.html", {"form": form})


def password_reset_set(request):
    """第二步：设置新密码"""
    user_id = request.session.get("password_reset_user_id")
    if not user_id:
        return redirect("diary:password_reset")

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect("diary:password_reset")

    if request.method == "POST":
        form = PasswordResetVerifyForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data["new_password1"])
            user.save()
            # 清除session
            del request.session["password_reset_user_id"]
            return render(request, "diary/password_reset_done.html")
    else:
        form = PasswordResetVerifyForm()
    return render(request, "diary/password_reset_set.html", {"form": form, "username": user.username})


@login_required
def record_list(request):
    today = date_type.today()
    half_year_ago = today - timedelta(days=183)
    one_year_ago = today - timedelta(days=365)
    month_start = today.replace(day=1)

    base_qs = DailyRecord.objects.filter(user=request.user)

    def _agg(qs):
        return {
            "clear_in": qs.aggregate(s=Sum("clear_in_count"))["s"] or 0,
            "clear_boom": qs.aggregate(s=Sum("clear_boom_count"))["s"] or 0,
            "big_jin": qs.aggregate(s=Sum("big_jin"))["s"] or 0,
            "small_jin": qs.aggregate(s=Sum("small_jin"))["s"] or 0,
            "golden_nine": qs.aggregate(s=Sum("golden_nine"))["s"] or 0,
        }

    stats = {
        "month": _agg(base_qs.filter(date__gte=month_start)),
        "half_year": _agg(base_qs.filter(date__gte=half_year_ago)),
        "one_year": _agg(base_qs.filter(date__gte=one_year_ago)),
        "all": _agg(base_qs),
    }

    # 获取当前选择的时间段，默认为"本月"
    period = request.GET.get("period", "month")

    records = base_qs.order_by("-date", "-created_at")
    return render(
        request,
        "diary/record_list.html",
        {
            "records": records,
            "stats": stats,
            "period": period,
        },
    )


@login_required
def record_new(request):
    if request.method == "POST":
        form = DailyRecordForm(request.POST)
        if form.is_valid():
            cleaned = form.cleaned_data
            with transaction.atomic():
                record = DailyRecord.objects.create(
                    user=request.user,
                    game_type=cleaned["game_type"],
                    date=cleaned["date"],
                    opponent_name=cleaned["opponent_name"],
                    score_for=cleaned["score_for"],
                    score_against=cleaned["score_against"],
                    clear_in_count=cleaned["clear_in_count"],
                    clear_boom_count=cleaned["clear_boom_count"],
                    score=cleaned["score"],
                    big_jin=cleaned["big_jin"],
                    small_jin=cleaned["small_jin"],
                    golden_nine=cleaned["golden_nine"],
                    foul_count=cleaned["foul_count"],
                    comment=cleaned["comment"],
                )

                for uploaded in request.FILES.getlist("media_files"):
                    if not uploaded:
                        continue

                    # 验证文件安全性
                    errors = _validate_media_file(uploaded)
                    if errors:
                        continue  # 跳过无效文件

                    DailyMedia.objects.create(
                        record=record,
                        file=uploaded,
                        media_type=DailyMedia.guess_media_type(uploaded),
                    )

            return redirect("diary:record_detail", pk=record.pk)
    else:
        form = DailyRecordForm(
            initial={
                "date": request.GET.get("date", str(date_type.today())),
            }
        )

    return render(request, "diary/record_new.html", {"form": form})


@login_required
def record_delete(request, pk: int):
    record = get_object_or_404(DailyRecord, pk=pk, user=request.user)
    if request.method == "POST":
        record.delete()
        return redirect("diary:record_list")
    return render(request, "diary/record_delete.html", {"record": record})


@login_required
def record_detail(request, pk: int):
    record = get_object_or_404(DailyRecord, pk=pk, user=request.user)
    media_items = record.media_items.order_by("-uploaded_at")

    if request.method == "POST":
        if not request.user.is_authenticated:
            return JsonResponse({"error": "未授权"}, status=401)

        # 更新评论
        if "update_comment" in request.POST:
            raw_comment = request.POST.get("comment", "")[:2000]
            record.comment = re.sub(r"<[^>]+>", "", raw_comment).strip()
            record.save(update_fields=["comment", "updated_at"])
            return redirect("diary:record_detail", pk=record.pk)

        # 上传媒体文件
        elif "upload_media" in request.POST:
            uploaded_files = request.FILES.getlist("media_files")
            for uploaded in uploaded_files:
                if not uploaded:
                    continue

                # 验证文件
                errors = _validate_media_file(uploaded)
                if errors:
                    continue  # 跳过无效文件

                # 使用安全的文件名
                safe_name = validate_secure_filename(uploaded.name)

                DailyMedia.objects.create(
                    record=record,
                    file=uploaded,
                    media_type=DailyMedia.guess_media_type(uploaded),
                )
            return redirect("diary:record_detail", pk=record.pk)
    
    return render(
        request,
        "diary/record_detail.html",
        {
            "record": record,
            "media_items": media_items,
        },
    )


def _build_stats(base_qs):
    def _agg(qs):
        return {
            "clear_in": qs.aggregate(s=Sum("clear_in_count"))["s"] or 0,
            "clear_boom": qs.aggregate(s=Sum("clear_boom_count"))["s"] or 0,
            "big_jin": qs.aggregate(s=Sum("big_jin"))["s"] or 0,
            "small_jin": qs.aggregate(s=Sum("small_jin"))["s"] or 0,
            "golden_nine": qs.aggregate(s=Sum("golden_nine"))["s"] or 0,
        }

    today = date_type.today()
    stats = {
        "month": _agg(base_qs.filter(date__gte=today.replace(day=1))),
        "half_year": _agg(base_qs.filter(date__gte=today - timedelta(days=183))),
        "one_year": _agg(base_qs.filter(date__gte=today - timedelta(days=365))),
        "all": _agg(base_qs),
    }
    return stats


def _filter_by_period(qs, period):
    today = date_type.today()
    if period == "month":
        return qs.filter(date__gte=today.replace(day=1))
    if period == "half_year":
        return qs.filter(date__gte=today - timedelta(days=183))
    if period == "one_year":
        return qs.filter(date__gte=today - timedelta(days=365))
    return qs


def user_search(request):
    username = request.GET.get("username", "").strip()
    if username:
        target = User.objects.filter(username=username).first()
        if target:
            return redirect("diary:public_profile", username=target.username)
        else:
            return render(request, "diary/user_search.html", {"username": username, "not_found": True})
    return render(request, "diary/user_search.html")


def public_profile(request, username: str):
    target = get_object_or_404(User, username=username)
    base_qs = DailyRecord.objects.filter(user=target)
    period = request.GET.get("period", "month")
    if period not in {"month", "half_year", "one_year", "all"}:
        period = "month"

    stats = _build_stats(base_qs)
    records = _filter_by_period(base_qs, period).order_by("-date", "-created_at")
    return render(
        request,
        "diary/public_profile.html",
        {
            "target_user": target,
            "records": records,
            "stats": stats,
            "period": period,
            "selected_stats": stats[period],
        },
    )


@login_required
def moments_feed(request):
    if request.method == "POST":
        form = MomentForm(request.POST)
        media_files = request.FILES.getlist("media_files")

        if len(media_files) > 9:
            form.add_error(None, "一次最多上传9个图片或视频。")

        valid_media = []
        for uploaded in media_files:
            errors = _validate_media_file(uploaded)
            if errors:
                form.add_error(None, f"{uploaded.name}: {'；'.join(errors)}")
            else:
                valid_media.append(uploaded)

        if form.is_valid():
            text = form.cleaned_data["text"]
            if not text and not valid_media:
                form.add_error(None, "请填写文字，或上传至少一个图片/视频。")
            else:
                with transaction.atomic():
                    moment = Moment.objects.create(user=request.user, text=text)
                    for uploaded in valid_media:
                        MomentMedia.objects.create(
                            moment=moment,
                            file=uploaded,
                            media_type=MomentMedia.guess_media_type(uploaded),
                        )
                messages.success(request, "朋友圈已发布。")
                return redirect("diary:moments")
    else:
        form = MomentForm()

    return render(
        request,
        "diary/moments.html",
        {
            "form": form,
            **_build_moments_context(
                request,
                Moment.objects.all(),
                page_title="朋友圈",
                subtitle="分享台球瞬间，看看大家最近在打什么。",
                back_url=reverse("diary:record_list"),
                back_label="返回",
                show_composer=True,
            ),
        },
    )


def _build_moments_context(
    request,
    moments_qs,
    page_title,
    subtitle,
    back_url,
    back_label,
    show_composer=False,
):
    moments = (
        moments_qs.select_related("user")
        .prefetch_related("media_items", "comments__user")
        .annotate(like_count=Count("likes", distinct=True))
        .order_by("-created_at")
    )
    liked_moment_ids = set(
        MomentLike.objects.filter(user=request.user, moment__in=moments).values_list(
            "moment_id", flat=True
        )
    )
    for moment in moments:
        moment.is_liked_by_me = moment.id in liked_moment_ids

    return {
        "moments": moments,
        "page_title": page_title,
        "subtitle": subtitle,
        "back_url": back_url,
        "back_label": back_label,
        "show_composer": show_composer,
    }


@login_required
def user_moments(request, username: str):
    target = get_object_or_404(User, username=username)
    return render(
        request,
        "diary/moments.html",
        _build_moments_context(
            request,
            Moment.objects.filter(user=target),
            page_title=f"{target.username} 的朋友圈",
            subtitle=f"以下是 {target.username} 发布过的朋友圈。",
            back_url=reverse("diary:public_profile", kwargs={"username": target.username}),
            back_label="返回TA的主页",
        ),
    )


@login_required
@require_http_methods(["POST"])
def moment_like(request, pk: int):
    moment = get_object_or_404(Moment, pk=pk)
    like = MomentLike.objects.filter(moment=moment, user=request.user).first()
    if like:
        like.delete()
        liked = False
    else:
        MomentLike.objects.create(moment=moment, user=request.user)
        liked = True
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "liked": liked,
                "like_count": moment.likes.count(),
            }
        )
    return redirect(request.META.get("HTTP_REFERER") or reverse("diary:moments"))


@login_required
@require_http_methods(["POST"])
def moment_comment(request, pk: int):
    moment = get_object_or_404(Moment, pk=pk)
    text = re.sub(r"<[^>]+>", "", request.POST.get("text", "")).strip()[:500]
    if text:
        comment = MomentComment.objects.create(moment=moment, user=request.user, text=text)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "comment": {
                        "username": comment.user.username,
                        "text": comment.text,
                    }
                }
            )
    elif request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"error": "评论内容不能为空"}, status=400)
    return redirect(request.META.get("HTTP_REFERER") or reverse("diary:moments"))


@login_required
def media_serve(request, relative_path: str):
    # relative_path 来自 FileField 的 upload_to 输出（不带前导 /）。
    media = DailyMedia.objects.select_related("record").filter(
        file=relative_path,
        record__user=request.user,
    ).first()
    if media is None:
        media = get_object_or_404(
            MomentMedia.objects.select_related("moment"),
            file=relative_path,
        )

    content_type, _ = mimetypes.guess_type(media.file.name)
    try:
        media_handle = media.file.open("rb")
    except Exception as exc:  # pragma: no cover
        raise Http404("媒体文件不存在") from exc

    return FileResponse(media_handle, content_type=content_type or "application/octet-stream")


@login_required
@require_http_methods(["POST"])
def media_delete(request, pk: int):
    """删除媒体文件"""
    media = get_object_or_404(
        DailyMedia.objects.select_related("record"),
        pk=pk,
        record__user=request.user,
    )
    record_pk = media.record.pk
    media.delete()
    return redirect("diary:record_detail", pk=record_pk)


@login_required
def game_start(request):
    """开灯页面：输入对手名和选择游戏类型"""
    if request.method == "POST":
        opponent_name = request.POST.get("opponent_name", "").strip()
        game_type = request.POST.get("game_type")
        if game_type in [DailyRecord.TYPE_8BALL, DailyRecord.TYPE_SCORE]:
            params = urlencode({"opponent_name": opponent_name}) if opponent_name else ""
            url = reverse('diary:game_play', kwargs={'game_type': game_type})
            if params:
                url = f"{url}?{params}"
            return redirect(url)
    return render(request, "diary/game_start.html")


@login_required
def game_play(request, game_type: str):
    """实时计分页面"""
    if game_type not in [DailyRecord.TYPE_8BALL, DailyRecord.TYPE_SCORE]:
        return redirect("diary:game_start")
    opponent_name = request.GET.get("opponent_name", "").strip()
    return render(
        request,
        "diary/game_play.html",
        {
            "game_type": game_type,
            "opponent_name": opponent_name,
        },
    )


@login_required
@require_http_methods(["POST"])
def game_update_score(request):
    """更新比分（AJAX）"""
    try:
        data = json.loads(request.body)

        # 验证 game_type
        game_type = data.get("game_type")
        if game_type not in [DailyRecord.TYPE_8BALL, DailyRecord.TYPE_SCORE]:
            return JsonResponse({"error": "无效的游戏类型"}, status=400)

        action = data.get("action")

        if game_type == DailyRecord.TYPE_8BALL:
            # 黑八模式 - 严格范围验证
            score_for = max(0, min(50, int(data.get("score_for", 0))))
            score_against = max(0, min(50, int(data.get("score_against", 0))))
            clear_in = max(0, min(50, int(data.get("clear_in", 0))))
            clear_boom = max(0, min(50, int(data.get("clear_boom", 0))))
            return JsonResponse({
                "score_for": score_for,
                "score_against": score_against,
                "clear_in": clear_in,
                "clear_boom": clear_boom,
            })
        elif game_type == DailyRecord.TYPE_SCORE:
            # 追分模式 - 严格范围验证
            score = max(-200, min(200, int(data.get("score", 0))))
            big_jin = max(0, min(50, int(data.get("big_jin", 0))))
            small_jin = max(0, min(50, int(data.get("small_jin", 0))))
            golden_nine = max(0, min(50, int(data.get("golden_nine", 0))))
            foul_count = max(0, min(50, int(data.get("foul_count", 0))))
            return JsonResponse({
                "score": score,
                "big_jin": big_jin,
                "small_jin": small_jin,
                "golden_nine": golden_nine,
                "foul_count": foul_count,
            })
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({"error": "无效的请求数据"}, status=400)
    return JsonResponse({"error": "Invalid request"}, status=400)


@login_required
@require_http_methods(["POST"])
def game_end(request):
    """关灯：保存比赛结果"""
    try:
        data = json.loads(request.body)
        game_type = data.get("game_type")

        # 验证游戏类型
        if game_type not in [DailyRecord.TYPE_8BALL, DailyRecord.TYPE_SCORE]:
            return JsonResponse({"error": "无效的游戏类型"}, status=400)

        # 清理对手名称
        opponent_name = _sanitize_input(
            data.get("opponent_name", ""),
            max_length=64,
            pattern=r"[^\w\s\u4e00-\u9fff\-\(\)\[\]]"
        )

        if game_type == DailyRecord.TYPE_8BALL:
            # 黑八模式 - 严格范围验证
            record = DailyRecord.objects.create(
                user=request.user,
                game_type=game_type,
                date=date_type.today(),
                opponent_name=opponent_name,
                score_for=max(0, min(50, int(data.get("score_for", 0)))),
                score_against=max(0, min(50, int(data.get("score_against", 0)))),
                clear_in_count=max(0, min(50, int(data.get("clear_in", 0)))),
                clear_boom_count=max(0, min(50, int(data.get("clear_boom", 0)))),
            )
        elif game_type == DailyRecord.TYPE_SCORE:
            # 追分模式 - 严格范围验证
            record = DailyRecord.objects.create(
                user=request.user,
                game_type=game_type,
                date=date_type.today(),
                opponent_name=opponent_name,
                score=max(-200, min(200, int(data.get("score", 0)))),
                big_jin=max(0, min(50, int(data.get("big_jin", 0)))),
                small_jin=max(0, min(50, int(data.get("small_jin", 0)))),
                golden_nine=max(0, min(50, int(data.get("golden_nine", 0)))),
                foul_count=max(0, min(50, int(data.get("foul_count", 0)))),
            )

        return JsonResponse({"success": True, "record_id": record.pk})
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({"error": "无效的请求数据"}, status=400)

