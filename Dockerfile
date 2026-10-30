# Dependency-free: standard library only, so the image stays tiny and there is
# no install step to break.
FROM python:3.12-slim
WORKDIR /app
COPY kabo_mcp_server.py kabo_food_data.json ./
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",8000)}/health',timeout=4)"
CMD ["python3", "kabo_mcp_server.py", "--http"]
