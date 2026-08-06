#!/usr/bin/env python3
"""檢查 checkpoint key 映射問題"""

import re
import sys
from pathlib import Path

QAU = Path("serve/quark-audio")

ckpt = torch.load(
    str(QAU / "checkpoints/epoch=20-step=109367.ckpt"),
    map_location="cpu",
    weights_only=False,
)
state_dict = ckpt["state_dict"]

keys_with_dnn = [k for k in state_dict if "dnn" in k]
print(f"Keys with 'dnn': {len(keys_with_dnn)}")

# 顯示所有 unique prefix patterns
print("\n=== 原始 checkpoint keys 前 30 ===")
for k in sorted(keys_with_dnn)[:30]:
    print(f"  {k}")

print(f"\n... ({len(keys_with_dnn)} 總共) ...\n")

# 檢查是否有 conv_module 或 conv_ 模式
conv_keys = [k for k in keys_with_dnn if ".conv_" in k]
print(f"Keys with '.conv_': {len(conv_keys)}")
for k in sorted(conv_keys):
    # 替換 layer index 為 {N} 來去重複
    simplified = re.sub(r"\.layers\.\d+", ".layers.{N}", k)
    print(f"  {simplified}")

# 模擬清理 + 映射
print("\n=== 映射測試 ===")
pattern = r"(cond_encoder\.layers\.\d+)\.conv_"
mapped_keys = []
for k in keys_with_dnn:
    new_k = k.replace("dnn.", "").replace("module.dnn.", "").replace("module.", "")
    new_k = re.sub(pattern, r"\1.conv_module.", new_k)
    mapped_keys.append(new_k)

# 檢查 conv_ 是否都變了
original_conv = sorted(
    set(re.sub(r"\.layers\.\d+", ".layers.{N}", k) for k in conv_keys)
)
mapped_conv = sorted(
    set(
        re.sub(r"\.layers\.\d+", ".layers.{N}", k)
        for k in mapped_keys
        if ".conv_" in k or ".conv_module." in k
    )
)

print(f"\nOriginal conv keys ({len(original_conv)} unique patterns):")
for k in original_conv:
    print(f"  {k}")

print(f"\nMapped conv keys ({len(mapped_conv)} unique patterns):")
for k in mapped_conv:
    print(f"  {k}")

print(f"\n映射前: {len(original_conv)} 個 unique conv patterns")
print(f"映射後: {len(mapped_conv)} 個 unique conv patterns")
