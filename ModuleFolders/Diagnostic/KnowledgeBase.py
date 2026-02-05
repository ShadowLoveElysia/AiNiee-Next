"""
知识库模块 - 低成本诊断层

支持:
1. FAQ缓存 - 完全免费
2. 关键词检索 - 免费
3. 向量检索 - 可选本地模型(免费)或API
"""

import os
import hashlib
try:
    import rapidjson as json
except ImportError:
    import json
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

from ModuleFolders.Diagnostic.i18n import get_text


@dataclass
class KnowledgeItem:
    """知识条目"""
    id: str
    question: str           # 问题描述
    keywords: List[str]     # 关键词
    answer: str             # 解答
    category: str           # 分类
    hit_count: int = 0      # 命中次数


class KnowledgeBase:
    """
    知识库

    分层检索策略:
    1. FAQ缓存精确匹配 (hash)
    2. 关键词匹配
    3. 向量相似度 (可选)
    """

    def __init__(self, base_path: str = None, lang: str = "zh_CN"):
        if base_path is None:
            base_path = os.path.join(".", "Resource", "Diagnostic")

        self.base_path = base_path
        self.lang = lang
        self.kb_path = os.path.join(base_path, "knowledge_base.json")
        self.faq_cache_path = os.path.join(base_path, "faq_cache.json")

        # 确保目录存在
        os.makedirs(base_path, exist_ok=True)

        # 加载数据
        self.knowledge_items: Dict[str, KnowledgeItem] = {}
        self.faq_cache: Dict[str, dict] = {}  # hash -> answer

        self._load_knowledge_base()
        self._load_faq_cache()

    def _load_knowledge_base(self):
        """加载知识库"""
        if not os.path.exists(self.kb_path):
            self._init_default_knowledge()
            return

        try:
            with open(self.kb_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item_data in data.get("items", []):
                    item = KnowledgeItem(**item_data)
                    self.knowledge_items[item.id] = item
        except Exception:
            self._init_default_knowledge()

    def _load_faq_cache(self):
        """加载FAQ缓存"""
        if os.path.exists(self.faq_cache_path):
            try:
                with open(self.faq_cache_path, 'r', encoding='utf-8') as f:
                    self.faq_cache = json.load(f)
            except Exception:
                self.faq_cache = {}

    def _save_faq_cache(self):
        """保存FAQ缓存"""
        try:
            with open(self.faq_cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.faq_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _hash_query(self, query: str) -> str:
        """生成查询的hash"""
        # 简单标准化: 小写 + 去除多余空格
        normalized = ' '.join(query.lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    def search_faq_cache(self, query: str) -> Optional[dict]:
        """
        搜索FAQ缓存 (精确匹配)

        Returns:
            匹配的缓存条目或None
        """
        query_hash = self._hash_query(query)
        return self.faq_cache.get(query_hash)

    def add_to_faq_cache(self, query: str, answer: dict):
        """添加到FAQ缓存"""
        query_hash = self._hash_query(query)
        self.faq_cache[query_hash] = {
            "query": query,
            "answer": answer,
            "hit_count": 0
        }
        self._save_faq_cache()

    def search_by_keywords(self, error_text: str, top_k: int = 3) -> List[Tuple[KnowledgeItem, float]]:
        """
        关键词检索

        Returns:
            [(KnowledgeItem, score), ...] 按相关度排序
        """
        results = []
        error_lower = error_text.lower()

        for item in self.knowledge_items.values():
            score = 0.0
            matched_keywords = 0

            for keyword in item.keywords:
                if keyword.lower() in error_lower:
                    matched_keywords += 1
                    # 关键词越长，权重越高
                    score += len(keyword) / 10.0

            if matched_keywords > 0:
                # 匹配的关键词比例
                score += matched_keywords / len(item.keywords) * 0.5
                results.append((item, score))

        # 按分数排序
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _init_default_knowledge(self):
        """初始化默认知识库"""
        default_items = [
            {
                "id": "kb_001",
                "question": "API Key 配置问题",
                "keywords": ["api_key", "api key", "401", "认证", "authentication", "invalid key"],
                "answer": "API Key 问题通常有以下原因:\n1. Key 未正确复制（检查首尾空格）\n2. Key 已过期或被禁用\n3. Key 没有对应模型的权限\n\n解决方案:\n1. 重新复制 API Key\n2. 在 API 提供商后台检查 Key 状态\n3. 确认账户余额充足",
                "category": "配置问题",
                "hit_count": 0
            },
            {
                "id": "kb_002",
                "question": "网络连接问题",
                "keywords": ["connection", "timeout", "网络", "代理", "proxy", "ssl", "refused"],
                "answer": "网络问题排查步骤:\n1. 检查网络连接是否正常\n2. 如果使用代理，确认代理设置正确\n3. 部分 API 需要科学上网\n4. SSL 错误通常是代理或证书问题",
                "category": "网络问题",
                "hit_count": 0
            },
            {
                "id": "kb_003",
                "question": "模型选择问题",
                "keywords": ["model", "模型", "KeyError", "not found", "不存在"],
                "answer": "模型相关问题:\n1. 确保在界面上选择了模型并保存\n2. 检查模型名称是否正确\n3. 部分模型需要特殊权限\n4. 自定义平台需要填写正确的模型名",
                "category": "配置问题",
                "hit_count": 0
            },
            {
                "id": "kb_004",
                "question": "文件读取问题",
                "keywords": ["file", "文件", "路径", "path", "FileNotFoundError", "permission"],
                "answer": "文件问题排查:\n1. 确认文件路径正确\n2. 检查文件是否被其他程序占用\n3. 确认有读写权限\n4. 路径中避免使用特殊字符",
                "category": "文件问题",
                "hit_count": 0
            },
            {
                "id": "kb_005",
                "question": "配置文件损坏",
                "keywords": ["config", "配置", "json", "JSONDecodeError", "格式"],
                "answer": "配置文件问题:\n1. 不要手动编辑配置文件\n2. 如果已损坏，删除 Resource/config.json 让程序重新生成\n3. 备份重要设置后再删除",
                "category": "配置问题",
                "hit_count": 0
            },
            {
                "id": "kb_006",
                "question": "依赖包问题",
                "keywords": ["import", "module", "依赖", "pip", "install", "ModuleNotFoundError", "uv"],
                "answer": "依赖问题解决:\n1. 运行: uv sync\n2. 或单独安装: uv add <包名>\n3. 如果使用pip: uv pip install -r requirements.txt\n4. 确保使用正确的 Python 版本",
                "category": "环境问题",
                "hit_count": 0
            },
            {
                "id": "kb_007",
                "question": "请求限流问题",
                "keywords": ["429", "rate limit", "限流", "too many", "quota"],
                "answer": "限流问题处理:\n1. 降低并发数设置\n2. 增加请求间隔\n3. 检查账户是否有配额限制\n4. 考虑升级 API 套餐",
                "category": "API问题",
                "hit_count": 0
            },
            {
                "id": "kb_008",
                "question": "上下文长度超限",
                "keywords": ["context", "token", "length", "too long", "超长", "max"],
                "answer": "上下文超限解决:\n1. 减少单次翻译的文本量\n2. 调整分段设置\n3. 使用支持更长上下文的模型\n4. 精简提示词",
                "category": "API问题",
                "hit_count": 0
            },
            {
                "id": "kb_009",
                "question": "服务器错误 (500/502/503)",
                "keywords": ["500", "502", "503", "server error", "bad gateway", "service unavailable", "服务器", "网关"],
                "answer": "服务器错误通常是API提供商的问题:\n\n500 Internal Server Error:\n- API服务器内部错误，稍后重试\n\n502 Bad Gateway:\n- 网关错误，通常是服务器过载\n- 稍等几分钟后重试\n\n503 Service Unavailable:\n- 服务暂时不可用，可能在维护\n- 检查API提供商状态页面\n\n解决方案:\n1. 等待几分钟后重试\n2. 降低并发数\n3. 检查API提供商状态",
                "category": "API问题",
                "hit_count": 0
            },
            {
                "id": "kb_010",
                "question": "权限错误 (403)",
                "keywords": ["403", "forbidden", "permission", "权限", "禁止访问"],
                "answer": "403 权限错误原因:\n1. API Key 没有访问该模型的权限\n2. 账户被限制或封禁\n3. 请求的资源不允许访问\n\n解决方案:\n1. 检查API Key权限设置\n2. 确认账户状态正常\n3. 联系API提供商确认权限",
                "category": "API问题",
                "hit_count": 0
            }
        ]

        for item_data in default_items:
            item = KnowledgeItem(**item_data)
            self.knowledge_items[item.id] = item

        self._save_knowledge_base()

    def _save_knowledge_base(self):
        """保存知识库"""
        try:
            data = {
                "version": "1.0",
                "items": [
                    {
                        "id": item.id,
                        "question": item.question,
                        "keywords": item.keywords,
                        "answer": item.answer,
                        "category": item.category,
                        "hit_count": item.hit_count
                    }
                    for item in self.knowledge_items.values()
                ]
            }
            with open(self.kb_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_context_for_llm(self, error_text: str, max_items: int = 2) -> str:
        """
        获取用于LLM的上下文信息

        只返回最相关的知识条目，控制token消耗
        """
        results = self.search_by_keywords(error_text, top_k=max_items)

        if not results:
            return ""

        context_parts = [get_text("kb_context_header", self.lang)]
        for item, score in results:
            context_parts.append(f"\n【{item.question}】\n{item.answer}")

        return "\n".join(context_parts)
