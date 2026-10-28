FROM node:22-alpine AS builder

# Install the pnpm version pinned in package.json.
RUN npm install -g pnpm@11.24.0

WORKDIR /app

# Install only the frontend workspace from the monorepo lockfile.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY front/package.json ./front/package.json
COPY server/package.json ./server/package.json

RUN pnpm install --frozen-lockfile --filter front...

COPY front ./front

ARG VITE_BACKEND_URL
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL

RUN pnpm --filter front build

FROM nginx:alpine

COPY --from=builder /app/front/dist /usr/share/nginx/html

RUN echo 'server { \
    listen 80; \
    location / { \
    root /usr/share/nginx/html; \
    index index.html index.htm; \
    try_files $uri $uri/ /index.html; \
    } \
    }' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
