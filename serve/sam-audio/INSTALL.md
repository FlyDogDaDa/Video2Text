# sam_audio 環境安裝備忘錄

## 問題背景

`sam-audio` 的相依套件 `perception-models` 硬編指定 `decord==0.6.0`，
而 `decord` 官方不提供 Python 3.12 + Linux 的 wheel，導致 `uv pip install` 失敗。

此外：
- `transformers>=5` 不支援 `huggingface_hub<0.34`
- `pkg_resources` 在 Python 3.12 不再內建，需要 `setuptools<69`
- Hugging Face 模型是 gated repo，需要 token 授權

## 解決方案

1. 使用 [decord2](https://pypi.org/project/decord2/) 替換 `decord`
2. 使用 `--no-deps` 跳過 `perception-models` 的依賴解析
3. 手動控制 `transformers` 和 `huggingface_hub` 版本
4. 手動補上 `setuptools<69` 提供 `pkg_resources`

> **為什麼不用 `uv` dependency override？**
> `perception-models` 的 `requirements.txt` 硬編 `decord==0.6.0`，
> `uv` 無法穿透第二層相依套用 override，必須手動控制。

## 完整 SOP

### 1. 建立虛擬環境

```bash
uv venv serve/sam-audio/.venv
```

### 2. 先安裝 decord2

```bash
uv pip install decord2 --python serve/sam-audio/.venv/bin/python
```

### 3. 手動安裝 perception-models（跳過依賴解析）

```bash
uv pip install --no-deps \
  "perception-models @ git+https://github.com/facebookresearch/perception_models.git@unpin-deps" \
  --python serve/sam-audio/.venv/bin/python
```

### 4. 手動安裝 sam-audio（跳過依賴解析）

```bash
uv pip install --no-deps \
  "sam_audio @ git+https://github.com/facebookresearch/sam-audio.git" \
  --python serve/sam-audio/.venv/bin/python
```

### 5. 補上 setuptools（Python 3.12 需要 pkg_resources）

```bash
uv pip install "setuptools<69" --python serve/sam-audio/.venv/bin/python
```

### 6. 安裝剩餘相依套件（注意版本限制）

```bash
uv pip install \
  "dacvae@git+https://github.com/facebookresearch/dacvae.git" \
  "imagebind@git+https://github.com/facebookresearch/ImageBind.git" \
  laion-clap \
  audiobox_aesthetics \
  einops \
  pydub \
  torch \
  torchaudio \
  torchcodec \
  torchdiffeq \
  torchvision \
  "transformers>=4.54.0,<5.0" \
  "huggingface_hub>=0.34,<1.0" \
  --python serve/sam-audio/.venv/bin/python
```

### 7. 補裝 xformers 和 FastAPI 伺服器相依

```bash
uv pip install xformers fastapi "uvicorn[standard]" pydantic numpy \
  --python serve/sam-audio/.venv/bin/python
```

### 8. 驗證安裝

```bash
serve/sam-audio/.venv/bin/python -c "import sam_audio; print('OK')"
```

## 設定 Hugging Face Token

`sam-audio` 的模型存放在 Hugging Face gated repo，需要 token 授權：

```bash
# 方法一：互動式登入
serve/sam-audio/.venv/bin/python -c "from huggingface_hub import login; login()"

# 方法二：直接指定 token
export HF_TOKEN=your_token_here
```

或在程式碼中：

```python
from huggingface_hub import login
login(token="hf_your_token_here")
```

## 啟動伺服器

```bash
# 方法一：使用 start_server.py
nohup serve/sam-audio/.venv/bin/python serve/sam-audio/start_server.py > /tmp/sam-audio-server.log 2>&1 &

# 方法二：直接執行
serve/sam-audio/.venv/bin/python serve/sam-audio/start_server.py

# 檢查伺服器狀態
tail -f /tmp/sam-audio-server.log

# 測試 API（假設模型已載入完成）
curl -X POST http://localhost:8000/your-endpoint -H "Content-Type: application/json" -d '{"key": "value"}'
```

伺服器預設監聽 `0.0.0.0:8000`。

## 版本清單

| 套件 | 版本 | 備註 |
|------|------|------|
| Python | 3.12 | 必要 |
| decord2 | 3.4.0 | 替代 decord |
| perception-models | 1.0.0 (git) | 從 unpin-deps branch |
| sam_audio | 0.1.0 (git) | 從 main branch |
| transformers | 4.57.x | **必須 <5.0** |
| huggingface_hub | 0.36.x | **必須 >=0.34** |
| setuptools | 68.2.x | **必須 <69** (提供 pkg_resources) |
| xformers | 0.0.35 | runtime 相依 |
| fastapi | 0.139.x | 伺服器框架 |
| uvicorn | 0.51.x | ASGI 伺服器 |
| pydantic | 2.x | 資料驗證 |

## 常見問題

### Q: 安裝 `decord` 失敗？
A: 改用 `decord2`，它提供 `import decord` 且支援 Python 3.12。

### Q: `transformers` 匯入失敗 `cannot import name 'is_offline_mode'`？
A: `transformers>=5` 需要新版 `huggingface_hub`，但 `sam-audio` 的 `BaseModel` 不支援。降版：
```bash
uv pip install "transformers>=4.54.0,<5.0" "huggingface_hub>=0.34,<1.0"
```

### Q: `ModuleNotFoundError: No module named 'pkg_resources'`？
A: Python 3.12 移除內建 `pkg_resources`，安裝舊版 setuptools：
```bash
uv pip install "setuptools<69"
```

### Q: `401 Unauthorized` 下載模型失敗？
A: 模型是 gated repo，需要設定 Hugging Face token：
```bash
export HF_TOKEN=your_token_here
```
或在程式碼中 `login(token="...")`。

### Q: `AssertionError: Install ImageBind`？
A: `ImageBind` 相依未正確安裝，手動安裝：
```bash
uv pip install "imagebind@git+https://github.com/facebookresearch/ImageBind.git"
```

### Q: 伺服器啟動後卡住？
A: 模型權重需要時間載入，查看 log：
```bash
tail -f /tmp/sam-audio-server.log
```

## 實戰修復紀錄

### 問題 1：`Processor.from_pretrained()` 不支援新版 huggingface_hub 參數

**錯誤訊息：**
```
TypeError: Processor.from_pretrained() got an unexpected keyword argument 'proxies'
```

**原因：** `SAMAudioProcessor.from_pretrained()` 方法沒有 `**kwargs`，新版 `huggingface_hub` 會自動注入 `proxies` 和 `resume_download` 參數。

**修復方式：** 修改 `sam_audio_core.py` 中的呼叫：

```python
# ❌ 錯誤寫法
processor = SAMAudioProcessor.from_pretrained(
    "facebook/sam-audio-small",
    proxies={},
    resume_download=True,
)

# ✅ 正確寫法
processor = SAMAudioProcessor.from_pretrained(
    "facebook/sam-audio-small",
)
```

`SAMAudio` 可以正常運作，因為它繼承 `ModelHubMixin` 自動處理這些參數，但 `SAMAudioProcessor` 是純手動實作。

### 問題 2：版本相依衝突鏈

```huggingface_hub````→```transformers``` 版本相依是一個鏈式問題：

| transformers 版本 | 需要的 huggingface_hub 版本 | 問題 |
|-------------------|---------------------------|------|
| 4.54.0 ~ 4.57.x | >=0.34, <1.0 | ✅ 正確 |
| 5.0+ | >=0.34, <1.0 | ❌ sam-audio 的 ModelHubMixin 不支援新版 API |

**解法：** 同時指定兩者版本範圍：
```bash
uv pip install "transformers>=4.54.0,<5.0" "huggingface_hub>=0.34,<1.0"
```

### 問題 3：uv 無法穿透第二層相依解析

**情境：** 使用 `uv pip install --upgrade` 時，uv 會自動解析 `perception-models` 的 `requirements.txt`，發現 `decord==0.6.0` 後嘗試從 PyPI 下載，導致失敗。

**解法：** 使用 `--no-deps` 完全跳過依賴解析：
```bash
uv pip install --no-deps "perception-models @ git+..."
```

## 除錯技巧

### 1. 檢查套件版本
```bash
serve/sam-audio/.venv/bin/python -m pip list | grep -E "decord|transformers|huggingface_hub|setuptools"
```

### 2. 檢查模型檔案是否存在
```bash
ls -lh /home/freespace/.cache/huggingface/hub/models--facebook--sam-audio-small/snapshots/
```

### 3. 測試模型匯入
```bash
serve/sam-audio/.venv/bin/python -c "
from sam_audio import SAMAudio, SAMAudioProcessor
print('SAMAudio OK')
print('SAMAudioProcessor OK')
"
```

### 4. 測試 HuggingFace Token
```bash
serve/sam-audio/.venv/bin/python -c "
from huggingface_hub import HfApi
api = HfApi()
model_info = api.model_info('facebook/sam-audio-small')
print(f'Model: {model_info.id}')
print(f'Size: {model_info.siblings[0].size if model_info.siblings else "N/A"}')
"
```

## 快速重裝指令

```bash
# 一次搞定所有安裝
uv venv serve/sam-audio/.venv && \
uv pip install decord2 "setuptools<69" \
  "transformers>=4.54.0,<5.0" "huggingface_hub>=0.34,<1.0" \
  xformers fastapi "uvicorn[standard]" pydantic numpy \
  --python serve/sam-audio/.venv/bin/python && \
uv pip install --no-deps \
  "perception-models @ git+https://github.com/facebookresearch/perception_models.git@unpin-deps" \
  "sam_audio @ git+https://github.com/facebookresearch/sam-audio.git" \
  --python serve/sam-audio/.venv/bin/python && \
uv pip install \
  "dacvae@git+https://github.com/facebookresearch/dacvae.git" \
  "imagebind@git+https://github.com/facebookresearch/ImageBind.git" \
  laion-clap audiobox_aesthetics einops pydub \
  torch torchaudio torchcodec torchdiffeq torchvision \
  --python serve/sam-audio/.venv/bin/python
```