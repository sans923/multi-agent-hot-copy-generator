import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.core.security import hash_password

db = SessionLocal()

fake_users = [
    {"username": "lisi",    "email": "lisi@example.com",    "password": "Lisi123456",    "nickname": "李四", "is_admin": False},
    {"username": "wangwu",  "email": "wangwu@example.com",  "password": "Wangwu123456",  "nickname": "王五", "is_admin": False},
    {"username": "zhaoliu", "email": "zhaoliu@example.com", "password": "Zhaoliu123456", "nickname": "赵六", "is_admin": False},
    {"username": "admin2",  "email": "admin@example.com",   "password": "Admin123456",   "nickname": "管理员", "is_admin": True},
]

for u in fake_users:
    exists = db.query(User).filter(User.email == u["email"]).first()
    if exists:
        print(f"skip (exists): {u['email']}")
        continue
    user = User(
        username=u["username"],
        email=u["email"],
        hashed_password=hash_password(u["password"]),
        nickname=u["nickname"],
        is_admin=u["is_admin"],
        is_active=True,
    )
    db.add(user)
    print(f"created: {u['email']}  password={u['password']}  is_admin={u['is_admin']}")

db.commit()
db.close()
print("done")
