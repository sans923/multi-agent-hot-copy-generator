"""
ORM 模型包
==========
把所有模型汇集到一个包里，方便统一导入

SQLAlchemy 要知道有哪些表，必须在 Base.metadata.create_all() 之前
import 这些模型类，所以这里做了统一导出
"""

from app.models.user import User
from app.models.task import Task
from app.models.document import Document
from app.models.copy import Copy
from app.models.agent_log import AgentLog
from app.models.orchestration_audit_log import OrchestrationAuditLog
from app.models.hotlist_sync import HotlistSync
from app.models.system_log import SystemLog
from app.models.toutiao_reference import ToutiaoReference
from app.models.style_card import StyleCard
from app.models.memory_index_job import MemoryIndexJob

__all__ = [
    "User",
    "Task",
    "Document",
    "Copy",
    "AgentLog",
    "OrchestrationAuditLog",
    "HotlistSync",
    "SystemLog",
    "ToutiaoReference",
    "StyleCard",
    "MemoryIndexJob",
]
