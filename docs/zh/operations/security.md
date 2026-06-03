# 安全

## 攻击面

| 暴露 | 生产建议 |
|------|----------|
| `FRONTEND_PORT` (40005) | 可经防火墙 / 反向代理 + TLS |
| API 8000 | **不映射**；仅 Docker 内网 |
| postgres / redis / minio | **不映射** |
| KnowFlow 9380 | **不映射**；经 embed-proxy |
| MinIO console 9001 | 不映射 |

## 认证与密钥

- `JWT_SECRET`：强随机，生产必改
- `BOOTSTRAP_ADMIN_PASSWORD`：首次登录后改密
- `DEEPSEEK_API_KEY` 等：仅 `.env`，勿提交 Git
- MinIO / MySQL / ES 密码：与默认值不同

## 应用层

- CORS：`config.cors_origins` 限制来源
- 文件上传：大小限制、类型校验（文档 API）
- 数据分析：代码沙箱超时 `data_analysis_exec_timeout_seconds`
- embed-proxy：KnowFlow 路由 **无** 平台 JWT（依赖 KnowFlow auth query）；静态资源公开只读

## 容器

- 非 root 用户：按基础镜像默认
- 卷权限：`DATA_ROOT` 仅部署用户可读写
- 镜像：定期 rebuild 拉取安全补丁

## 依赖

- `pip install -e .` / `npm audit` 定期扫描
- PostgreSQL 16、Redis 7、ES 8 跟踪 CVE

## 生产 Checklist

- [ ] 关闭 `debug`
- [ ] HTTPS 终止在 Nginx / 网关
- [ ] 强密码与 JWT_SECRET
- [ ] 备份加密存储
- [ ] 审计日志保留策略
- [ ] 限制 SSH / 40005 来源 IP

## 漏洞响应

1. 隔离：down 受影响服务
2. 评估：日志、audit_logs
3. 补丁：升级镜像 / 依赖
4. 轮换密钥
