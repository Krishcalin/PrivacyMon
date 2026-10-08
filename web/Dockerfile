# PrivacyMon admin console (SRS section 10). Build context is web/ (see
# infra/docker-compose.yml: web.build.context = ../web). Multi-stage: build the SPA
# with Node, then serve the static bundle with nginx, which also reverse-proxies
# /api to the API service so the browser calls the console same-origin (no CORS).
FROM node:20-slim AS build
WORKDIR /web
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /web/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
