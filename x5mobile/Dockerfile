FROM node:22-bookworm-slim AS build

WORKDIR /app

ENV CI=1 \
    EXPO_NO_TELEMETRY=1 \
    npm_config_update_notifier=false

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Empty value → same-origin fetch('/login', …). nginx proxies those paths to FastAPI.
ARG EXPO_PUBLIC_API_URL=
ENV EXPO_PUBLIC_API_URL=$EXPO_PUBLIC_API_URL
ARG EXPO_PUBLIC_WEB_LAYOUT=phone
ENV EXPO_PUBLIC_WEB_LAYOUT=$EXPO_PUBLIC_WEB_LAYOUT

RUN npx expo export --platform web --output-dir dist

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/99-web-layout.sh /docker-entrypoint.d/99-web-layout.sh
COPY --from=build /app/dist /usr/share/nginx/html
RUN chmod +x /docker-entrypoint.d/99-web-layout.sh

EXPOSE 80
