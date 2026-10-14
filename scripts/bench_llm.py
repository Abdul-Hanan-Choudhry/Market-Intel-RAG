"""Measure local LLM speed: prompt processing (reading) vs generation (writing).

On CPU these differ a lot, and the RAG context size is chosen from these numbers.
Usage: python scripts/bench_llm.py [model.gguf] [n_threads] [n_threads_batch]
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llama_cpp import Llama

from rag.config import settings

model = sys.argv[1] if len(sys.argv) > 1 else settings.llm_file
threads = int(sys.argv[2]) if len(sys.argv) > 2 else settings.llm_threads
threads_batch = int(sys.argv[3]) if len(sys.argv) > 3 else threads

t = time.perf_counter()
llm = Llama(model_path=str(settings.models_dir / model), n_ctx=4096, n_threads=threads,
            n_threads_batch=threads_batch, n_batch=512, verbose=False)
print(f"{model} threads={threads} batch_threads={threads_batch} load={time.perf_counter() - t:.1f}s")

context = "The State Bank of Pakistan kept the policy rate unchanged as inflation eased. " * 70
prompt = f"{context}\nIn one sentence, what did the central bank do?"
n_prompt = len(llm.tokenize(prompt.encode()))

t = time.perf_counter()
first = None
n_gen = 0
for chunk in llm.create_completion(prompt, max_tokens=48, temperature=0, stream=True):
    if first is None:
        first = time.perf_counter() - t
    n_gen += 1
total = time.perf_counter() - t
print(f"  prompt {n_prompt} tok in {first:.1f}s = {n_prompt / first:.0f} tok/s reading | "
      f"generation {(n_gen - 1) / (total - first):.1f} tok/s")
