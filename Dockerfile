FROM python:3-alpine

RUN apk add --no-cache curl lzo-dev gcc libc-dev

WORKDIR /app
COPY ./ .

RUN pip install --no-cache-dir -U pip
RUN pip install --no-cache-dir --break-system-packages waitress

COPY req.txt .
RUN pip install --no-cache-dir -r req.txt

RUN ln -s /app/uploads/ /app/static/uploads

EXPOSE 5000/tcp

ENTRYPOINT ["waitress-serve"] 
CMD ["--host", "0.0.0.0", "--port", "5000", "--call", "app:createApp"]
