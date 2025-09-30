
from __future__ import annotations
import os, json, concurrent.futures, traceback, sys
from typing import Dict, Any, List, Optional
from tqdm import tqdm

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config import PipelineConfig
from app.pipeline.planner import LLMPlanner, Plan
from app.pipeline.extractors import DocumentExtractor, ExcelExtractor, CsvExtractor
from app.pipeline.loaders import scan_folder

def _process_one(plan: Plan, cfg: PipelineConfig, spec: Optional[Dict[str, Any]] = None, post_sdk=None) -> Dict[str, Any]:
    path = plan.path
    try:
        if plan.strategy == "excel":
            excel = ExcelExtractor(cfg)
            out = excel.extract(path, spec=spec)
        elif plan.doc_type == "csv":
            csv_ext = CsvExtractor(cfg)
            out = csv_ext.extract(path, spec=spec)
        elif plan.strategy == "vision_full":
            de = DocumentExtractor(cfg)
            out = de.extract_vision_full(path, spec=spec)
        elif plan.strategy == "vision_per_page":
            de = DocumentExtractor(cfg)
            out = de.extract_vision_per_page(path, spec=spec)
        else:
            de = DocumentExtractor(cfg)
            out = de.extract_textual(path, spec=spec)
        return {"path": path, "doc_type": plan.doc_type, "category": plan.category, "strategy": plan.strategy, "data": out}
    except Exception as e:
        return {"path": path, "error": str(e), "trace": traceback.format_exc()}

def run_folder(input_dir: str, cfg: PipelineConfig, output_jsonl: Optional[str] = None, spec: Optional[Dict[str, Any]] = None, post_sdk=None) -> List[Dict[str, Any]]:
    files = scan_folder(input_dir, cfg.planner.allowed_extensions, recursive=cfg.planner.recursive)
    planner = LLMPlanner(cfg)
    plans = [planner.plan_for_file(p) for p in files]

    # Concurrency for extraction
    results: List[Dict[str, Any]] = []
    if cfg.planner.concurrency > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.planner.concurrency) as ex:
            futs = [ex.submit(_process_one, pl, cfg, spec) for pl in plans]
            for f in tqdm(concurrent.futures.as_completed(futs), total=len(futs), desc="Processing files"):
                results.append(f.result())
    else:
        for pl in tqdm(plans, desc="Processing files"):
            results.append(_process_one(pl, cfg, spec))

    if output_jsonl:
        with open(output_jsonl, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return results

# Simple CLI runner
def main():
    import argparse
    parser = argparse.ArgumentParser(description="LLM-powered document pipeline")
    parser.add_argument("--input", required=True, help="Input folder")
    parser.add_argument("--provider", default="gpt", choices=["gpt", "claude"], help="LLM provider")
    parser.add_argument("--model", default=None, help="Override model id")
    parser.add_argument("--vision", default="auto", choices=["auto","full_document","page_by_page","off"], help="Vision strategy")
    parser.add_argument("--no-vision", action="store_true", help="Disable vision even if available")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--jsonl", default=None, help="Write results as JSONL to this path")
    parser.add_argument("--spec", default=None, help="Path to a JSON spec file for targeted extraction")
    parser.add_argument("--vision-batch-bytes", type=int, default=45*1024*1024)
    parser.add_argument("--vision-long-side", type=int, default=1600)
    parser.add_argument("--vision-jpeg-quality", type=int, default=70)
    parser.add_argument("--vision-max-images", type=int, default=10)
    args = parser.parse_args()

    from app.config import PipelineConfig, LLMConfig, VisionConfig, PlannerConfig

    llm_enable_vision = not args.no_vision and args.vision in ["auto","full_document","page_by_page"]
    vision_strategy = "auto" if args.vision == "auto" else ("full_document" if args.vision=="full_document" else ("page_by_page" if args.vision=="page_by_page" else "auto"))

    cfg = PipelineConfig(
        llm=LLMConfig(provider=args.provider, model=args.model, enable_vision=llm_enable_vision),
        vision=VisionConfig(strategy=vision_strategy),
        planner=PlannerConfig(concurrency=args.concurrency),
    )
    
    spec = None
    if args.spec:
        with open(args.spec, "r", encoding="utf-8") as f:
            spec = json.load(f)

    results = run_folder(args.input, cfg, output_jsonl=args.jsonl, spec=spec)
    print(json.dumps(results[:2], indent=2, ensure_ascii=False))  # preview

if __name__ == "__main__":
    main()
