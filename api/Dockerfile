FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Bake the embedding model into the image so the Pi needs no internet access at runtime
ENV HF_HOME=/app/.hf-cache EMBEDDING_MODEL=minishlab/potion-base-8M
RUN python -c "import os; from model2vec import StaticModel; StaticModel.from_pretrained(os.environ['EMBEDDING_MODEL'])"
ENV HF_HUB_OFFLINE=1
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
