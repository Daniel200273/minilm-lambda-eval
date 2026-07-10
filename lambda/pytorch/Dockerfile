FROM public.ecr.aws/lambda/python:3.12

# Install CPU-only torch first. Lambda has no GPU, so the default CUDA build
# (~2 GB of nvidia libraries) is dead weight that only makes the image-pull
# cold start slower. The CPU wheel is ~180 MB.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY lambda/pytorch/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chmod=755 model/pytorch/  /var/task/model/pytorch/
COPY data/  /var/task/data/
COPY lambda/shared/similarity.py  /var/task/shared/similarity.py
COPY lambda/pytorch/handler.py  /var/task/

CMD ["handler.lambda_handler"]