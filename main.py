import sys
from src.logger import logger
from src.database import get_questions, get_processed_question_ids, start_run, finish_run, save_mention_response, save_sentiment_response, save_fanout_queries
from src.querier import query_all_engines
from src.parsing.parser import parse_response
from src.classify_run_citations import classify_and_store
import time

def main():
    resume_run_id = None
    if "--resume" in sys.argv:
        idx = sys.argv.index("--resume")
        resume_run_id = sys.argv[idx + 1]

    if resume_run_id:
        run_id = resume_run_id
        logger.info(f"Resuming run {run_id}...")
    else:
        logger.info("Starting run...")
        run_id = start_run()

    try:
        questions = get_questions()
        if resume_run_id:
            done = get_processed_question_ids(run_id)
            questions = [q for q in questions if q[0] not in done]
            logger.info(f"Skipping {len(done)} already-processed questions, {len(questions)} remaining")
        logger.info(f"Loaded {len(questions)} questions")

        for question_id, question, question_type in questions:
            logger.info(f"Querying: {question}")

            engine_results = query_all_engines(question)

            for engine, result in engine_results.items():
                if "error" in result:
                    logger.error(f"[{engine}] Failed for '{question}': {result['error']}")
                    continue

                fanout = result.get("fanout_queries", [])
                if fanout:
                    save_fanout_queries(run_id, question_id, engine, fanout)
                    logger.info(f"[{engine}] Saved {len(fanout)} fanout queries for '{question}'")

                if "text" not in result:
                    continue  # fanout-only engine (e.g. gemini), no response to parse/store

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
        try:
            logger.info("Classifying competitor citations...")
            classify_and_store(run_id)
            logger.info("Citation classification complete")
        except Exception as e:
            logger.error(f"Citation classification failed (non-fatal): {e}")

    except Exception as e:
        finish_run(run_id, status="failed", error=str(e))
        logger.error(f"Run failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()