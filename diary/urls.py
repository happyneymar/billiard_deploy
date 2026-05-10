from django.urls import path

from diary import views

app_name = "diary"

urlpatterns = [
    # 带权限校验的媒体展示（避免在 DEBUG 下直接暴露 /media/）
    # 注意：media_delete 必须在 media_serve 之前，否则会被误匹配
    path("media/<int:pk>/delete/", views.media_delete, name="media_delete"),
    path("media/<path:relative_path>", views.media_serve, name="media_serve"),
    path("", views.record_list, name="record_list"),
    path("records/new/", views.record_new, name="record_new"),
    path("records/<int:pk>/", views.record_detail, name="record_detail"),
    path("records/<int:pk>/delete/", views.record_delete, name="record_delete"),
    path("battles/", views.battles, name="battles"),
    path("battles/created/", views.battle_created, name="battle_created"),
    path("battles/history/", views.battle_history, name="battle_history"),
    path("battles/<int:pk>/join/", views.battle_join, name="battle_join"),
    path("friends/", views.friends, name="friends"),
    path("friends/add/", views.friend_add, name="friend_add"),
    path("friends/requests/", views.friend_requests, name="friend_requests"),
    path("friends/requests/<int:pk>/accept/", views.friend_request_accept, name="friend_request_accept"),
    path("friends/requests/<int:pk>/decline/", views.friend_request_decline, name="friend_request_decline"),
    path("friends/<str:username>/message/", views.private_message_new, name="private_message_new"),
    path("friends/<str:username>/battle/", views.direct_battle_new, name="direct_battle_new"),
    path("messages/", views.user_messages, name="messages"),
    path("messages/direct-battles/<int:pk>/accept/", views.direct_battle_accept, name="direct_battle_accept"),
    path("messages/direct-battles/<int:pk>/decline/", views.direct_battle_decline, name="direct_battle_decline"),
    path("moments/", views.moments_feed, name="moments"),
    path("moments/<int:pk>/like/", views.moment_like, name="moment_like"),
    path("moments/<int:pk>/comment/", views.moment_comment, name="moment_comment"),
    path("moments/<int:pk>/delete/", views.moment_delete, name="moment_delete"),
    path("moments/comments/<int:pk>/delete/", views.moment_comment_delete, name="moment_comment_delete"),
    path("register/", views.register, name="register"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.user_logout, name="logout"),
    path("password-reset/", views.password_reset, name="password_reset"),
    path("password-reset/set/", views.password_reset_set, name="password_reset_set"),
    path("search/", views.user_search, name="user_search"),
    path("u/<str:username>/moments/", views.user_moments, name="user_moments"),
    path("u/<str:username>/", views.public_profile, name="public_profile"),
    # 开灯功能
    path("game/start/", views.game_start, name="game_start"),
    path("game/play/<str:game_type>/", views.game_play, name="game_play"),
    path("api/game/update-score/", views.game_update_score, name="game_update_score"),
    path("api/game/end/", views.game_end, name="game_end"),
]

