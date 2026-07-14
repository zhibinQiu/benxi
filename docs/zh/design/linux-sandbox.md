# Linux 沙箱执行环境 — 设计提案

## 动机

当前 Agent 系统中，智能体通过 Python 工具调用执行操作。很多场景下原生 Linux 命令比 Python 代码快得多（grep/awk/sed/find/jq/cut 等文本处理、ffmpeg/imagemagick 等多媒体处理），且更符合运维人员的使用习惯。

## 架构

```
Agent LLM
  → invoke_skill(linux-executor, call, {operation: "run", command: "..."})
  → Skill Runtime
    → SandboxManager
      → Docker 容器 (Linux)
        → bash -c "command"
        → stdout/stderr/exit_code
      → 结果过滤 + 安全检查
    → 返回给 LLM
```

## 沙箱容器配置

### Docker Compose

```yaml
services:
  sandbox:
    image: alpine:latest  # 或自定义 sandbox image
    container_name: agent-sandbox
    init: true
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100M
      - /home:noexec,nosuid,size=10M
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    network_mode: "none"  # 默认无网络，按需开启
    mem_limit: 256m
    pids_limit: 50
```

### 安全策略

| 维度 | 策略 |
|------|------|
| 网络 | 默认隔离（`network_mode: none`），仅特定命令允许网络 |
| 文件系统 | `read_only: true`，仅 `/tmp` `/home` 可写 |
| 特权 | `cap_drop: ALL`，禁止提权 |
| 超时 | 命令执行超时 30s |
| 输出 | stdout/stderr 截断 100KB |
| 命令黑名单 | `rm -rf /`、`dd`、`mkfs`、`fdisk`、`mount`、`chmod 777` 等禁止 |
| 白名单模式 | 可选 strict 模式：只允许特定命令列表 |

## API

### 工具定义

```json
{
  "name": "sandbox_run",
  "description": "在隔离 Linux 沙箱中执行系统命令。返回 stdout、stderr、exit_code。适合文件处理、数据过滤、格式转换等场景。",
  "parameters": {
    "command": {"type": "string", "description": "要执行的命令（bash 语法）"},
    "workdir": {"type": "string", "description": "工作目录（默认 /tmp）"},
    "timeout": {"type": "integer", "description": "超时秒数（默认 30，最大 120）"},
    "network": {"type": "boolean", "description": "是否允许网络访问（默认 false）"}
  },
  "required": ["command"]
}
```

### 命令执行包装

```python
import asyncio, subprocess, json

async def sandbox_run(command: str, *, timeout=30, workdir="/tmp", network=False) -> str:
    safe_command = _sanitize_command(command)
    docker_args = [
        "docker", "exec", "-i",
        "--workdir", workdir,
        "agent-sandbox",
        "timeout", str(timeout),
        "bash", "-c", safe_command,
    ]
    proc = await asyncio.create_subprocess_exec(
        *docker_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout + 5
        )
    except asyncio.TimeoutError:
        proc.kill()
        return json.dumps({"ok": False, "error": "timeout"})
    return json.dumps({
        "ok": True,
        "stdout": (stdout or b"").decode()[:100_000],
        "stderr": (stderr or b"").decode()[:10_000],
        "exit_code": proc.returncode,
    })
```

## 集成方式

作为**技能包（Skill）** 集成，而非内建工具：

1. 创建 `sandbox-executor` 技能包
2. 上传到平台，skill-dev 负责安装维护
3. 暴露 `invoke_skill(sandbox-executor, call, {operation, command, workdir, timeout})`
4. 可选：内置为平台工具（`sandbox_run`），供 orchestrator 直接调用

## 使用场景

| 场景 | Python 方案 | Linux 方案 | 速度对比 |
|------|-----------|-----------|---------|
| 大文本搜索 | 逐行读取 + re.search | `grep -rn "pattern" /data/` | 10-100x |
| JSON 提取 | json.load + 遍历 | `jq '.key' file.json` | 5-10x |
| 文件统计 | os.walk + cnt | `find /data -type f \| wc -l` | 20-50x |
| 日志分析 | 逐行解析 | `awk '{print $1}' \| sort \| uniq -c` | 10-30x |
| 格式转换 | Python lib | `ffmpeg` (多媒体), `pandoc` (文档) | 3-10x |
| 数据管道 | 多步骤 Python | `cmd1 \| cmd2 \| cmd3` | 5-20x |

## 安全边界

- 沙箱容器使用 `seccomp` 限制系统调用
- 禁止 `mount`、`modprobe`、`ptrace` 等安全敏感 syscall
- 超时后强制 `docker kill`
- 输出长度限制（防止 OOM）
- 日志审计：记录所有执行的命令

## 后续扩展

- 支持文件挂载（通过卷挂载只读访问主机文件）
- 预装常用工具包（jq, yq, ffmpeg, pandoc, curl, wget, git）
- 多会话隔离（每个对话一个沙箱实例）
