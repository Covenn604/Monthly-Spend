FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data PORT=8080
WORKDIR /app
RUN groupadd --gid 10001 monthlyspend && useradd --uid 10001 --gid monthlyspend --no-create-home monthlyspend && mkdir /data && chown monthlyspend:monthlyspend /data
COPY --chown=monthlyspend:monthlyspend app.py auth.py migration.py /app/
COPY --chown=monthlyspend:monthlyspend static /app/static
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"
CMD ["python", "app.py"]
