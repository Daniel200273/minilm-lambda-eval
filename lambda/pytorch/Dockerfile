FROM public.ecr.aws/lambda/python:3.12

COPY lambda/pytorch/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY model/pytorch/  /var/task/model/pytorch/
COPY data/  /var/task/data/
COPY lambda/shared/similarity.py  /var/task/shared/similarity.py
COPY lambda/pytorch/handler.py  /var/task/

CMD ["handler.lambda_handler"]