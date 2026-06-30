import sys
from src.logger import logger
from src.database import get_questions, start_run, finish_run, save_mention_response, save_sentiment_response
from src.querier import query_all_engines
from src.parser import parse_response
import time

def main():
    logger.info("Starting run...")
    run_id = start_run()

    try:
        questions = get_questions()
        logger.info(f"Loaded {len(questions)} questions")

        for question_id, question, question_type in questions:
            logger.info(f"Querying: {question}")

            engine_results = query_all_engines(question)

            for engine, result in engine_results.items():
                if "error" in result:
                    logger.error(f"[{engine}] Failed for '{question}': {result['error']}")
                    continue

                parsed = parse_response(
                    question=question,
                    question_type=question_type,
                    raw_response=result["text"],
                    citations=result["citations"]
                )

                if not parsed:
                    logger.error(f"[{engine}] Parser returned empty for '{question}'")
                    continue

                if question_type in ("course", "general"):
                    save_mention_response(
                        run_id=run_id,
                        question_id=question_id,
                        engine=engine,
                        raw_response=result["text"],
                        citations=result["citations"],
                        parsed=parsed
                    )
                else:
                    save_sentiment_response(
                        run_id=run_id,
                        question_id=question_id,
                        engine=engine,
                        raw_response=result["text"],
                        citations=result["citations"],
                        parsed=parsed
                    )

                logger.info(f"[{engine}] Saved {question_type} response for '{question}'")
            time.sleep(2)
        finish_run(run_id, status="success")
        logger.info("Run complete")

    except Exception as e:
        finish_run(run_id, status="failed", error=str(e))
        logger.error(f"Run failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()