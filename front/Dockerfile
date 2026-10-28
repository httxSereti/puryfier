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

# Optional: leave empty in production to use the current origin (same-origin
# /api and /ws through nginx). Local Docker builds may override it.
ARG VITE_BACKEND_URL=
ARG VITE_APP_VERSION

ENV VITE_BACKEND_URL=$VITE_BACKEND_URL \
    VITE_APP_VERSION=$VITE_APP_VERSION

RUN pnpm --filter front build

FROM nginx:alpine

COPY front/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/front/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
