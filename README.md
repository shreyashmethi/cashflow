
# LLM Document Pipeline (Planner + Vision + Excel Codegen)

This module adds an **LLM-driven planner** and **extractors** that work across many document types:

- Configurable LLMs: **GPT (default)** or **Claude** (any model string).
- **Folder ingestion** (process many docs at once).
- Planner uses LLM to **classify** each document and select the best strategy.
- **Vision** capability for PDFs/images, with auto **full-document** vs **page-by-page**.
- **Excel**: pre-planning + optional **dynamic code generation** to extract tables with pandas.

## Install

```bash
pip install openai anthropic pandas numpy pypdf pillow
# Optional but recommended for PDFs -> images:
pip install pymupdf  # or: pip install pdf2image
# Optional for Word/HTML text previews:
pip install python-docx beautifulsoup4
```

Set API keys in env:

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
```

## Usage

```python
from llm_doc_pipeline.config import PipelineConfig, LLMConfig, VisionConfig, PlannerConfig
from llm_doc_pipeline.run_pipeline import run_folder

cfg = PipelineConfig(
    llm=LLMConfig(provider="gpt", model=None, enable_vision=True),
    vision=VisionConfig(strategy="auto", max_pages_full=15, dpi=180),
    planner=PlannerConfig(concurrency=2, classify_with_llm=True),
)

results = run_folder("/path/to/folder", cfg, output_jsonl="out.jsonl")
```

Or CLI:

```bash
python -m llm_doc_pipeline.run_pipeline --input ./docs --provider gpt --vision auto --concurrency 4 --jsonl results.jsonl
```

## What it does

1. **Scan folder** for supported files.
2. **Plan** per file (LLM classifies + chooses a strategy):
   - `excel` → Excel extractor
   - `vision_full` → send all pages/images to LLM
   - `vision_per_page` → page loop, merge JSON
   - `text` → text chunk to LLM
3. **Extract** with the selected strategy.
4. **Write** JSONL (optional).

## Excel dynamic codegen

- Pre-plans layout by LLM (or heuristics fallback).
- Optionally asks the LLM to **generate a pandas program** to transform sheets into a single `result` DataFrame.
- You may disable execution of generated code (for review) via config.

## Notes

- When vision is off or not available, the pipeline falls back to text.
- For very long PDFs, the planner may choose **page-by-page** to control token usage.
- Safety: executing generated code is sandboxed with a **very restricted** environment, but still review in sensitive contexts.

## Spec-driven extraction & Post-processing

You can pass a JSON **field spec** so the extractor asks the LLM to fill exactly those fields
(with metadata like `confidence`, `page`, and `provenance`). Use the included sample:

```bash
python -m llm_doc_pipeline.run_pipeline --input ./docs --provider gpt --vision auto --spec llm_doc_pipeline/sample_spec_annual_report.json --jsonl results.jsonl
```

Programmatic:

```python
import json
from llm_doc_pipeline.config import PipelineConfig, LLMConfig, VisionConfig, PlannerConfig
from llm_doc_pipeline.run_pipeline import run_folder
from llm_doc_pipeline.postprocess import PostProcessorSDK, SampleAnnualReportProcessor

with open("llm_doc_pipeline/sample_spec_annual_report.json","r") as f:
    spec = json.load(f)

cfg = PipelineConfig(
    llm=LLMConfig(provider="gpt", enable_vision=True),
    vision=VisionConfig(strategy="auto"),
    planner=PlannerConfig(concurrency=4),
)

post = PostProcessorSDK()
post.register(SampleAnnualReportProcessor())

results = run_folder("./docs", cfg, spec=spec, post_sdk=post, output_jsonl="results.jsonl")
```

Each extracted scalar field is an object:

```json
{
  "company_name": {"value": "Fairfax Financial Holdings Limited", "confidence": 0.93, "page": 1, "provenance": {"text": "Fairfax Financial Holdings Limited", "bbox": null}}
}
```

Each array row contains per-cell objects with the same structure.
The `PostProcessorSDK` then runs validation + enrichment (see `postprocess.py`).
