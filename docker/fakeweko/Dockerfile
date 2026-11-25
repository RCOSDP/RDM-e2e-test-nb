FROM python:3.12-slim
WORKDIR /srv
RUN pip install --no-cache-dir Flask==3.1.2 gunicorn==23.0.0
COPY app.py records.py register.py item-*.json ./
CMD ["gunicorn", "--bind", "0.0.0.0:443", "--certfile", "/certs/server.crt", "--keyfile", "/certs/server.key", "--access-logfile", "-", "--access-logformat", "%(m)s %(U)s %(s)s", "app:app"]
