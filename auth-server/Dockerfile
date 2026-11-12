FROM node:22-slim AS base

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 make g++ ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm config set ignore-scripts false && pnpm install

COPY . .

EXPOSE 3030
CMD ["pnpm", "start"]
