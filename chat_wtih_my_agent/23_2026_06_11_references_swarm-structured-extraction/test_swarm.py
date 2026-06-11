if __name__ == "__main__":
    import json
    import os

    from PIL import Image
    from transformers import AutoProcessor
    from vllm import SamplingParams

    from main import load_model, swarm_extract

    video_path = "short_test.mp4"
    model_path = os.getenv("VLLM_MODEL", "google/gemma-4-12B-it-qat-w4a16-ct")

    print("=" * 60)
    print("Step 1: Load model")
    print("=" * 60)
    llm = load_model(model_path)

    print("\n" + "=" * 60)
    print("Step 2: Extract first slice only")
    print("=" * 60)
    slices = swarm_extract(video_path)
    slice_0 = slices[0]
    frames = slice_0["frames"]
    audio_clips = slice_0["audio_clips"]

    print(f"\nSlice 0: {frames.shape[0]} frames, {len(audio_clips)} audio clips")

    print("\n" + "=" * 60)
    print("Step 3: Build prompt with processor")
    print("=" * 60)

    template = {
        "description": {"visual": "", "audio": ""},
        "transcription": {"audio": [{"text": "", "speaker": ""}], "visual": ""},
        "time_range": {"start": 0.0, "end": 30.0},
    }
    prompt_text = (
        f"Analyze this 30-second video slice. "
        f"Return ONLY valid JSON with this structure:\n\n"
        f"{json.dumps(template, indent=2)}\n\n"
        f"Fill in the values based on the video content."
    )

    processor = AutoProcessor.from_pretrained(model_path)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                *[{"type": "image"} for _ in range(frames.shape[0])],
                {"type": "audio"},  # Need audio placeholder for audio data
            ],
        }
    ]

    prompt = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    print(f"Prompt length: {len(prompt)} chars")

    multi_modal_data = {
        "image": [Image.fromarray(f) for f in frames],
        "audio": [audio_clips[0]] if audio_clips else [],
    }

    print("\n" + "=" * 60)
    print("Step 4: Run inference")
    print("=" * 60)

    sampling_params = SamplingParams(
        temperature=1.0,  # Google official default
        top_p=0.95,  # Google official default
        top_k=64,  # Google official default
        repetition_penalty=1.1,  # Mitigate Gemma 4 repetition pathologies
        max_tokens=2048,
        seed=42,
    )
    inputs = {
        "prompt": prompt,
        "multi_modal_data": multi_modal_data if multi_modal_data else None,
    }

    outputs = llm.generate(inputs, sampling_params=sampling_params)
    response = outputs[0].outputs[0].text.strip()

    print(f"\n🤖 Response:\n{response}")

    print("\n" + "=" * 60)
    print("Step 5: Parse JSON")
    print("=" * 60)

    try:
        json_text = response
        if "```json" in response:
            json_text = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_text = response.split("```")[1].split("```")[0]

        result = json.loads(json_text)
        print(f"\n✅ Parsed result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except json.JSONDecodeError as e:
        print(f"\n⚠ JSON parse error: {e}")
        print(f"Raw (first 200 chars): {response[:200]}")
