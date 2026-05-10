from diary.models import DirectBattleRequest, PrivateMessage


def pending_message_count(request):
    if not request.user.is_authenticated:
        return {"pending_message_count": 0}
    direct_battle_count = DirectBattleRequest.objects.filter(
        to_user=request.user,
        status=DirectBattleRequest.STATUS_PENDING,
    ).count()
    private_message_count = PrivateMessage.objects.filter(
        to_user=request.user,
        is_read=False,
    ).count()
    return {"pending_message_count": direct_battle_count + private_message_count}
