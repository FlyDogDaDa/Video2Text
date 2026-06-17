import json
from io import IOBase
from pathlib import Path, PosixPath
from typing import Any, Generator


def read_jsonl(
    file_source: str | Path | PosixPath | IOBase,
) -> Generator[dict[str, Any], None, None]:
    """讀取 JSONL 檔案，逐行 yield 轉換後的字典。"""
    # 如果傳入的是路徑（字串或 Path），就安全開啟它
    if isinstance(file_source, (str, Path, PosixPath)):
        file_source = Path(file_source)
        # 檢查副檔名
        if not file_source.suffix == ".jsonl":
            raise ValueError("file_source 必須是 .jsonl 副檔名的路徑或 IO 檔案物件")
        with open(file_source, "r", encoding="utf-8") as f:
            yield from read_jsonl(f)  # 遞迴呼叫
        return

    # 如果傳入的不是 IO 檔案物件，則拋出錯誤
    if not isinstance(file_source, IOBase):
        raise TypeError("file_source 必須是 str, Path 或 IO 檔案物件")
    # 如果傳入的是已經開啟的檔案 IO 物件
    for line in file_source:
        if line := line.strip():
            yield json.loads(line)


def write_jsonl(
    file_source: str | Path | IOBase,
    item: Any,
) -> None:
    """寫入資料至 JSONL 檔案。"""
    # 如果傳入的是路徑（字串或 Path），就開啟它並遞迴呼叫
    if isinstance(file_source, (str, Path)):
        file_source = Path(file_source)
        # 檢查副檔名
        if not file_source.suffix == ".jsonl":
            raise ValueError("file_source 必須是 .jsonl 副檔名的路徑或 IO 檔案物件")
        with open(file_source, mode="a", encoding="utf-8") as f:
            write_jsonl(f, item)
        return  # 記得 return 結束這次執行

    # 如果傳入的不是 IO 檔案物件，則拋出錯誤
    if not isinstance(file_source, IOBase):
        raise TypeError("file_source 必須是 str, Path 或 IO 檔案物件")

    json_str = json.dumps(item, ensure_ascii=False)
    file_source.write(json_str + "\n")
