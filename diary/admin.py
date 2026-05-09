from django.contrib import admin

from diary.models import DailyMedia, DailyRecord


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
