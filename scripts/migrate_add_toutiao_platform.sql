-- 已有 MySQL 数据库需要扩展 tasks.platform 枚举；新建数据库无需执行。
ALTER TABLE tasks
MODIFY COLUMN platform ENUM(
  'TOUTIAO', 'WEIBO', 'WECHAT', 'DOUYIN', 'XIAOHONGSHU', 'ZHIHU'
) NOT NULL DEFAULT 'WEIBO';
