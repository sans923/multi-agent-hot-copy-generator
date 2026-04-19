"""
文档表模型（documents）
=======================
存储用户上传的背景资料文档（产品介绍、品牌手册、往期爆款等）
这些文档会被向量化存入 ChromaDB，用于 RAG（检索增强生成）

RAG 工作原理（简化版）：
1. 用户上传文档 -> 切分成小块 -> 向量化 -> 存入 ChromaDB
2. 生成文案时 -> 把需求向量化 -> 在 ChromaDB 中搜索最相关的文档块
3. 把相关内容作为"参考资料"传给 Agent -> 生成更贴近用户品牌风格的文案
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, BigInteger, JSON
from sqlalchemy.orm import relationship

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="文档ID")

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="上传者用户ID"
    )

    # 原始文件名（用户上传时的名字，不要直接用于存储路径，防止路径穿越攻击）
    original_filename = Column(String(255), nullable=False, comment="原始文件名")

    # 文件类型：pdf / txt / docx / md
    file_type = Column(String(20), nullable=False, comment="文件类型")

    # 文件大小（字节数），BigInteger 支持大文件
    file_size = Column(BigInteger, nullable=True, comment="文件大小(字节)")

    # 文档内容（提取后的纯文本，用于向量化）
    content = Column(Text, nullable=True, comment="提取的文档纯文本内容")

    # 向量化状态：pending/processing/completed/failed
    embedding_status = Column(
        String(20),
        default="pending",
        nullable=False,
        comment="向量化状态"
    )

    # ChromaDB 中对应的 collection 名称（用于检索时定向搜索）
    chroma_collection = Column(
        String(100),
        nullable=True,
        comment="在ChromaDB中的collection名称"
    )

    # 向量化分块数量（一个大文档会被切成多个小块分别向量化）
    chunk_count = Column(Integer, default=0, comment="向量化分块数量")

    # 文档摘要（由 AI 生成，用于快速了解文档内容）
    summary = Column(Text, nullable=True, comment="AI生成的文档摘要")

    # 额外元数据（存储任何不适合单独建列的信息）
    metadata_json = Column(JSON, nullable=True, comment="额外元数据")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="上传时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间")

    user = relationship("User", back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.original_filename} status={self.embedding_status}>"
