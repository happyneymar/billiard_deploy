from django.contrib import admin

from diary.models import BattleRequest, BattleResponse, DailyMedia, DailyRecord, Moment, MomentComment, MomentLike, MomentMedia


@admin.register(DailyRecord)
class DailyRecordAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "date",
        "game_type",
        "opponent_name",
        "score_for",
        "score_against",
        "clear_in_count",
        "clear_boom_count",
        "big_jin",
        "small_jin",
        "golden_nine",
        "foul_count",
        "score",
        "updated_at",
    ]
    list_filter = ["game_type", "date", "user"]
    search_fields = ["user__username", "opponent_name", "comment"]


@admin.register(DailyMedia)
class DailyMediaAdmin(admin.ModelAdmin):
    list_display = ["id", "record", "media_type", "uploaded_at"]
    list_filter = ["media_type", "uploaded_at"]


@admin.register(Moment)
class MomentAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "created_at", "updated_at"]
    list_filter = ["created_at", "user"]
    search_fields = ["user__username", "text"]


@admin.register(MomentMedia)
class MomentMediaAdmin(admin.ModelAdmin):
    list_display = ["id", "moment", "media_type", "uploaded_at"]
    list_filter = ["media_type", "uploaded_at"]


@admin.register(MomentLike)
class MomentLikeAdmin(admin.ModelAdmin):
    list_display = ["id", "moment", "user", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__username", "moment__text"]


@admin.register(MomentComment)
class MomentCommentAdmin(admin.ModelAdmin):
    list_display = ["id", "moment", "user", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__username", "text", "moment__text"]

@admin.register(BattleRequest)
class BattleRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "battle_time", "location", "player_count", "created_at"]
    list_filter = ["battle_time", "user"]
    search_fields = ["user__username", "location", "note"]


@admin.register(BattleResponse)
class BattleResponseAdmin(admin.ModelAdmin):
    list_display = ["id", "battle", "user", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__username", "battle__user__username", "battle__location"]
