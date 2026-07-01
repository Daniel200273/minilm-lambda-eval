"""
Local smoke test: verify the ONNX and PyTorch Lambda handlers return
identical top-5 results (same questions, same order, scores within 1e-3).

Requires model/onnx/, model/pytorch/, data/corpus_questions.json,
data/corpus_embeddings.npy, and data/user_questions.json to already exist
(run export_to_onnx.py, precompute_embeddings.py, curate_user_questions.py first).
"""
import importlib.util
import json
import os
import random
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LAMBDA_TASK_ROOT"] = REPO_ROOT
sys.path.insert(0, os.path.join(REPO_ROOT, "lambda", "shared"))


def load_handler(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_queries():
    with open(os.path.join(REPO_ROOT, "data", "user_questions.json")) as f:
        user_questions = json.load(f)

    by_bucket = {"short": [], "medium": [], "long": []}
    for entry in user_questions:
        by_bucket[entry["bucket"]].append(entry)

    random.seed(0)
    sampled = []
    for bucket, entries in by_bucket.items():
        sampled.extend(random.sample(entries, min(3, len(entries))))
    return sampled


def main():
    print("Loading ONNX handler (cold start)...")
    onnx_handler = load_handler("onnx_handler", os.path.join(REPO_ROOT, "lambda", "onnx", "handler.py"))
    print("Loading PyTorch handler (cold start)...")
    pytorch_handler = load_handler("pytorch_handler", os.path.join(REPO_ROOT, "lambda", "pytorch", "handler.py"))

    queries = sample_queries()
    print(f"\nRunning {len(queries)} test queries...\n")

    failures = 0
    for entry in queries:
        query = entry["question"]
        event = {"body": json.dumps({"query": query, "top_k": 5})}

        onnx_resp = onnx_handler.lambda_handler(event, None)
        pytorch_resp = pytorch_handler.lambda_handler(event, None)

        ok = True
        if onnx_resp["statusCode"] != 200:
            ok = False
            print(f"FAIL [{entry['bucket']}] '{query}': onnx statusCode={onnx_resp['statusCode']}")
        if pytorch_resp["statusCode"] != 200:
            ok = False
            print(f"FAIL [{entry['bucket']}] '{query}': pytorch statusCode={pytorch_resp['statusCode']}")

        if ok:
            onnx_body = json.loads(onnx_resp["body"])
            pytorch_body = json.loads(pytorch_resp["body"])
            onnx_results = onnx_body["results"]
            pytorch_results = pytorch_body["results"]

            onnx_questions = [r["question"] for r in onnx_results]
            pytorch_questions = [r["question"] for r in pytorch_results]

            if onnx_questions != pytorch_questions:
                ok = False
                print(f"FAIL [{entry['bucket']}] '{query}': top-5 questions differ")
                print(f"  onnx:    {onnx_questions}")
                print(f"  pytorch: {pytorch_questions}")
            else:
                for o, p in zip(onnx_results, pytorch_results):
                    if abs(o["score"] - p["score"]) > 1e-3:
                        ok = False
                        print(
                            f"FAIL [{entry['bucket']}] '{query}': score mismatch at rank {o['rank']} "
                            f"(onnx={o['score']:.4f}, pytorch={p['score']:.4f})"
                        )

        if ok:
            print(
                f"PASS [{entry['bucket']}] '{query}' "
                f"(onnx={onnx_body['inference_ms']:.1f}ms, pytorch={pytorch_body['inference_ms']:.1f}ms)"
            )
        else:
            failures += 1

    print(f"\n{len(queries) - failures}/{len(queries)} passed")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
