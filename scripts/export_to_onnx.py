"""
Step 1 — Export MiniLM-L6-v2 to ONNX.
Run once locally before building Docker images.

Output:
  lambda/onnx/model.onnx       (~88 MB, commit to repo)
  lambda/onnx/tokenizer.json   (small, commit to repo)

Requirements:
  pip install optimum[onnxruntime] transformers torch sentence-transformers
"""
from pathlib import Path
from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
DST = Path("lambda/onnx")
DST.mkdir(parents=True, exist_ok=True)

print(f"Downloading and exporting {MODEL_ID} to ONNX...")
model = ORTModelForFeatureExtraction.from_pretrained(MODEL_ID, export=True)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

model.save_pretrained(str(DST))
tokenizer.save_pretrained(str(DST))

size_mb = (DST / "model.onnx").stat().st_size / 1e6
print(f"Done. lambda/onnx/model.onnx ({size_mb:.0f} MB)")
print("Next: run scripts/precompute_embeddings.py")
