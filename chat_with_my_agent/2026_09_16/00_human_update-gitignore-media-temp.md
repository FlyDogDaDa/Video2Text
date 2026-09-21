---
created: 2026-09-16
author: human
type: human
tags: [gitignore, housekeeping, video2text]
---

# `.gitignore` 補錄影輸出與暫存目錄

## What

- `.gitignore` 新增：`tmp/`、`output.mkv`、`output.webm`、`output.mp4`
- `git check-ignore -v` 驗證三項全數生效（`output/` 目錄規則原本已有，不受影響）

## Why

- 專案根目錄殘留螢幕錄影輸出（`output.mkv`、`output.webm`，各 ~418MB）與 `tmp/` 暫存目錄，不該進 git

## How

- 編輯 `.gitignore`，插入於「Test audio directory」區塊之後

## Follow-up

- 無

## Uncertainty

- 無

## References

- 無（無獨立討論細節）
