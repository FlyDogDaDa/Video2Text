#!/usr/bin/env python3
"""QuarkAudio-UniSE TSE 診斷腳本"""

import math
import sys
from pathlib import Path

import numpy as np
import torch

# 專案根目錄 (Video2Text/)
PROJECT_ROOT = Path(
    __file__
).parent.parent.parent  # serve/quark-audio/debug_tse.py -> Video2Text/
QAU_ROOT = PROJECT_ROOT / "serve" / "quark-audio"

# 加入官方 repo 路徑
sys.path.insert(0, str(QAU_ROOT / "unified-audio" / "QuarkAudio-UniSE"))

import librosa
import yaml


def main():
    checkpoint_dir = QAU_ROOT / "checkpoints"
    ckpt_path = checkpoint_dir / "epoch=20-step=109367.ckpt"
    mix_path = PROJECT_ROOT / "test-audio" / "2026_07_21_test_30s.mp3"
    enroll_path = PROJECT_ROOT / "test-audio" / "speech-reference.mp3"

    print("=" * 70)
    print("QuarkAudio-UniSE TSE 診斷")
    print("=" * 70)

    # ── Step 1: 檢查權重 ──
    print("\n[Step 1] 檢查權重檔案...")
    print(f"  ckpt_path exists: {ckpt_path.exists()}")
    print(f"  ckpt_path size: {ckpt_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(
        f"  checkpoint_dir/BiCodec/config.yaml: {(checkpoint_dir / 'BiCodec' / 'config.yaml').exists()}"
    )
    print(
        f"  checkpoint_dir/BiCodec/model.safetensors: {(checkpoint_dir / 'BiCodec' / 'model.safetensors').exists()}"
    )
    print(
        f"  checkpoint_dir/wav2vec2-large-xlsr-53: {(checkpoint_dir / 'wav2vec2-large-xlsr-53').exists()}"
    )

    # ── Step 2: 檢查 config.yaml 內容 ──
    print("\n[Step 2] 檢查 config.yaml 內容...")
    llm_config_path = (
        QAU_ROOT / "unified-audio" / "QuarkAudio-UniSE" / "conf" / "config.yaml"
    )
    with open(llm_config_path, "r") as f:
        llm_config = yaml.safe_load(f)
    print(f"  llm_config.task_map: {llm_config['llm_config']['task_map']}")
    print(f"  llm_config.num_tasks: {llm_config['llm_config']['num_tasks']}")
    print(f"  llm_config.feats_dim: {llm_config['llm_config']['feats_dim']}")
    print(f"  stft_config: {llm_config['stft_config']}")

    # ── Step 3: 載入 checkpoint 狀態字典 ──
    print("\n[Step 3] 檢查 checkpoint 狀態字典...")
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    state_dict = ckpt.get("state_dict", ckpt)

    # 檢查 key 前綴
    keys_with_dnn = [k for k in state_dict.keys() if "dnn" in k]
    keys_without_dnn = [k for k in state_dict.keys() if "dnn" not in k]

    print(f"  state_dict keys with 'dnn': {len(keys_with_dnn)}")
    print(f"  state_dict keys WITHOUT 'dnn': {len(keys_without_dnn)}")

    if keys_with_dnn:
        # 顯示前綴分佈
        prefixes = {}
        for k in keys_with_dnn:
            parts = k.split(".dnn.")
            if len(parts) > 1:
                prefix = parts[0]
            else:
                prefix = "NO_DNN_SEPARATOR"
            prefixes[prefix] = prefixes.get(prefix, 0) + 1
        print(f"  前綴分佈: {prefixes}")
        print(f"  前 5 個 keys: {keys_with_dnn[:5]}")

    # 模擬 api.py 的載入邏輯
    cleaned = {
        k.replace("dnn.", "").replace("module.dnn.", "").replace("module.", ""): v
        for k, v in state_dict.items()
        if "dnn" in k
    }
    print(f"  清理後的 keys: {len(cleaned)}")

    # ── Step 4: 載入音訊 ──
    print("\n[Step 4] 載入音訊...")
    mix, mix_sr = librosa.load(str(mix_path), sr=16000, mono=True)
    enroll, enroll_sr = librosa.load(str(enroll_path), sr=16000, mono=True)

    print(f"  mix: {len(mix) / 16000:.2f}s, {len(mix)} samples, sr={mix_sr}")
    print(
        f"  enroll: {len(enroll) / 16000:.2f}s, {len(enroll)} samples, sr={enroll_sr}"
    )

    # ── Step 5: 檢查分段邏輯 ──
    print("\n[Step 5] 檢查分段邏輯...")
    seg_len = 5 * 16000  # 5 seconds
    pad_len = math.ceil(len(mix) / seg_len) * seg_len - len(mix)
    print(f"  seg_len: {seg_len} samples ({seg_len / 16000:.1f}s)")
    print(f"  pad_len: {pad_len} samples ({pad_len / 16000:.1f}s)")
    print(f"  total segments: {math.ceil((len(mix) + pad_len) / seg_len)}")

    # ── Step 6: 載入模型 ──
    print("\n[Step 6] 載入模型...")
    from model.llm.llm_sft import LLM_SFT

    dnn = LLM_SFT(**llm_config["llm_config"])

    # 載入 checkpoint
    state_dict_cleaned = {
        k.replace("dnn.", "").replace("module.dnn.", "").replace("module.", ""): v
        for k, v in state_dict.items()
        if "dnn" in k
    }

    missing, unexpected = dnn.load_state_dict(state_dict_cleaned, strict=False)
    print(f"  Missing keys: {len(missing)}")
    if missing:
        for k in missing[:5]:
            print(f"    - {k}")
    print(f"  Unexpected keys: {len(unexpected)}")
    if unexpected:
        for k in unexpected[:5]:
            print(f"    - {k}")

    # 檢查參數是否為零
    total_params = sum(p.numel() for p in dnn.parameters())
    non_zero_params = sum(int((p != 0).sum().item()) for p in dnn.parameters())
    print(f"  Total params: {total_params:,}")
    print(
        f"  Non-zero params: {non_zero_params:,} ({non_zero_params / total_params * 100:.1f}%)"
    )

    # ── Step 7: 載入 BiCodec ──
    print("\n[Step 7] 載入 BiCodec tokenizer...")
    from model.bicodec.audio_tokenizer import BiCodecTokenizer

    tokenizer = BiCodecTokenizer(model_dir=str(checkpoint_dir))
    tokenizer = tokenizer.to("cuda")
    tokenizer.eval()
    print("  BiCodec loaded OK")

    # ── Step 8: 載入 WavLM ──
    print("\n[Step 8] 載入 WavLM...")
    from transformers import AutoModel

    semantic_model = AutoModel.from_pretrained("microsoft/wavlm-base-plus")
    semantic_model = semantic_model.to("cuda")
    semantic_model.eval()
    semantic_model.requires_grad_(False)
    print("  WavLM loaded OK")

    dnn = dnn.to("cuda")
    dnn.eval()

    # ── Step 9: 測試特征提取 ──
    print("\n[Step 9] 測試特征提取...")

    def extract_semantic_features(wavs):
        import torch.nn.functional as F

        wavs = F.pad(wavs, (160, 160))
        feats = semantic_model(wavs, output_hidden_states=True)
        return torch.stack(feats.hidden_states, dim=1).mean(1).detach()

    def stft_logmel(x):
        import torch.nn.functional as F
        from torchaudio.functional import melscale_fbanks

        assert x.ndim == 2
        hop = llm_config["stft_config"]["hop_length"]
        win = llm_config["stft_config"]["win_length"]
        n_fft = llm_config["stft_config"]["n_fft"]
        n_mels = llm_config["stft_config"]["n_mels"]

        pad = hop - x.size(-1) % hop if x.size(-1) % hop != 0 else 0
        if pad:
            x = F.pad(x, ((win - hop) // 2, (win - hop) // 2 + pad))
        else:
            x = F.pad(x, ((win - hop) // 2, (win - hop) // 2))

        spec = torch.stft(
            x,
            n_fft,
            hop,
            win,
            window=torch.hann_window(win).to(x.device),
            onesided=True,
            center=False,
            return_complex=True,
        ).transpose(1, 2)

        mag = spec.abs()
        if not hasattr(stft_logmel, "_fb"):
            fb = melscale_fbanks(
                n_freqs=n_fft // 2 + 1,
                f_min=0,
                f_max=8000,
                n_mels=n_mels,
                sample_rate=16000,
            )
            stft_logmel._fb = fb.to(x.device)
        mel = mag @ stft_logmel._fb
        return torch.log(mel + 1e-10)

    mix_t = torch.from_numpy(mix).float().to("cuda").unsqueeze(0)
    enroll_t = torch.from_numpy(enroll).float().to("cuda").unsqueeze(0)

    print(f"  mix shape: {mix_t.shape}")
    print(f"  enroll shape: {enroll_t.shape}")

    enroll_mel = stft_logmel(enroll_t)
    enroll_feats = extract_semantic_features(enroll_t)
    print(f"  enroll_mel shape: {enroll_mel.shape}")
    print(f"  enroll_feats shape: {enroll_feats.shape}")

    mix_mel = stft_logmel(mix_t)
    mix_feats = extract_semantic_features(mix_t)
    print(f"  mix_mel shape: {mix_mel.shape}")
    print(f"  mix_feats shape: {mix_feats.shape}")

    # ── Step 10: 測試 TSE generate ──
    print("\n[Step 10] 測試 TSE generate...")

    seg_len = 5 * 16000
    pad_len = math.ceil(mix_t.size(-1) / seg_len) * seg_len - mix_t.size(-1)

    src_padded = np.pad(mix_t.cpu().numpy(), [(0, 0), (0, pad_len)], "wrap")
    src_padded = torch.from_numpy(src_padded).to("cuda")
    src_padded = src_padded.reshape(-1, seg_len)

    print(f"  src_padded shape: {src_padded.shape}")

    enroll_mel_batch = torch.cat([enroll_mel for _ in range(src_padded.size(0))], dim=0)
    enroll_feats_batch = torch.cat(
        [enroll_feats for _ in range(src_padded.size(0))], dim=0
    )
    print(f"  enroll_mel_batch shape: {enroll_mel_batch.shape}")
    print(f"  enroll_feats_batch shape: {enroll_feats_batch.shape}")

    mix_mel_batch = stft_logmel(src_padded)
    mix_feats_batch = extract_semantic_features(src_padded)
    print(f"  mix_mel_batch shape: {mix_mel_batch.shape}")
    print(f"  mix_feats_batch shape: {mix_feats_batch.shape}")

    # 測試 TSE task
    print("\n  >>> 執行 dnn.generate(task_name='tse') ...")
    try:
        with torch.no_grad():
            global_ids, semantic_ids = dnn.generate(
                task_name="tse",
                enroll_mel=enroll_mel_batch,
                enroll_feats=enroll_feats_batch,
                mix_mel=mix_mel_batch,
                mix_feats=mix_feats_batch,
                do_sample=False,  # 先試 greedy
            )
        print(f"  global_ids shape: {global_ids.shape}")
        print(f"  semantic_ids shape: {semantic_ids.shape}")
        print(
            f"  global_ids range: [{global_ids.min().item()}, {global_ids.max().item()}]"
        )
        print(
            f"  semantic_ids range: [{semantic_ids.min().item()}, {semantic_ids.max().item()}]"
        )

        # 檢查 token 分佈是否有意義
        unique_global = global_ids.unique().numel()
        unique_semantic = semantic_ids.unique().numel()
        print(
            f"  unique global tokens: {unique_global} (expected ~{seg_len // 2 * 32 / 5})"
        )
        print(f"  unique semantic tokens: {unique_semantic}")

        # 測試 detokenize
        print("\n  >>> 執行 detokenize...")
        est = tokenizer.detokenize(global_ids.unsqueeze(1), semantic_ids).squeeze(1)
        print(f"  est shape: {est.shape}")
        print(f"  est range: [{est.min().item()}, {est.max().item()}]")

        # 截斷回原始長度
        est = est.reshape(-1)[: mix_t.size(-1)].cpu().numpy()

        # 比較輸出和輸入
        print("\n[Step 11] 比較輸出與輸入...")
        print(f"  mix  range: [{mix.min():.4f}, {mix.max():.4f}]")
        print(f"  est  range: [{est.min():.4f}, {est.max():.4f}]")
        print(f"  mix  mean: {mix.mean():.6f}")
        print(f"  est  mean: {est.mean():.6f}")
        print(f"  mix  rms:  {np.sqrt(np.mean(mix**2)):.6f}")
        print(f"  est  rms:  {np.sqrt(np.mean(est**2)):.6f}")

        # 計算相關性
        corr = np.corrcoef(mix[: len(est)], est)[0, 1]
        print(f"  Pearson correlation (mix vs est): {corr:.4f}")

        # 計算 MSE
        mse = np.mean((mix[: len(est)] - est) ** 2)
        print(f"  MSE (mix vs est): {mse:.8f}")

        # 寫出測試音檔
        import soundfile as sf

        output_path = PROJECT_ROOT / "output" / "tse_debug.wav"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), est, 16000)
        print(f"\n  診斷輸出 → {output_path}")

        # 也寫出 mix 方便比較
        sf.write(str(PROJECT_ROOT / "output" / "mix_reference.wav"), mix, 16000)
        print(f"  混合音訊參考 → {PROJECT_ROOT / 'output' / 'mix_reference.wav'}")

    except Exception as e:
        print(f"  ERROR during generate: {e}")
        import traceback

        traceback.print_exc()

    # ── Step 12: 測試 do_sample=True ──
    print("\n[Step 12] 測試 TSE generate (do_sample=True)...")
    try:
        with torch.no_grad():
            global_ids2, semantic_ids2 = dnn.generate(
                task_name="tse",
                enroll_mel=enroll_mel_batch,
                enroll_feats=enroll_feats_batch,
                mix_mel=mix_mel_batch,
                mix_feats=mix_feats_batch,
                do_sample=True,
            )
        est2 = tokenizer.detokenize(global_ids2.unsqueeze(1), semantic_ids2).squeeze(1)
        est2 = est2.reshape(-1)[: mix_t.size(-1)].cpu().numpy()

        corr2 = np.corrcoef(mix[: len(est2)], est2)[0, 1]
        mse2 = np.mean((mix[: len(est2)] - est2) ** 2)

        print(f"  do_sample=True:")
        print(f"    Pearson correlation: {corr2:.4f}")
        print(f"    MSE: {mse2:.8f}")

        sf.write(
            str(PROJECT_ROOT / "output" / "tse_debug_sample_true.wav"), est2, 16000
        )
        print(f"    輸出 → {PROJECT_ROOT / 'output' / 'tse_debug_sample_true.wav'}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 70)
    print("診斷完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
