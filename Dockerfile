# Используем официальный Python-образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект внутрь контейнера
COPY . .

# Указываем переменные окружения
ENV PYTHONUNBUFFERED=1

# Команда по умолчанию (указана также в docker-compose.yml, но на всякий случай)
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
