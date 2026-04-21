"""
通用响应 Schema
===============
定义统一的 API 响应格式，让所有接口的返回结构保持一致

统一响应格式的好处：
- 前端只需要写一套解析代码
- 错误处理统一（永远检查 success 字段）
- 方便后期添加全局字段（如 request_id 用于追踪）

响应格式：
{
    "success": true,
    "message": "操作成功",
    "data": { ... }        // 成功时的数据
}

或者错误时：
{
    "success": false,
    "message": "用户名已存在",
    "data": null
}
"""

from typing import TypeVar, Generic, Optional, Any
from pydantic import BaseModel, Field


# TypeVar 用于泛型，让 data 字段可以是任意类型
# 这样 ApiResponse[UserResponse] 表示 data 是 UserResponse 类型
T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """
    通用 API 响应包装器
    
    使用示例（在路由函数中）：
        return ApiResponse(success=True, message="登录成功", data=token_data)
        return ApiResponse(success=False, message="密码错误")
    """
    success: bool = True
    message: str = "操作成功"
    data: Optional[T] = None


class PaginationResponse(BaseModel, Generic[T]):
    """
    分页响应格式（列表接口用）
    
    返回示例：
    {
        "items": [...],
        "total": 100,
        "page": 1,
        "page_size": 20,
        "total_pages": 5
    }
    """
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginationParams(BaseModel):
    """
    分页请求参数（作为查询参数使用）
    
    使用示例（在路由函数中）：
        @router.get("/tasks")
        def list_tasks(pagination: PaginationParams = Depends()):
            ...
    """
    page: int = Field(default=1, ge=1, description="页码，从1开始")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量，最多100")

    @property
    def offset(self) -> int:
        """计算数据库查询的偏移量"""
        return (self.page - 1) * self.page_size


