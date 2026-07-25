# syntax=docker/dockerfile:1
#
# Build context MUST be the repository root, e.g.:
#   docker build -f apps/frontend/Dockerfile -t aiios/frontend .
#
# This is required because the frontend is a member of the root pnpm
# workspace (see /pnpm-workspace.yaml) and its lockfile is resolved against
# the whole workspace, per docs/004_Master_Repository_Structure.md.txt.

FROM node:22-slim AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

FROM base AS deps
WORKDIR /repo
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY apps/frontend/package.json apps/frontend/package.json
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

FROM base AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules /repo/node_modules
COPY --from=deps /repo/apps/frontend/node_modules /repo/apps/frontend/node_modules
COPY . .
WORKDIR /repo/apps/frontend
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN groupadd --system aiios && useradd --system --gid aiios aiios

COPY --from=builder /repo/apps/frontend/public ./public
COPY --from=builder --chown=aiios:aiios /repo/apps/frontend/.next/standalone ./
COPY --from=builder --chown=aiios:aiios /repo/apps/frontend/.next/static ./apps/frontend/.next/static

USER aiios
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
    CMD node -e "fetch('http://localhost:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "apps/frontend/server.js"]
