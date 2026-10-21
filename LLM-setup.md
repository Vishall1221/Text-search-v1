# Local query-extraction LLM

This installation is for interpreting a search query into fields such as movie title, cast, genre, language, and scene/dialogue clues. It does **not** generate embeddings, rerank results, or change the agreed lexical search flow.

- Model: Qwen3-4B-Instruct-2507, Q4_K_M GGUF (4-bit), Apache-2.0. The upstream model is from Qwen; this GGUF quantization is from Unsloth.
- Model file: `models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf`
- Runtime: llama.cpp b11756 for Windows x64 with CUDA 12.4, under `runtime/`.
- Tested PC: Intel i7-12700H, 16 GB RAM, NVIDIA RTX 3050 Ti Laptop GPU (4 GB VRAM).

From PowerShell in this folder, start the local API with:

```powershell
& .\runtime\llama-server.exe -m .\models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf -c 2048 -ngl 99 --host 127.0.0.1 --port 8081
```

The API is local-only at `http://127.0.0.1:8081/v1/chat/completions`. Keep the context at 2048 for this 4 GB GPU; raising it significantly may exhaust VRAM. Stop the server with Ctrl+C.

For the eventual extraction prompt, distinguish **requested movie language** from the language used to write the query, and validate extracted titles, genres, cast, and languages against CMS before applying filters. A smoke test showed that otherwise the model can invent a genre or treat the query language as the movie language.

Sources:

- Original model and license: https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
- Quantized model: https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF
- Runtime release: https://github.com/ggml-org/llama.cpp/releases/tag/b11756

The model choice is a starting point for your local benchmarks, not a commitment to use it in production. The Mac will need a macOS runtime build, but the GGUF file itself is portable.
