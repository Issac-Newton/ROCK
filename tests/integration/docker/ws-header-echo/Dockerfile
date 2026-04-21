FROM chatos-registry.cn-hangzhou.cr.aliyuncs.com/chatos/base:python3.11

RUN pip install --no-cache-dir websockets

COPY ws_header_echo.py /app/ws_header_echo.py

EXPOSE 8080

CMD ["python", "/app/ws_header_echo.py"]
