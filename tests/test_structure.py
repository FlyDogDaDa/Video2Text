"""結構檢查測試 — Layer 1: 專案目錄與模組結構驗證。"""

import importlib
import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = PROJECT_ROOT / "video2text"

# ---------------------------------------------------------------------------
# 輔助常數
# ---------------------------------------------------------------------------

MODULE_FILES = [
    PACKAGE_DIR / "modules" / "vad.py",
    PACKAGE_DIR / "modules" / "asr.py",
    PACKAGE_DIR / "modules" / "video_desc.py",
    PACKAGE_DIR / "modules" / "clean.py",
    PACKAGE_DIR / "modules" / "summarize.py",
]

EXPECTED_YAMLS = {"default.yaml", "research.yaml", "final.yaml"}

PROFILE_DIR = PACKAGE_DIR / "profiles"

# ---------------------------------------------------------------------------
# 1. framework/config.py 存在且可 import
# ---------------------------------------------------------------------------


def test_framework_config_exists_and_importable():
    """framework/config.py 檔案存在且 ``import framework.config`` 不會報錯。"""
    config_path = PACKAGE_DIR / "framework" / "config.py"
    assert config_path.exists(), f"{config_path} 不存在"

    import_result = subprocess.run(
        [
            "python",
            "-c",
            "import importlib.util, sys, pathlib; "
            "spec = importlib.util.spec_from_file_location('framework.config', "
            f"pathlib.Path(r'{config_path}')); "
            "module = importlib.util.module_from_spec(spec); "
            "sys.modules['framework.config'] = module; "
            "spec.loader.exec_module(module)",
        ],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert import_result.returncode == 0, (
        f"import framework.config 失敗:\nstdout: {import_result.stdout}\n"
        f"stderr: {import_result.stderr}"
    )

    # 也確認 ``import framework.config`` 本身不會拋出 ImportError
    import_result2 = subprocess.run(
        ["python", "-c", "import framework.config"],
        capture_output=True,
        text=True,
        cwd=str(PACKAGE_DIR),
    )
    assert import_result2.returncode == 0, (
        f"import framework.config (子程序) 失敗:\nstderr: {import_result2.stderr}"
    )


# ---------------------------------------------------------------------------
# 2. modules/__init__.py 存在
# ---------------------------------------------------------------------------


def test_modules_init_exists():
    """modules/__init__.py 檔案存在。"""
    init_path = PACKAGE_DIR / "modules" / "__init__.py"
    assert init_path.exists(), "modules/__init__.py 不存在"


# ---------------------------------------------------------------------------
# 3. 每個 module 都有 BaseModel（Config class）
# ---------------------------------------------------------------------------


def test_each_module_has_config_class():
    """每個 module 檔案都包含 ``BaseModel`` 定義（pydantic Config class）。"""
    for mod_path in MODULE_FILES:
        assert mod_path.exists(), f"{mod_path} 不存在，無法檢查 BaseModel"
        content = mod_path.read_text()
        assert "BaseModel" in content, (
            f"{mod_path.name} 未發現 BaseModel（Config class 預期使用 pydantic）"
        )


# ---------------------------------------------------------------------------
# 4. workflow.py 存在
# ---------------------------------------------------------------------------


def test_workflow_py_exists():
    """專案根目錄下的 workflow.py 檔案存在。"""
    workflow_path = PROJECT_ROOT / "workflow.py"
    assert workflow_path.exists(), "workflow.py 不存在於專案根目錄"


# ---------------------------------------------------------------------------
# 5. profiles/ 下有三個 YAML 檔案
# ---------------------------------------------------------------------------


def test_profiles_has_expected_yaml_files():
    """profiles/ 目錄包含 default.yaml、research.yaml、final.yaml。"""
    assert PROFILE_DIR.is_dir(), f"{PROFILE_DIR} 不是目錄"
    existing = {p.name for p in PROFILE_DIR.glob("*.yaml")} | {
        p.name for p in PROFILE_DIR.glob("*.yml")
    }
    for name in EXPECTED_YAMLS:
        assert name in existing, f"profiles/ 缺少 {name}"


# ---------------------------------------------------------------------------
# 6. profiles/ 下沒有其他 YAML 檔案
# ---------------------------------------------------------------------------


def test_profiles_has_no_extra_yaml_files():
    """profiles/ 目錄只包含預期的三個 YAML 檔案。"""
    assert PROFILE_DIR.is_dir(), f"{PROFILE_DIR} 不是目錄"
    existing = {p.name for p in PROFILE_DIR.glob("*.yaml")} | {
        p.name for p in PROFILE_DIR.glob("*.yml")
    }
    unexpected = existing - EXPECTED_YAMLS
    assert not unexpected, (
        f"profiles/ 存在未預期的 YAML 檔案: {', '.join(sorted(unexpected))}"
    )


# ---------------------------------------------------------------------------
# 7. Config key 一致性：module Config field 在 YAML 中找到對應 key
# ---------------------------------------------------------------------------


def _extract_config_keys(file_path: Path) -> list[str]:
    """從 pydantic BaseModel Config class 中提取 field 名稱。"""
    text = file_path.read_text()

    # 尋找 class Config(BaseModel): ... 區塊
    config_class_match = re.search(
        r"class\s+Config\s*\(\s*BaseModel\s*\)\s*:(.*?)"
        r"(?=\nclass |\ncode|^def |$)",
        text,
        re.DOTALL,
    )
    if not config_class_match:
        return []

    body = config_class_match.group(1)

    # 匹配 field 定義：key: Type 或 key: Type = default
    pattern = re.compile(r"^(\w+)\s*:\s*(?!return)", re.MULTILINE)
    keys = []
    for match in pattern.finditer(body):
        name = match.group(1)
        # 排除 type: 註解風格的 False Positive
        line_start = match.start()
        line = text[:line_start].rfind("\n") + 1
        line_text = text[line:line_start].strip()
        if line_text.startswith("#"):
            continue
        keys.append(name)
    return keys


def _yaml_has_keys(file_path: Path, keys: list[str]) -> bool:
    """檢查 YAML 檔案內容是否包含所有給定 key（字串匹配）。"""
    text = file_path.read_text()
    for key in keys:
        # 檢查 key 是否出現在 YAML 內容中
        pattern = re.compile(r"(?m)^\s*" + re.escape(key) + r"\b")
        if not pattern.search(text):
            return False
    return True


def test_config_key_consistency():
    """每個 module 的 Config key（BaseModel field）在 profiles YAML 中能找到。"""
    yaml_files = sorted(
        [p for p in PROFILE_DIR.glob("*.yaml")] + [p for p in PROFILE_DIR.glob("*.yml")]
    )
    if not yaml_files:
        pytest.skip("profiles/ 下沒有 YAML 檔案")

    all_keys_in_yaml = set()
    for yaml_path in yaml_files:
        all_keys_in_yaml.update(
            k.strip() for k in re.findall(r"(?m)^\s*(\w+)\s*:", yaml_path.read_text())
        )

    for mod_path in MODULE_FILES:
        if not mod_path.exists():
            continue

        keys = _extract_config_keys(mod_path)
        if not keys:
            continue

        matched = [k for k in keys if k in all_keys_in_yaml]
        unmatched = set(keys) - set(matched)
        assert not unmatched, (
            f"{mod_path.name} 的 Config key 未能在任何 YAML 中找到: "
            f"{', '.join(sorted(unmatched))}\n"
            f"  已找到的 YAML keys: {', '.join(sorted(all_keys_in_yaml))}"
        )


# ---------------------------------------------------------------------------
# 8. module 都有 main function
# ---------------------------------------------------------------------------


def test_each_module_has_main_function():
    """每個 module 都有符合命名規範的主函式 ``def main``。"""
    for mod_path in MODULE_FILES:
        assert mod_path.exists(), f"{mod_path} 不存在"
        content = mod_path.read_text()
        assert re.search(r"^def\s+main\s*\(", content, re.MULTILINE), (
            f"{mod_path.name} 缺少 ``def main()`` 主函式"
        )
