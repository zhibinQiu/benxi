# frp（无 token）

| 端口 | 用途 |
|------|------|
| 40007 | frps 控制（frpc serverPort） |
| 40008 | frpc remotePort（本机 Vite 对外） |

他人访问本机 dev：**http://172.19.134.45:40008/ai/**

HTTP 依赖已收拢到 gateway **:40005**，见 [deploy/gateway/README.md](../gateway/README.md)。
