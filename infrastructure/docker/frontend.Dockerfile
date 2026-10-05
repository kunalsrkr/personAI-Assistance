FROM node:22-alpine AS build

WORKDIR /app

# Optional host SSL-inspection CA (gitignored). Node keeps its own trust store.
COPY infrastructure/docker/certs/ /tmp/extra-certs/
RUN set -e; \
    mkdir -p /usr/local/share/ca-certificates; \
    if ls /tmp/extra-certs/*.crt >/dev/null 2>&1; then \
      cat /tmp/extra-certs/*.crt > /usr/local/share/ca-certificates/extra-ca.crt; \
    fi

ENV NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/extra-ca.crt

COPY frontend/package.json frontend/package-lock.json* /app/
RUN npm install
COPY frontend /app
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY infrastructure/docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
