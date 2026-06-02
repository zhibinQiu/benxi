#!/usr/bin/env bash
# 下载 RAGFlow LIGHTEN 构建所需依赖（跳过大型 embedding 模型）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KF="$ROOT/platform/third_party/KnowFlow"

[[ -d "$KF" ]] || { echo "请先运行: bash scripts/zhitan.sh knowflow setup"; exit 1; }

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
cd "$KF"

python3 <<'PY'
import os
import urllib.request
import nltk
from huggingface_hub import snapshot_download

os.environ.setdefault("HF_ENDPOINT", os.environ.get("HF_ENDPOINT", "https://hf-mirror.com"))

urls = [
    ("http://mirrors.tuna.tsinghua.edu.cn/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_amd64.deb", "libssl1.1_1.1.1f-1ubuntu2_amd64.deb"),
    ("http://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_arm64.deb", "libssl1.1_1.1.1f-1ubuntu2_arm64.deb"),
    ("https://repo.huaweicloud.com/repository/maven/org/apache/tika/tika-server-standard/3.0.0/tika-server-standard-3.0.0.jar", "tika-server-standard-3.0.0.jar"),
    ("https://repo.huaweicloud.com/repository/maven/org/apache/tika/tika-server-standard/3.0.0/tika-server-standard-3.0.0.jar.md5", "tika-server-standard-3.0.0.jar.md5"),
    ("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken", "cl100k_base.tiktoken"),
]
zips = [
    ("https://registry.npmmirror.com/-/binary/chrome-for-testing/121.0.6167.85/linux64/chrome-linux64.zip", "chrome-linux64-121-0-6167-85"),
    ("https://registry.npmmirror.com/-/binary/chrome-for-testing/121.0.6167.85/linux64/chromedriver-linux64.zip", "chromedriver-linux64-121-0-6167-85"),
]
repos_light = [
    "InfiniFlow/text_concat_xgb_v1.0",
    "InfiniFlow/deepdoc",
    "InfiniFlow/huqie",
]

for url, name in urls:
    if not os.path.exists(name):
        print(f"下载 {name} ...")
        urllib.request.urlretrieve(url, name)

for url, name in zips:
    if not os.path.exists(name):
        print(f"下载 {name} ...")
        urllib.request.urlretrieve(url, name)

local_dir = os.path.abspath("nltk_data")
for data in ["wordnet", "punkt", "punkt_tab"]:
    print(f"下载 nltk {data} ...")
    nltk.download(data, download_dir=local_dir)

for repo_id in repos_light:
    local = os.path.abspath(os.path.join("huggingface.co", repo_id))
    if os.path.isdir(local) and os.listdir(local):
        print(f"跳过已存在 {repo_id}")
        continue
    print(f"下载 HF {repo_id} ...")
    os.makedirs(local, exist_ok=True)
    snapshot_download(repo_id=repo_id, local_dir=local, max_workers=4)

print("LIGHTEN 依赖下载完成")
PY
