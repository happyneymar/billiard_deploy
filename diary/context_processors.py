from diary.models import DirectBattleRequest


def pending_message_count(request):
    if not request.user.is_authenticated:
        return {"pending_message_count": 0}
    return {
        "pending_message_count": DirectBattleRequest.objects.filter(
            to_user=request.user,
            status=DirectBattleRequest.STATUS_PENDING,
        ).count()
    }
