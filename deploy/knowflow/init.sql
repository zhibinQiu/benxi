CREATE DATABASE IF NOT EXISTS rag_flow;
USE rag_flow;

-- KnowFlow / RAGFlow 容器经 Docker 网络访问 MySQL（非仅 localhost）
CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY 'infini_rag_flow';
ALTER USER 'root'@'%' IDENTIFIED BY 'infini_rag_flow';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
