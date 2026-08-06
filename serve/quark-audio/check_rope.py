import torch
from transformers import AutoModel

model = AutoModel.from_pretrained(
    "/home/freespace/文件/Video2Text/serve/quark-audio/checkpoints/epoch=20-step=109367.ckpt",
    device_map="cpu",
    torch_dtype=torch.float16,
    trust_remote_code=True,
)
# Find rotary embedding
for name, module in model.named_modules():
    if "rotary" in name.lower() or "Rope" in str(type(module).__name__):
        print(f"=== {name}: {type(module).__name__} ===")
        for attr in dir(module):
            if not attr.startswith("_"):
                val = getattr(module, attr)
                if not callable(val):
                    print(f"  {attr}: {val}")
        if hasattr(module, "state_dict"):
            sd = module.state_dict()
            for k, v in sd.items():
                print(f"  state_dict[{k}]: {v.shape}")
