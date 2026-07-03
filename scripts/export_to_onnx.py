"""
One-time local export of sentence-transformers/all-MiniLM-L6-v2 to:
  - model/onnx/      (ONNX graph + tokenizer, for the ONNX Lambda variant)
  - model/pytorch/   (full sentence-transformers model, for the PyTorch Lambda variant)

Requires: sentence-transformers, torch, optimum[exporters] (not needed at Lambda inference time).
"""
import os
import onnx
from optimum.exporters.onnx import main_export
from sentence_transformers import SentenceTransformer

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONNX_DIR = os.path.join(REPO_ROOT, "model", "onnx")
PYTORCH_DIR = os.path.join(REPO_ROOT, "model", "pytorch")

#UNUSED_DOMAINS_TO_PATCH = {"ai.onnx.ml": 3}

def dir_size_mb(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            total += os.path.getsize(os.path.join(dirpath, name))
    return total / (1024 * 1024)

# def patch_unused_opset_stamps(onnx_model_path):
#     model = onnx.load(onnx_model_path)
#     domains_used = {node.domain for node in model.graph.node}

#     changed = False
#     for op in model.opset_import:
#         if op.domain in UNUSED_DOMAINS_TO_PATCH:
#             if op.domain in domains_used:
#                 raise RuntimeError(
#                     f"Refusing to patch domain {op.domain!r} - it IS used "
#                     f"by the graph. Re-check before exporting."
#                 )
#             target_version = UNUSED_DOMAINS_TO_PATCH[op.domain]
#             print(f"  Patching unused domain {op.domain!r}: "
#                   f"opset {op.version} -> {target_version}")
#             op.version = target_version
#             changed = True

#     if changed:
#         onnx.save(model, onnx_model_path)

def main():
    os.makedirs(ONNX_DIR, exist_ok=True)
    os.makedirs(PYTORCH_DIR, exist_ok=True)

    print(f"Exporting {MODEL_ID} to ONNX at {ONNX_DIR} ...")
    main_export(
        model_name_or_path=MODEL_ID,
        output=ONNX_DIR,
        task="feature-extraction",
        opset=14,
        optimize="O2",
        library_name="transformers",
    )

    # onnx_model_path = os.path.join(ONNX_DIR, "model.onnx")
    # print("Checking for unused opset domain stamps...")
    # patch_unused_opset_stamps(onnx_model_path)

    print(f"Saving full PyTorch model to {PYTORCH_DIR} ...")
    model = SentenceTransformer(MODEL_ID)
    model.save(PYTORCH_DIR)

    print("\nDone.")
    print(f"  model/onnx/    : {dir_size_mb(ONNX_DIR):.1f} MB")
    print(f"  model/pytorch/ : {dir_size_mb(PYTORCH_DIR):.1f} MB")


if __name__ == "__main__":
    main()
