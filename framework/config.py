"""Config management — profile-based YAML loading with Pydantic validation."""

import yaml
from pydantic import BaseModel

# Global state — set once, read many times
_PROFILE_PATH = "profiles/default.yaml"


def set_profile(path: str) -> None:
    """Set the profile path. Called once at startup (in workflow.py).

    Parameters
    ----------
    path:
        Path to the YAML profile file (e.g. "profiles/research.yaml").
    """
    global _PROFILE_PATH
    _PROFILE_PATH = path


def get_profile_path() -> str:
    """Return the current profile path.

    Returns
    -------
    str
        The current profile path.
    """
    return _PROFILE_PATH


def cfg(key: str, model: type[BaseModel]) -> BaseModel:
    """Load a config section from the current profile and validate with Pydantic.

    Parameters
    ----------
    key:
        Section name in the YAML (e.g. "vad", "asr").
    model:
        Pydantic model class to validate and instantiate.

    Returns
    -------
    BaseModel
        An instance of *model* with fields populated from the YAML section.

    Raises
    ------
    KeyError
        If the key does not exist in the YAML.
    """
    with open(get_profile_path()) as f:
        raw = yaml.safe_load(f)
    section = raw[key]
    return model(**section)
