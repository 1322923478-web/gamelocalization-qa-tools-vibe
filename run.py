import argparse
import sys
import os
from app.main import QATool
from dotenv import load_dotenv
from loguru import logger

# 添加 app 目录到 python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Game QA Tool")
    parser.add_argument("--input", required=True, help="Input file path (xlsx, txt)")
    parser.add_argument("--output", required=True, help="Output file path (xlsx, json)")
    parser.add_argument("--termbase", help="Termbase file path (xlsx, txt)")
    parser.add_argument("--log", default="logs/qa_tool.log", help="Log file path")
    parser.add_argument("--workers", type=int, default=None, help="Parallel workers for QA (default: env QA_MAX_WORKERS or 1)")
    parser.add_argument("--no-header", action="store_true", help="Excel has no header row (first row is data)")
    parser.add_argument("--checkers", default=None, help="Comma-separated checkers: spelling,grammar,term,context,comprehensive")
    parser.add_argument("--lean-prompts", action="store_true", help="Use lean prompts to reduce tokens")
    parser.add_argument("--theme", default="武侠", help="Theme for RAG metadata filtering")
    parser.add_argument("--text-type", default="功能", help="Text type for RAG metadata filtering")
    parser.add_argument("--qa-samples", default="data/samples", help="QA sample library path (dir or file: .json/.xlsx)")
    parser.add_argument("--provider", choices=["openai", "deepseek", "qwen", "zhipu"], default="openai", help="LLM provider")
    parser.add_argument("--model", help="LLM model (overrides provider default)")
    parser.add_argument("--api-key", help="API key (overrides .env)")
    parser.add_argument("--base-url", help="Base URL (overrides .env)")
    # 每个检查器的特定配置
    parser.add_argument("--spelling-api-key", help="API key for spelling checker (overrides general API key)")
    parser.add_argument("--grammar-api-key", help="API key for grammar checker (overrides general API key)")
    parser.add_argument("--term-api-key", help="API key for term checker (overrides general API key)")
    parser.add_argument("--context-api-key", help="API key for context checker (overrides general API key)")
    parser.add_argument("--comprehensive-api-key", help="API key for comprehensive checker (overrides general API key)")

    args = parser.parse_args()

    # 构建 LLM 配置
    llm_config = {}
    provider_prefix = args.provider.upper()
    
    # 优先使用命令行参数，其次使用 .env 中 provider 特有的配置，最后使用通用的 OPENAI_ 配置
    llm_config["api_key"] = args.api_key or os.getenv(f"{provider_prefix}_API_KEY") or os.getenv("OPENAI_API_KEY")
    llm_config["base_url"] = args.base_url or os.getenv(f"{provider_prefix}_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    llm_config["model"] = args.model or os.getenv(f"{provider_prefix}_MODEL") or os.getenv("LLM_MODEL")

    # 构建每个检查器的特定配置
    checkers_config = {}
    checker_api_keys = {
        "spelling": args.spelling_api_key,
        "grammar": args.grammar_api_key,
        "term": args.term_api_key,
        "context": args.context_api_key,
        "comprehensive": args.comprehensive_api_key
    }
    
    for checker_name, checker_api_key in checker_api_keys.items():
        if checker_api_key:
            # 为每个检查器创建独立的配置
            checkers_config[checker_name] = {
                "api_key": checker_api_key,
                "base_url": llm_config["base_url"],
                "model": llm_config["model"]
            }

    # 配置日志
    logger.add(args.log, rotation="500 MB")
    logger.info(f"Starting QA Tool with provider: {args.provider}, model: {llm_config['model']}")

    try:
        enabled_checkers = None
        if args.checkers:
            enabled_checkers = [x.strip() for x in args.checkers.split(",") if x.strip()]
        prompt_dir = "config/prompts_lean" if args.lean_prompts else "config/prompts"

        tool = QATool(
            termbase_path=args.termbase,
            samples_path=args.qa_samples,
            llm_config=llm_config,
            checkers_config=checkers_config,
            enabled_checkers=enabled_checkers,
            prompt_dir=prompt_dir,
            theme=args.theme,
            text_type=args.text_type
        )
        report = tool.run(args.input, args.output, has_header=(not args.no_header), max_workers=args.workers)
        
        print("\nQA 检查完成！")
        print(f"检查段落总数: {report.total_segments}")
        print(f"发现问题总数: {len(report.issues)}")
        print(f"报告已生成至: {args.output}")
        
    except Exception as e:
        logger.exception(f"QA Tool failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
