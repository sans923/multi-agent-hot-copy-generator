"""
用户表模型（users）
==================
对应数据库中的 users 表

字段设计思路：
- id：主键，自增整数，唯一标识一个用户
- username / email：用户名和邮箱，用于登录
- hashed_password：密码哈希值（绝对不存明文密码！）
- is_active：账号状态，软删除用（不真正删数据，只标记为不活跃）
- is_admin：是否是管理员（后台管理功能用）
- created_at / updated_at：创建和最后修改时间，便于追踪
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """
    ORM 模型 = 一张数据库表
    
    类名 User -> 表名 users（SQLAlchemy 自动转为小写复数，
    也可以用 __tablename__ 手动指定）
    
    每个类属性 = 表中的一个字段（列）
    Column(...) 定义字段的类型和约束
    """
    __tablename__ = "users"

    # 主键：每个表必须有主键，用于唯一标识一行数据
    # autoincrement=True：新插入一行时自动 +1，不需要手动指定
    id = Column(Integer, primary_key=True, autoincrement=True, comment="用户ID")

    # String(50) 对应 VARCHAR(50)，最长50个字符
    # unique=True：数据库层面保证不重复（即使代码没检查也不会写入重复值）
    # nullable=False：不允许为空（必填字段）
    # index=True：在这个字段上建索引，加快查询速度
    username = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="用户名（登录用）"
    )

    email = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="邮箱（登录用）"
    )

    # 密码哈希：存 bcrypt 哈希后的字符串，如 "$2b$12$..."
    # 哈希值是单向的，无法反向得到原密码（安全核心）
    hashed_password = Column(
        String(128),
        nullable=False,
        comment="bcrypt 加密后的密码"
    )

    # Boolean 对应 TINYINT(1)，True=1 False=0
    # default=True：新用户默认是激活状态
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="账号是否激活（False表示封号）"
    )

    is_admin = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否是管理员"
    )

    # Text 用于存较长的文字（无长度限制），String 有长度上限
    nickname = Column(String(50), nullable=True, comment="昵称（展示用）")
    avatar_url = Column(Text, nullable=True, comment="头像URL")

    # default=datetime.utcnow：插入时自动填入当前UTC时间
    # onupdate=datetime.utcnow：更新时自动更新时间戳
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="注册时间"
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="最后更新时间"
    )

    # ---- 关联关系（ORM层面的，不是数据库字段）----
    # relationship 告诉 SQLAlchemy 这个 User 关联了哪些 Task
    # 可以通过 user.tasks 直接获取这个用户的所有任务（自动 JOIN 查询）
    # back_populates="user" 与 Task 模型中的 relationship 对应，建立双向关联
    tasks = relationship("Task", back_populates="user", lazy="dynamic")
    documents = relationship("Document", back_populates="user", lazy="dynamic")

    def __repr__(self) -> str:
        """让 print(user) 时显示有意义的信息（调试用）"""
        return f"<User id={self.id} username={self.username}>"
