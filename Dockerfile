FROM python:3.11-slim
WORKDIR /app
COPY app ./app
COPY web ./web
COPY db ./db
COPY docs ./docs
RUN mkdir -p /app/data
ENV AI_SIM_HOST=0.0.0.0 AI_SIM_PORT=8000 AI_SIM_DB=/app/data/ai_sim.sqlite3
EXPOSE 8000
CMD ["python", "-m", "app.server"]
