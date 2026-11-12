FROM node:22-slim AS base

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 make g++ ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@9 --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install

COPY . .

EXPOSE 3030
CMD ["sh", "-c", "pnpm db:migrate && pnpm start"]
