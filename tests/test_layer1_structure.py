"""結構檢查測試 — Layer 1: 專案目錄與模組結構驗證。"""

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Flat layout — framework, modules, profiles 都在專案根目錄
PACKAGE_DIR = PROJECT_ROOT

# ---------------------------------------------------------------------------
# 輔助常數
# ---------------------------------------------------------------------------

MODULES = [
    "vad",
    "asr",
    "video_desc",
    "clean",
    "summarize",
]

EXPECTED_YAMLS = ["default.yaml", "research.yaml", "final.yaml"]

PROFILE_DIR = PACKAGE_DIR / "profiles"  # 在 flat layout 中即 PROJECT_ROOT/profiles

MAIN_FUNCTIONS = {
    "vad": "detect_speech",
    "asr": "transcribe",
    "video_desc": "describe_frames",
    "clean": "reduce_redundancy",
    "summarize": "generate_summary",
}


# ---------------------------------------------------------------------------
# Test 1: framework/config.py 存在
# ---------------------------------------------------------------------------


def test_framework_exists():
    """framework/config.py 檔案存在。"""
    config_path = (
        PACKAGE_DIR / "framework" / "config.py"
    )  # flat layout: PROJECT_ROOT/framework/config.py
    assert config_path.exists(), (
        f"{config_path} 不存在 — 請確認 framework/config.py 已建立"
    )


# ---------------------------------------------------------------------------
# Test 2: framework.config 可匯入且導出 cfg, set_profile
# ---------------------------------------------------------------------------


def test_framework_imports():
    """``from framework.config import cfg, set_profile`` 不會報錯。"""
    # 確保專案根目錄可被發現（flat layout）
    package_dir = str(PACKAGE_DIR)
    if package_dir not in sys.path:
        sys.path.insert(0, package_dir)

    try:
        from framework.config import cfg, set_profile  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"from framework.config import cfg, set_profile 匯入失敗: {exc}")
    finally:
        # 清理已載入的模組，避免污染其他測試
        for mod_name in ("framework", "framework.config"):
            sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# Test 3: modules/__init__.py 存在
# ---------------------------------------------------------------------------


def test_modules_exists():
    """modules/__init__.py 檔案存在。"""
    init_path = (
        PACKAGE_DIR / "modules" / "__init__.py"
    )  # flat layout: PROJECT_ROOT/modules/__init__.py
    assert init_path.exists(), f"{init_path} 不存在 — 請建立 modules/__init__.py"


# ---------------------------------------------------------------------------
# Test 4: 每個模組可獨立匯入主函式
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name,func_name", MAIN_FUNCTIONS.items())
def test_each_module_import(module_name, func_name):
    """每個模組的 ``from modules.<name> import <func>`` 不報錯。"""
    package_dir = str(PACKAGE_DIR)
    if package_dir not in sys.path:
        sys.path.insert(0, package_dir)

    mod_path = (
        PACKAGE_DIR / "modules" / f"{module_name}.py"
    )  # flat layout: PROJECT_ROOT/modules/{name}.py
    assert mod_path.exists(), f"modules/{module_name}.py 不存在"

    try:
        # 用 importlib 載入，避免污染 sys.modules
        spec = importlib.util.spec_from_file_location(
            f"modules.{module_name}", mod_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        pytest.fail(f"modules.{module_name} 載入失敗: {exc}")

    assert hasattr(module, func_name), (
        f"modules/{module_name}.py 缺少主函式 {func_name}()"
    )

    # 清理
    sys.modules.pop(f"modules.{module_name}", None)


# ---------------------------------------------------------------------------
# Test 5: profiles YAML 都存在
# ---------------------------------------------------------------------------


def test_profiles_exist():
    """profiles/ 下包含 default.yaml, research.yaml, final.yaml。"""
    assert PROFILE_DIR.is_dir(), f"{PROFILE_DIR} 不是目錄 — 請建立 profiles/"

    missing = []
    for yaml_name in EXPECTED_YAMLS:
        yaml_path = PROFILE_DIR / yaml_name
        if not yaml_path.exists():
            missing.append(yaml_name)

    assert not missing, f"profiles/ 缺少以下檔案: {', '.join(missing)}"


# ---------------------------------------------------------------------------
# Test 6: 每個模組程式碼中都有 BaseModel import
# ---------------------------------------------------------------------------


def test_each_module_has_base_config():
    """每個模組檔案都包含 ``BaseModel`` 的匯入（pydantic Config class）。"""
    for module_name in MODULES:
        mod_path = (
            PACKAGE_DIR / "modules" / f"{module_name}.py"
        )  # flat layout: PROJECT_ROOT/modules/{name}.py
        assert mod_path.exists(), f"modules/{module_name}.py 不存在"

        content = mod_path.read_text()
        has_base_model = "BaseModel" in content and (
            "from pydantic import BaseModel" in content or "from pydantic" in content
        )
        assert has_base_model, (
            f"modules/{module_name}.py 缺少 BaseModel 匯入 — "
            f"Config class 應繼承自 pydantic.BaseModel"
        )
