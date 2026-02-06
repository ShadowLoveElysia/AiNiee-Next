"""
Provider Fingerprint - API 特性指纹记录系统

功能：
- 记录各 API Provider 的特性支持情况
- 自动检测并标记不支持的功能（缓存、流式等）
- 下次启动时静默降级，避免重复报错
"""

import hashlib
import threading
from typing import Optional, Dict, Any
from enum import Enum

from ModuleFolders.Base.Base import Base


class FeatureSupport(Enum):
    """功能支持状态"""
    UNKNOWN = "unknown"      # 未知，需要探测
    SUPPORTED = "supported"  # 支持
    UNSUPPORTED = "unsupported"  # 不支持


class ProviderFingerprint(Base):
    """Provider 特性指纹管理器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._fingerprints: Dict[str, Dict[str, Any]] = {}
        self._load_fingerprints()
        self._initialized = True

    def _get_provider_key(self, api_url: str) -> str:
        """生成 Provider 唯一标识"""
        # 提取主机部分作为 key
        from urllib.parse import urlparse
        parsed = urlparse(api_url)
        host = parsed.netloc or parsed.path.split('/')[0]
        return hashlib.md5(host.encode()).hexdigest()[:12]

    def _load_fingerprints(self) -> None:
        """从配置加载指纹数据"""
        try:
            config = self.load_config()
            self._fingerprints = config.get("provider_fingerprints", {})
        except Exception:
            self._fingerprints = {}

    def _save_fingerprints(self) -> None:
        """保存指纹数据到配置"""
        try:
            config = self.load_config()
            config["provider_fingerprints"] = self._fingerprints
            self.save_config(config)
        except Exception as e:
            self.warning(f"Failed to save provider fingerprints: {e}")

    def get_cache_support(self, api_url: str) -> FeatureSupport:
        """获取 Provider 的缓存支持状态"""
        key = self._get_provider_key(api_url)
        fp = self._fingerprints.get(key, {})
        status = fp.get("cache_support", FeatureSupport.UNKNOWN.value)
        return FeatureSupport(status)

    def set_cache_support(self, api_url: str, supported: bool) -> None:
        """设置 Provider 的缓存支持状态"""
        key = self._get_provider_key(api_url)
        if key not in self._fingerprints:
            self._fingerprints[key] = {"api_url": api_url}

        status = FeatureSupport.SUPPORTED if supported else FeatureSupport.UNSUPPORTED
        self._fingerprints[key]["cache_support"] = status.value
        self._save_fingerprints()

    def get_stream_support(self, api_url: str, model: str) -> FeatureSupport:
        """获取 Provider + Model 的流式支持状态"""
        key = self._get_provider_key(api_url)
        fp = self._fingerprints.get(key, {})
        stream_models = fp.get("stream_models", {})
        status = stream_models.get(model, FeatureSupport.UNKNOWN.value)
        return FeatureSupport(status)

    def set_stream_support(self, api_url: str, model: str, supported: bool) -> None:
        """设置 Provider + Model 的流式支持状态"""
        key = self._get_provider_key(api_url)
        if key not in self._fingerprints:
            self._fingerprints[key] = {"api_url": api_url}

        if "stream_models" not in self._fingerprints[key]:
            self._fingerprints[key]["stream_models"] = {}

        status = FeatureSupport.SUPPORTED if supported else FeatureSupport.UNSUPPORTED
        self._fingerprints[key]["stream_models"][model] = status.value
        self._save_fingerprints()

    def should_use_cache(self, api_url: str) -> bool:
        """判断是否应该使用缓存功能"""
        status = self.get_cache_support(api_url)
        # 未知状态默认尝试使用
        return status != FeatureSupport.UNSUPPORTED

    def mark_cache_unsupported(self, api_url: str, error_msg: str) -> None:
        """标记 Provider 不支持缓存（基于错误信息）"""
        from ModuleFolders.Infrastructure.LLMRequester.ErrorClassifier import ErrorClassifier

        if ErrorClassifier.is_cache_related_error(error_msg):
            self.set_cache_support(api_url, False)
            self.info(f"Provider fingerprint updated: cache disabled for {api_url}")

    def get_fingerprint_summary(self, api_url: str) -> Dict[str, Any]:
        """获取 Provider 的完整指纹摘要"""
        key = self._get_provider_key(api_url)
        return self._fingerprints.get(key, {})

    def clear_fingerprint(self, api_url: str) -> None:
        """清除指定 Provider 的指纹（用于重置）"""
        key = self._get_provider_key(api_url)
        if key in self._fingerprints:
            del self._fingerprints[key]
            self._save_fingerprints()

    def clear_all_fingerprints(self) -> None:
        """清除所有指纹数据"""
        self._fingerprints = {}
        self._save_fingerprints()
