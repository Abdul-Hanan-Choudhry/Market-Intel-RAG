"""Download the GGUF model over plain HTTPS with resume support.

Usage: python scripts/download_model.py [repo] [filename]
Defaults come from LLM_REPO / LLM_FILE in .env.
"""

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rag.config import settings

repo = sys.argv[1] if len(sys.argv) > 1 else settings.llm_repo
filename = sys.argv[2] if len(sys.argv) > 2 else settings.llm_file
url = f"https://huggingface.co/{repo}/resolve/main/{filename}"
dest = settings.models_dir / filename
part = dest.with_suffix(dest.suffix + ".part")

if dest.exists():
    print(f"already downloaded: {dest}")
    sys.exit(0)

done = part.stat().st_size if part.exists() else 0
headers = {"Range": f"bytes={done}-"} if done else {}
with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=60) as r:
    r.raise_for_status()
    total = done + int(r.headers.get("content-length", 0))
    print(f"{url}\n-> {dest} ({total / 2**30:.2f} GB, resuming at {done / 2**20:.0f} MB)", flush=True)
    t0, last = time.time(), 0.0
    with part.open("ab") as f:
        for block in r.iter_bytes(1 << 20):
            f.write(block)
            done += len(block)
            if time.time() - last > 15:
                speed = (done - (total - int(r.headers.get("content-length", 0)))) / (time.time() - t0) / 2**20
                print(f"{done / total:6.1%}  {done / 2**20:7.0f} MB  {speed:5.1f} MB/s", flush=True)
                last = time.time()
part.rename(dest)
print(f"DOWNLOADED {dest}")
