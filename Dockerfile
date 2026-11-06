FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# catálogo de sequências: persiste apenas se houver um volume montado aqui
VOLUME ["/app/db"]

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]
