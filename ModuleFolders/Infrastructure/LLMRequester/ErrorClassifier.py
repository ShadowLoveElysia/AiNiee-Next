"""
错误分类器 - 区分硬伤错误与软伤错误

硬伤错误（需永久降级）：
- 400 Bad Request：格式不匹配、参数错误
- 401 Unauthorized：API Key 无效
- 403 Forbidden：权限不足
- 404 Not Found：端点不存在

软伤错误（需智能等待/降低并发）：
- 429 Too Many Requests：频率限制
- 500 Internal Server Error：服务器内部错误
- 502 Bad Gateway：网关错误
- 503 Service Unavailable：服务不可用
- 504 Gateway Timeout：网关超时
- Timeout：请求超时
- Connection Error：连接错误
"""

from enum import Enum
from typing import Tuple, Optional
import re


class ErrorType(Enum):
    """错误类型"""
    HARD_ERROR = "hard"      # 硬伤：需永久降级
    SOFT_ERROR = "soft"      # 软伤：需智能等待
    SUCCESS = "success"      # 成功
    UNKNOWN = "unknown"      # 未知错误


class ErrorClassifier:
    """错误分类器"""

    # 硬伤错误特征
    HARD_ERROR_PATTERNS = [
        # HTTP 状态码
        r"400",
        r"401",
        r"403",
        r"404",
        # 格式/参数错误关键词
        r"invalid.*param",
        r"invalid.*field",
        r"invalid.*format",
        r"unsupported.*field",
        r"unknown.*field",
        r"bad.*request",
        r"malformed",
        r"schema.*error",
        r"validation.*error",
        r"not.*supported",
        r"api.*key.*invalid",
        r"authentication.*failed",
    ]

    # 软伤错误特征
    SOFT_ERROR_PATTERNS = [
        # HTTP 状态码
        r"429",
        r"500",
        r"502",
        r"503",
        r"504",
        # 限流/超时关键词
        r"rate.*limit",
        r"too.*many.*requests",
        r"timeout",
        r"timed.*out",
        r"connection.*error",
        r"connection.*reset",
        r"connection.*refused",
        r"service.*unavailable",
        r"bad.*gateway",
        r"internal.*server.*error",
        r"overloaded",
        r"capacity",
        r"retry.*later",
    ]

    # 缓存相关硬伤特征（需要降级缓存功能）
    CACHE_HARD_ERROR_PATTERNS = [
        r"cache.*control.*not.*supported",
        r"cache.*not.*supported",
        r"unknown.*field.*cache",
        r"invalid.*cache",
        r"ephemeral.*not.*supported",
    ]

    @classmethod
    def classify(cls, error_message: str) -> Tuple[ErrorType, str]:
        """
        分类错误类型

        Returns:
            Tuple[ErrorType, str]: (错误类型, 分类原因)
        """
        if not error_message:
            return ErrorType.SUCCESS, ""

        error_lower = error_message.lower()

        # 检查硬伤
        for pattern in cls.HARD_ERROR_PATTERNS:
            if re.search(pattern, error_lower):
                return ErrorType.HARD_ERROR, f"matched: {pattern}"

        # 检查软伤
        for pattern in cls.SOFT_ERROR_PATTERNS:
            if re.search(pattern, error_lower):
                return ErrorType.SOFT_ERROR, f"matched: {pattern}"

        return ErrorType.UNKNOWN, "no pattern matched"

    @classmethod
    def is_cache_related_error(cls, error_message: str) -> bool:
        """检查是否为缓存相关的硬伤错误"""
        if not error_message:
            return False

        error_lower = error_message.lower()
        for pattern in cls.CACHE_HARD_ERROR_PATTERNS:
            if re.search(pattern, error_lower):
                return True
        return False

    @classmethod
    def should_disable_cache(cls, error_message: str) -> bool:
        """
        判断是否应该禁用缓存

        只有硬伤错误且与缓存相关时才禁用
        软伤错误（如429、500）不应禁用缓存
        """
        error_type, _ = cls.classify(error_message)

        # 软伤错误：不禁用缓存
        if error_type == ErrorType.SOFT_ERROR:
            return False

        # 硬伤错误：检查是否与缓存相关
        if error_type == ErrorType.HARD_ERROR:
            return cls.is_cache_related_error(error_message)

        return False

    @classmethod
    def should_retry(cls, error_message: str) -> bool:
        """判断是否应该重试"""
        error_type, _ = cls.classify(error_message)
        # 软伤错误可以重试
        return error_type == ErrorType.SOFT_ERROR

    @classmethod
    def should_reduce_concurrency(cls, error_message: str) -> bool:
        """判断是否应该降低并发"""
        error_type, _ = cls.classify(error_message)
        if error_type != ErrorType.SOFT_ERROR:
            return False

        error_lower = error_message.lower()
        # 429 或 overloaded 时建议降低并发
        return bool(re.search(r"429|rate.*limit|overloaded|capacity", error_lower))
