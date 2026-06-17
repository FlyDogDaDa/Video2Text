import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from tqdm import tqdm


# 這是每個核心要執行的任務 (CPU Bound 任務)
def run_heavy_nested_job(worker_id):
    # 外層任務：例如這個核心要處理 3 個大資料夾
    # 這裡正常使用 tqdm 的 context 管理，完全不需要寫 position！
    with tqdm(total=3, desc=f"核心 #{worker_id} - 資料夾", leave=False) as pbar_outer:
        for folder in range(3):
            # 內層任務：每個資料夾裡面要處理 5 個檔案
            # 同樣正常使用 with 管理，leave=False 讓它做完就乾淨消失
            with tqdm(total=5, desc=f"  ┗ 檔案進度", leave=False) as pbar_inner:
                for file in range(5):
                    time.sleep(0.5)  # 模擬 CPU 運算
                    pbar_inner.update(1)

            pbar_outer.update(1)

    return f"核心 {worker_id} 全部搞定"


if __name__ == "__main__":
    # 假設我們有 4 個大任務要分給多個核心
    worker_tasks = [1, 2, 3, 4]

    tqdm.write("--- 多行程多層進度條開始 ---")

    # 使用 process_map 代替原本的 ProcessPoolExecutor
    # 它會自動幫你配發 Y 軸，絕對不會互相覆蓋！
    with tqdm(total=len(worker_tasks), desc="[總體排隊進度]") as pbar:
        with ProcessPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(run_heavy_nested_job, worker_id)
                for worker_id in worker_tasks
            ]
            for future in as_completed(futures):
                result = future.result()
                pbar.update(1)

    tqdm.write("--- 任務全部結束 ---")
