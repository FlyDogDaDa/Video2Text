---
created: 2026-07-22
author: FlyDogDaDa
type: agent
status: final
tags: [sam-audio, installation, dependency-resolution, server-setup]
---

# Sam-Audio 伺服器安裝與相容性修復

## What

將 `sam_audio` 套件成功部署到獨立虛擬環境並啟動 FastAPI 伺服器，期間解決多層相依相容性問題。

## Why

`sam-audio` 需要獨立於主專案的虛擬環境運行，因為其相依套件 (`perception-models`) 硬編 `decord==0.6.0`，而 PyPI 不提供 Python 3.12 + Linux 的 wheel。此外，多個套件之間存在版本相依衝突鏈。

## How

### 相容性問題修復

**問題 1：`decord` 無 Python 3.12 wheel**

使用 [decord2](https://pypi.org/project/decord2/)（社群維護的 `decord` 替代品）：
```bash
uv pip install decord2
```

**問題 2：uv 無法穿透第二層相依解析**

`perception-models` 的 `requirements.txt` 硬編 `decord==0.6.0`，`uv` dependency override 無效。使用 `--no-deps` 跳過依賴解析：
```bash
uv pip install --no-deps "perception-models @ git+..."
uv pip install --no-deps "sam_audio @ git+..."
```

**問題 3：`transformers` 與 `huggingface_hub` 版本衝突鏈**

```
transformers>=4.54 → huggingface_hub>=0.34 → 但 transformers>=5 不支援 sam-audio 的 ModelHubMixin
```
最終確定版本範圍：`transformers>=4.54.0,<5.0`、`huggingface_hub>=0.34,<1.0`。

**問題 4：Python 3.12 移除 `pkg_resources`**

```bash
uv pip install "setuptools<69"
```

**問題 5：`Processor.from_pretrained()` 不支援新版 huggingface_hub 參數**

`sam_audio_core.py` 第 38-41 行：
```python
# 移除 proxies 和 resume_download 參數（Processor 未實作 **kwargs）
processor = SAMAudioProcessor.from_pretrained("facebook/sam-audio-small")
```

### 伺服器啟動

模型權重下載：
- `checkpoint.pt`：5.10 GB（sam-audio-small）
- `imagebind_huge.pth`：4.47 GB（ImageBind）
- 其他小檔案：~9 個

最終狀態：`Uvicorn running on http://0.0.0.0:8000`
- `POST /separate`：音訊分離端點
- `GET /health`：健康檢查（確認 GPU 可用）

### Git 提交

| 提交 | Type | 說明 |
|------|------|------|
| `616bf45` | `fix(sam-audio)` | 移除 `Processor.from_pretrained()` 不支援的參數 |
| `8141d73` | `docs(sam-audio)` | 新增 `INSTALL.md` 安裝 SOP 與 `uv.lock` |

### 關鍵檔案

| 檔案 | 動作 | 說明 |
|------|------|------|
| `sam_audio_core.py` | 修改 | 移除不支援參數、新增 lifespan 預載 |
| `api/main.py` | 修改 | lifespan 上下文管理器 |
| `server.py` | 修改 | 伺服器配置 |
| `pyproject.toml` | 刪除 | 改由父專案管理 |
| `INSTALL.md` | 新增 | 完整安裝指南（~180 行） |
| `uv.lock` | 新增 | 依賴鎖定檔 |

## Follow-up

- [ ] 測試 `POST /separate` API 端點與音訊分離功能
- [ ] 確認 `sam-audio` 模組整合到主專案 pipeline

## References

- [INSTALL.md](../serve/sam-audio/INSTALL.md)
- [sam_audio_core.py](../serve/sam-audio/sam_audio_core.py)
- [api/main.py](../serve/sam-audio/api/main.py)
- [decord2 PyPI](https://pypi.org/project/decord2/)
- [sam-audio GitHub](https://github.com/facebookresearch/sam-audio)
- [perception_models GitHub](https://github.com/facebookresearch/perception_models)