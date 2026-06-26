"""
One-time export: PyTorch model -> ONNX.
Run this once locally, then deploy only minilm-onnx/ to AWS.

Requirements (not needed at inference time):
    pip install optimum[onnxruntime] transformers torch
"""
from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer
import os

SRC = "./minilm-model"
DST = "./minilm-onnx"

print("Exporting model to ONNX...")
model = ORTModelForFeatureExtraction.from_pretrained(SRC, export=True)
tokenizer = AutoTokenizer.from_pretrained(SRC)

os.makedirs(DST, exist_ok=True)
model.save_pretrained(DST)
tokenizer.save_pretrained(DST)
print(f"Done. Saved to {DST}/")
print("   Files needed at runtime: model.onnx, tokenizer.json")
