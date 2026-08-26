---
created: 2026-08-07
author: agent
type: agent
status: final
tags: [setuptools, pkg_resources, resemblyzer, voicetag, dependency]
---

# setuptools 版本卡關 — pkg_resources 被移除

## What

將 `setuptools` 從最新版（83.0.0）降級至 81.0.0，解決 `pkg_resources` 模組缺失問題。

## Why

`webuis` 使用 `voicetag[openai]` 做說話人 enrollment 時，遇到：

```
Exception: Failed to enroll speaker '婕': No module named 'pkg_resources'
```

根因：
1. `resemblyzer==0.1.4` 依賴 `webrtcvad`
2. `webrtcvad` 使用 `pkg_resources` 模組（已deprecated）
3. `setuptools 82.0.0`（2026年2月）正式移除 `pkg_resources`
4. `setuptools 83.0.0` 在 virtual environment 中被 uv 自動安裝

同時 `torch==2.13.0+cu130` 要求 `setuptools>=77.0.3`，所以版本不能低於 77。

## How

### 1. 確認 PyPI 無獨立 `pkg_resources` 套件

查詢 Python Packaging 官方討論（Feb 2026）：
- `pkg_resources` 名字被保留（namesquatted by @dstufft 在 2013），準備開放給 setuptools 團隊做成獨立套件，但**尚未釋出**
- 官方建議：暫時 `setuptools<82`

### 2. 安裝 `resemblyzer`（包含 `webrtcvad`）

```bash
uv add resemblyzer --project webuis
```

安裝成功：
```
+ resemblyzer==0.1.4
+ webrtcvad==2.0.10
```

### 3. 降級 `setuptools` 至 81.0.0

```bash
uv add "setuptools>=77,<82" --project webuis
```

版本範圍：
- **>=77.0.3**：符合 torch 2.13 需求
- **<82.0.0**：保留 `pkg_resources`（82.0.0 正式移除）

最終：`setuptools==81.0.0`

### 4. 完整依賴鏈

```
webuis
├── voicetag[openai]
│   └── resemblyzer  ← 需要 pkg_resources
│       └── webrtcvad  ← 使用 pkg_resources
├── pyannote-audio>=4.0
└── torch>=2.13  ← 需要 setuptools>=77.0.3
```

## Follow-up

- 一旦 PyPI 釋出獨立 `pkg_resources` 套件，可移除版本限制
- 長期建議：要求 `webrtcvad` / `resemblyzer` 遷移至 `importlib.metadata`

## References

- [71_2026_08_07_agent_fix-pyannote-environment](./71_2026_08_07_agent_fix-pyannote-environment.md)
- [61_2026_07_31_agent_voicetag-pkg_resources-fix-and-testing](./61_2026_07_31_agent_voicetag-pkg_resources-fix-and-testing.md)
- [pkg_resources removal discussion](https://discuss.python.org/t/pkg-resources-removal-how-to-go-from-there/106079)
- [GitHub issue: Restore pkg_resources](https://github.com/pypa/setuptools/issues/5174)