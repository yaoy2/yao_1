FROM python:3.12-slim
WORKDIR /app
COPY integrations/m14/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home m14
COPY utils/todo_db.py utils/todo_chat.py utils/github_backup_sync.py /app/utils/
COPY scripts/m14_mcp.py /app/scripts/m14_mcp.py
RUN mkdir -p /var/lib/m14-auth && chown m14:m14 /var/lib/m14-auth
USER m14
ENV M14_AUTH_STATE_DIR=/var/lib/m14-auth
EXPOSE 8000
CMD ["python", "scripts/m14_mcp.py", "--transport", "http"]
