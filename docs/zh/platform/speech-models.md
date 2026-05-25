# 录音转文字模型目录

FunASR / ModelScope 下载的 ASR、VAD、标点、说话人模型**默认保存在仓库内**：

```
pdf_trans/.run/speech-models/
```

该目录已在 `.gitignore` 的 `.run/` 规则下忽略，不会进入 Git。

## 配置

| 变量 | 说明 |
|------|------|
| `SPEECH_MODELS_DIR` | 覆盖默认路径（绝对或相对路径均可） |
| `MODELSCOPE_CACHE` | 与上项等价，FunASR 官方环境变量 |

- **宿主机启动**：`scripts/start_speech_local.sh` 自动使用 `$ROOT/.run/speech-models`
- **Docker 启动**：`docker-compose.speech.yml` 将宿主机 `../.run/speech-models` 挂载到容器 `/models`

## 迁移

若此前使用过 `.run/modelscope`，再次执行 `start_speech_local.sh` 会自动迁移到 `.run/speech-models`。
