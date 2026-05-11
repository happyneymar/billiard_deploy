"""
安全中间件 - 限流和请求验证
"""
import time
from collections import defaultdict
from threading import Lock

from django.http import JsonResponse


class RateLimitStore:
    """线程安全的限流存储"""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._data = defaultdict(list)
                    cls._instance._cleanup_interval = 3600  # 每小时清理一次
                    cls._instance._last_cleanup = time.time()
        return cls._instance

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """检查是否允许请求"""
        self._cleanup_if_needed()

        now = time.time()
        window_start = now - window_seconds

        # 清理过期的请求记录
        self._data[key] = [ts for ts in self._data[key] if ts > window_start]

        if len(self._data[key]) >= max_requests:
            return False

        self._data[key].append(now)
        return True

    def get_retry_after(self, key: str, window_seconds: int) -> int:
        """获取需要等待的秒数"""
        if key not in self._data or not self._data[key]:
            return 0

        oldest = min(self._data[key])
        elapsed = time.time() - oldest
        return max(0, int(window_seconds - elapsed))

    def _cleanup_if_needed(self):
        """定期清理过期数据"""
        now = time.time()
        if now - self._last_cleanup > self._cleanup_interval:
            self._data.clear()
            self._last_cleanup = now


class RateLimitMiddleware:
    """
    基于 IP 和用户的限流中间件

    限流规则：
    - 匿名用户: 较宽松的浏览额度，认证接口单独限制
    - 登录用户: 更高的正常操作额度
    - 不同类型请求分别计数，避免页面浏览误伤按钮/API 操作
    """

    # 不同端点的限流配置 (max_requests, window_seconds)。
    ANONYMOUS_RATE_LIMITS = {
        "api": (60, 60),
        "auth": (30, 60),
        "default": (120, 60),
        "upload": (30, 60),
    }
    AUTHENTICATED_RATE_LIMITS = {
        "api": (240, 60),
        "auth": (30, 60),
        "default": (240, 60),
        "upload": (60, 60),
    }

    # 豁免的路径（不需要限流）
    EXEMPT_PATHS = [
        "/static/",
        "/media/",
        "/favicon.ico",
        "/logout/",
    ]

    def __init__(self, get_response):
        self.get_response = get_response
        self.store = RateLimitStore()

    def __call__(self, request):
        # 豁免路径
        if self._is_exempt(request.path):
            return self.get_response(request)

        # 确定限流类别
        rate_type = self._get_rate_type(request.path)
        max_requests, window_seconds = self._get_rate_limit(request, rate_type)

        # 生成限流键
        rate_key = self._get_rate_key(request, rate_type)

        # 检查限流
        if not self.store.is_allowed(rate_key, max_requests, window_seconds):
            retry_after = self.store.get_retry_after(rate_key, window_seconds)
            return JsonResponse(
                {
                    "error": "请求过于频繁，请稍后再试",
                    "retry_after": retry_after,
                },
                status=429,
                headers={"Retry-After": str(retry_after)},
            )

        response = self.get_response(request)

        # 在响应头中添加限流信息
        remaining = max_requests - len([ts for ts in self.store._data.get(rate_key, []) if ts > time.time() - window_seconds])
        response["X-RateLimit-Limit"] = str(max_requests)
        response["X-RateLimit-Remaining"] = str(max(0, remaining))

        return response

    def _is_exempt(self, path: str) -> bool:
        """检查路径是否豁免限流"""
        return any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS)

    def _get_rate_type(self, path: str) -> str:
        """根据路径确定限流类型"""
        if "/api/" in path or path.startswith("/game_update_score") or path.startswith("/game_end"):
            return "api"
        if "/login" in path or "/register" in path:
            return "auth"
        if "/upload" in path or "media" in path:
            return "upload"
        return "default"

    def _get_rate_limit(self, request, rate_type: str) -> tuple[int, int]:
        limits = (
            self.AUTHENTICATED_RATE_LIMITS
            if hasattr(request, "user") and request.user.is_authenticated
            else self.ANONYMOUS_RATE_LIMITS
        )
        return limits.get(rate_type, limits["default"])

    def _get_rate_key(self, request, rate_type: str) -> str:
        """生成限流键"""
        # 优先使用用户ID，fallback 到 IP
        if hasattr(request, "user") and request.user.is_authenticated:
            return f"{rate_type}:user:{request.user.id}"
        return f"{rate_type}:ip:{self._get_client_ip(request)}"

    def _get_client_ip(self, request) -> str:
        """获取客户端真实IP"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

