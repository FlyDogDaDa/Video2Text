"""QuarkAudio-UniSE Python API — 目標說話人提取 (TSE)"""

import math
import sys
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import torch
from omegaconf import OmegaConf

# 加入官方 repo 路徑
PROJ_ROOT = Path(__file__).parent.parent.parent.parent
QAU_ROOT = PROJ_ROOT / "serve" / "quark-audio" / "unified-audio" / "QuarkAudio-UniSE"
sys.path.insert(0, str(QAU_ROOT))


class QuarkAudioTSE:
    """QuarkAudio-UniSE 目標說話人提取 (Target Speaker Extraction)"""

    def __init__(
        self,
        checkpoint_dir: Optional[Path] = None,
        ckpt_path: Optional[Path] = None,
        device: str = "cuda",
    ):
        """
        Args:
            checkpoint_dir: BiCodec + wav2vec2 權重目錄 (預設: unified-audio/QuarkAudio-UniSE/checkpoints/)
            ckpt_path: QuarkAudio-UniSE 權重檔案 (預設: epoch=20-step=109367.ckpt)
            device: "cuda" 或 "cpu"
        """
        self.device = torch.device(device)

        if checkpoint_dir is None:
            # QAU_ROOT = .../unified-audio/QuarkAudio-UniSE
            # 需要上兩層到 serve/quark-audio/
            checkpoint_dir = QAU_ROOT.parent.parent / "checkpoints"
        self.checkpoint_dir = checkpoint_dir

        if ckpt_path is None:
            ckpt_path = self.checkpoint_dir / "epoch=20-step=109367.ckpt"
        self.ckpt_path = Path(ckpt_path).resolve()

        self._setup()

    def _setup(self):
        # 確保 checkpoint_dir 是絕對路徑
        checkpoint_dir = Path(self.checkpoint_dir).resolve()

        import os

        print(f"[QuarkAudio] 工作目錄: {os.getcwd()}")
        print(f"[QuarkAudio] checkpoint_dir: {checkpoint_dir}")
        print(f"[QuarkAudio] ckpt_path: {self.ckpt_path}")

        # ── 讀 config ──
        config_path = QAU_ROOT / "conf" / "config.yaml"
        with open(config_path, "r") as f:
            import yaml

            config = yaml.safe_load(f)
        self.stft_conf = config["stft_config"]
        self.llm_config = config["llm_config"]

        # ── BiCodec tokenizer ──
        print("[QuarkAudio] 載入 BiCodec tokenizer...")
        from model.bicodec.audio_tokenizer import BiCodecTokenizer

        self.tokenizer = BiCodecTokenizer(model_dir=str(checkpoint_dir))
        self.tokenizer = self.tokenizer.to(self.device)
        self.tokenizer.eval()

        # ── WavLM semantic features ──
        print("[QuarkAudio] 載入 WavLM semantic model...")
        from transformers import AutoModel

        self.semantic_model = AutoModel.from_pretrained("microsoft/wavlm-base-plus")
        self.semantic_model = self.semantic_model.to(self.device)
        self.semantic_model.eval()
        self.semantic_model.requires_grad_(False)

        # ── LLM (dnn) ──
        print("[QuarkAudio] 載入 LLM (dnn)...")
        from model.llm.llm_sft import LLM_SFT

        self.dnn = LLM_SFT(**self.llm_config)

        # ── 載入 UniSE checkpoint ──
        if not self.ckpt_path.exists():
            raise FileNotFoundError(
                f"找不到權重: {self.ckpt_path}\n"
                "請先下載 QuarkAudio/QuarkAudio-UniSE checkpoint"
            )

        ckpt = torch.load(self.ckpt_path, map_location=self.device, weights_only=False)
        state_dict = ckpt.get("state_dict", ckpt)

        # 移除 lightning/module 前綴
        state_dict = {
            k.replace("dnn.", "").replace("module.dnn.", "").replace("module.", ""): v
            for k, v in state_dict.items()
            if "dnn" in k
        }
        self.dnn.load_state_dict(state_dict, strict=False)
        self.dnn = self.dnn.to(self.device)
        self.dnn.eval()

        print(f"[QuarkAudio] 載入完成 (device={self.device})")

    # ── 公開 API ──

    @torch.inference_mode()
    def extract(
        self,
        mix_path: str,
        enroll_path: str,
        output_path: str,
    ) -> str:
        """
        從混合音訊中提取指定說話人。

        Args:
            mix_path:     混合音訊檔案路徑
            enroll_path:  目標說話人參考音訊 (enrollment) 路徑
            output_path:  輸出 WAV 檔案路徑

        Returns:
            輸出檔案的絕對路徑
        """
        # 解析絕對路徑
        mix_path = Path(mix_path).resolve()
        enroll_path = Path(enroll_path).resolve()
        output_path = Path(output_path).resolve()

        print(f"[QuarkAudio] 讀取混合音訊: {mix_path}")
        print(f"[QuarkAudio] 讀取參考音訊: {enroll_path}")
        # 讀音訊 → 16kHz mono
        mix = self._load_wav(mix_path)
        enroll = self._load_wav(enroll_path)

        mix_tensor = (
            torch.from_numpy(mix).float().to(self.device).unsqueeze(0)
        )  # (1, T)
        enroll_tensor = (
            torch.from_numpy(enroll).float().to(self.device).unsqueeze(0)
        )  # (1, T)

        # 分段推理
        output = self._tse_infer(enroll_tensor, mix_tensor)

        # 寫出（output 已經是 np.ndarray）
        import soundfile as sf  # 僅寫出用

        sf.write(output_path, output, 16000)
        print(f"[QuarkAudio] 輸出 → {Path(output_path).resolve()}")
        return str(Path(output_path).resolve())

    # ── 內部方法 ──

    @staticmethod
    def _load_wav(path: str) -> np.ndarray:
        """載入並重採樣到 16kHz mono（支援 mp3 等格式）"""
        # librosa 支援 mp3 並自動處理重採樣
        wav, sr = librosa.load(str(path), sr=16000, mono=True)
        return wav

    def _extract_semantic_features(self, wavs: torch.Tensor) -> torch.Tensor:
        """WavLM 特徵提取"""
        wavs = torch.nn.functional.pad(wavs, (160, 160))
        feats = self.semantic_model(wavs, output_hidden_states=True)
        return torch.stack(feats.hidden_states, dim=1).mean(1).detach()

    def _stft_logmel(self, x: torch.Tensor) -> torch.Tensor:
        """Log-Mel spectrogram"""
        import torch.nn.functional as F
        from torchaudio.functional import melscale_fbanks

        assert x.ndim == 2  # (B, T)
        hop = self.stft_conf["hop_length"]
        win = self.stft_conf["win_length"]
        n_fft = self.stft_conf["n_fft"]
        n_mels = self.stft_conf["n_mels"]

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
        ).transpose(1, 2)  # (B, T, F)

        mag = spec.abs()  # (B, T, F)
        if not hasattr(self, "_fb"):
            fb = melscale_fbanks(
                n_freqs=n_fft // 2 + 1,
                f_min=0,
                f_max=8000,
                n_mels=n_mels,
                sample_rate=16000,
            )
            self._fb = fb.to(x.device)
        mel = mag @ self._fb
        return torch.log(mel + 1e-10)

    def _tse_infer(self, enroll: torch.Tensor, mix: torch.Tensor) -> np.ndarray:
        """TSE 推理 (照官方 model.py test_step 實作)"""
        seg_len = 5 * 16000  # 5 秒片段
        total_len = mix.size(-1)

        # 1. padding
        pad_len = math.ceil(mix.size(-1) / seg_len) * seg_len - mix.size(-1)
        src_padded = np.pad(mix.cpu().numpy(), [(0, 0), (0, pad_len)], "wrap")
        src_padded = torch.from_numpy(src_padded).to(mix.device)

        # 2. reshape 成 (batch, seg_len) 批量處理
        src_padded = src_padded.reshape(-1, seg_len)
        orig_len = mix.size(-1)  # 保留原始長度

        # 3. enroll features
        enroll_mel = self._stft_logmel(enroll)
        enroll_feats = self._extract_semantic_features(enroll)
        enroll_mel = torch.cat([enroll_mel for _ in range(src_padded.size(0))], dim=0)
        enroll_feats = torch.cat(
            [enroll_feats for _ in range(src_padded.size(0))], dim=0
        )

        # 4. mix features
        mix_mel = self._stft_logmel(src_padded)
        mix_feats = self._extract_semantic_features(src_padded)

        # 5. generate
        global_ids, semantic_ids = self.dnn.generate(
            task_name="tse",
            enroll_mel=enroll_mel,
            enroll_feats=enroll_feats,
            mix_mel=mix_mel,
            mix_feats=mix_feats,
            do_sample=False,
        )

        # 6. detokenize & reshape
        est = self.tokenizer.detokenize(global_ids.unsqueeze(1), semantic_ids).squeeze(
            1
        )  # (B, t)
        est = est.reshape(-1)[:orig_len]  # 截斷回原始長度
        return est.cpu().numpy()


# ── 便捷函式 ──


def extract_target_speaker(mix_path: str, enroll_path: str, output_path: str):
    """從混合音訊中提取指定說話人"""
    model = QuarkAudioTSE()
    return model.extract(mix_path, enroll_path, output_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="QuarkAudio-UniSE TSE")
    parser.add_argument("--mix", required=True, help="混合音訊路徑")
    parser.add_argument("--enroll", required=True, help="目標說話人參考音訊")
    parser.add_argument("--output", required=True, help="輸出路徑")
    args = parser.parse_args()

    result = extract_target_speaker(args.mix, args.enroll, args.output)
    print(f"完成: {result}")
