FROM python:3.11-alpine
WORKDIR /usr/src/app
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
COPY . .
RUN apk update \
    && apk add postgresql-dev gcc python3-dev musl-dev  \
    && pip install --upgrade pip \
    && pip install -r requirements.txt \
    && rm -f /var/lib/apt/lists/*
