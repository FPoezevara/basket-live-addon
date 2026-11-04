ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

# Les outils de compilation ne servent que si pip ne trouve pas de wheel musl ; ils sont retirés aussitôt
COPY requirements.txt /tmp/requirements.txt
RUN apk add --no-cache python3 py3-pip tzdata \
    && apk add --no-cache --virtual .build-deps gcc musl-dev python3-dev \
    && pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && apk del .build-deps \
    && rm /tmp/requirements.txt

WORKDIR /opt/basket_live
COPY app/ ./app/
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
