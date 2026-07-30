import os
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from parse_worker import process_file

def main():
    pdf_dir = sys.argv[1] if len(sys.argv) > 1 else "./pdfs"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "./output"
    gpu_ids = [0, 1, 2, 3]  # 使用前4张卡

    pdf_files = sorted(Path(pdf_dir).glob("*.pdf"))
    print(f"共 {len(pdf_files)} 份PDF，分配到 {len(gpu_ids)} 张GPU")

    # 把PDF列表分配给各GPU
    # (gpu_id, pdf_path) 任务队列
    tasks = [
        (gpu_ids[i % len(gpu_ids)], str(pdf), out_dir)
        for i, pdf in enumerate(pdf_files)
    ]

    with ProcessPoolExecutor(max_workers=len(gpu_ids)) as executor:
        futures = {
            executor.submit(process_file, gpu_id, pdf_path, out_dir): pdf_path
            for gpu_id, pdf_path, out_dir in tasks
        }
        for future in as_completed(futures):
            pdf = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"[错误] {pdf}: {e}", flush=True)

if __name__ == "__main__":
    main()