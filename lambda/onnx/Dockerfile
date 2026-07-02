FROM public.ecr.aws/lambda/python:3.11

COPY lambda/onnx/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Full ONNX model + HF tokenizer folder (generated locally, see note below —
# never commit these to git)
COPY model/onnx/  /var/task/model/onnx/

# Pre-computed corpus embeddings + questions
COPY data/  /var/task/data/

# Shared similarity utility, in a "shared" subfolder to match handler.py's import
COPY lambda/shared/similarity.py  /var/task/shared/similarity.py

COPY lambda/onnx/handler.py  /var/task/

CMD ["handler.lambda_handler"]