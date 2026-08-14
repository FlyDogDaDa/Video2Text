---
created: 2026-08-06
author: Agent
type: agent
status: final
tags: [git, branch-management, history-rewrite, legacy-backup]
---

# Git 主線歷史重塑 + Legacy 分支建立

## What

將 `main` 分支歷史重構成線性干净的初始版本，把舊主線完整歷史移至 `legacy/` 分支，建立 `refactor/rewrite` 作為開發主分支，並制定未來分支開發流程。

## Why

之前的 `main` 分支累積了許多初期開發的 commits（含 merge commit、文件更新、實驗性變更），歷史雜亂。為了建立清晰的專案起點與未來開發流程，需要：

1. `main` 只保留專案初始化與新開發的線性歷史
2. 舊歷史完整保留於 `legacy/*` 分支，供考古回溯
3. 建立 `refactor/rewrite` 作為長周期開發分支
4. 制定新的分支策略：新功能 → 大分支 → 子分支（保留完整足跡）→ 父分支 → main

## How

### 最終分支結構

```
main                      # 穩定主線（2 commits 線性歷史）
│
└── refactor/rewrite      # 開發主分支（89 commits 線性開發史）
     │
└── legacy/              # 歷史快照（不 merge 回 main）
    ├── legacy/main-v1    # 完整舊 main 歷史（30 commits）
    ├── legacy/voice-tag  # VoiceTag STT 軌跡（84 commits）
    ├── legacy/quark-audio# QuarkAudio TSE 軌跡（78 commits）
    └── legacy/sam-audio  # SAM-Audio 微服務軌跡（71 commits）
```

### 執行步驟

#### 階段一：建立安全備份

```bash
git branch temp-backup main          # 56b69a5（主線備份）
git branch temp-refactor refactor/rewrite  # 31d7d51（開發分支備份）
```

#### 階段二：建立 Legacy 分支快照

```bash
git branch legacy/main-v1 9b766cb      # 舊主線完整歷史
git branch legacy/voice-tag 5b44c22    # VoiceTag STT 軌跡
git branch legacy/quark-audio 0f93e2c  # QuarkAudio TSE 軌跡
git branch legacy/sam-audio ae15a29    # SAM-Audio 微服務軌跡
```

#### 階段三：重塑 Main 歷史

核心操作：使用 Python 腳本 + `git commit-tree` 重建 `refactor/rewrite` 的 commit chain。

**原因**：`refactor/rewrite` 與 `main` 沒有共同祖先（tree 完全不同），`git rebase --onto` 會產生衝突，`cherry-pick --root` 則因 root commit 的 tree 與 main 相同而被視為空提交。

**解法**：用 Python 讀取舊 commit chain（`31d7d51 → ... → eb90b3f`），逐個取出 tree SHA 與 commit message，用 `git commit-tree` 建立全新 commit，第一個 commit 的 parent 設為 `main` tip（`9591a45`），後續 commit 的 parent 為前一個重建的 commit，最後用 `git update-ref` 讓 `refactor/rewrite` 指向新 tip。

#### 階段四：推送與遠端同步

```bash
git push origin main --force-with-lease            # 9591a45 覆蓋舊 d10c4e5
git push origin refactor/rewrite --force-with-lease # 88d56a2 取代 31d7d51
```

#### 階段五：清理

```bash
git branch -D refactor/rewrite-new   # 删除残留分支
rm reparent.py                        # 删除腳本
```

### 驗證結果

| 檢查項目 | 結果 |
|---------|------|
| `main` 只有 2 commits | ✅ `029f9af` → `9591a45` |
| `refactor/rewrite` 是 main 後代 | ✅ `merge-base --is-ancestor` 通過 |
| `refactor/rewrite` 無 merge commit | ✅ 線性 89 commits |
| `refactor/rewrite` root 的 parent 是 `9591a45` | ✅ 正確 |
| 無舊 main commits 漏入 main | ✅ 無 `9b766cb` |
| 無舊 main commits 漏入 refactor/rewrite | ✅ 無 `9b766cb` |
| 遠端 `origin/main` 同步 | ✅ `9591a45` |
| 遠端 `origin/refactor/rewrite` 同步 | ✅ `88d56a2` |
| `legacy/main-v1` 完整 | ✅ `9b766cb` 在首行（30 commits） |

## Follow-up

- 建立 `DEVELOPMENT.md` 記錄新的分支開發流程（目前僅口頭規範）
- `refactor/rewrite` 作為開發主分支，新功能應從 `main` 拉分支實作
- 未來 `legacy/*` 不 merge 回 main（只用於考古回溯）

## References

- [refactor/rewrite](refactor/rewrite) — 開發主分支
- [legacy/main-v1](legacy/main-v1) — 完整舊主線歷史
- [legacy/voice-tag](legacy/voice-tag) — VoiceTag STT 軌跡
- [legacy/quark-audio](legacy/quark-audio) — QuarkAudio TSE 軌跡
- [legacy/sam-audio](legacy/sam-audio) — SAM-Audio 微服務軌跡