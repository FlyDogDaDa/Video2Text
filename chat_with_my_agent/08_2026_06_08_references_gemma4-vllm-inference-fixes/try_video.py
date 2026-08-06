from pathlib import Path

from dotenv import load_dotenv
from transformers import AutoProcessor
from vllm import LLM, SamplingParams
from vllm.config import AttentionConfig
from vllm.multimodal.utils import fetch_video
from vllm.v1.attention.backends.registry import AttentionBackendEnum

load_dotenv()

model_path = "google/gemma-4-12B-it-qat-w4a16-ct"
tp_size = 2
quantization = "compressed-tensors"
processor = AutoProcessor.from_pretrained(model_path)
llm = LLM(
    model=model_path,
    quantization=quantization,
    tensor_parallel_size=tp_size,  # Use 2 GPUs
    max_model_len=262144,  # Gemma-4-12B official context: 256K
    trust_remote_code=True,
    enforce_eager=True,
    limit_mm_per_prompt={"image": 4, "video": 1},
    attention_config=AttentionConfig(backend=AttentionBackendEnum.TRITON_ATTN),
)

video_url = "file:///home/b11223209/workspace/ProgramDevelopment/Video2Text/2026_05_11-19_18_26_louder4x.mp4"
video_data = fetch_video(video_url)

messages = [
    {
        "role": "user",
        "content": [
            {"type": "video"},
            {"type": "text", "text": "Summarize what happens in this video."},
        ],
    }
]
prompt = processor.apply_chat_template(
    messages, tokenize=False, add_generation_prompt=True
)

outputs = llm.generate(
    {"prompt": prompt, "multi_modal_data": {"video": [video_data]}},
    sampling_params=SamplingParams(temperature=0.0, max_tokens=1024),
)

print(outputs[0].outputs[0].text)
