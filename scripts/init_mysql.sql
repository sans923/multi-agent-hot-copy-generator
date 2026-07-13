-- MySQL 初始化（本地安装 MySQL 时手动执行一次）
-- 用法：mysql -u root -p < scripts/init_mysql.sql

CREATE DATABASE IF NOT EXISTS copy_generator
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'copygen'@'%' IDENTIFIED BY 'copygen123';
CREATE USER IF NOT EXISTS 'copygen'@'localhost' IDENTIFIED BY 'copygen123';

GRANT ALL PRIVILEGES ON copy_generator.* TO 'copygen'@'%';
GRANT ALL PRIVILEGES ON copy_generator.* TO 'copygen'@'localhost';

FLUSH PRIVILEGES;
