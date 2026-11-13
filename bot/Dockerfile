FROM python:3.12-slim
WORKDIR /srv/bot
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
CMD ["python", "-m", "app.main"]
