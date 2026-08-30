FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_BACKOFFICE_URL
ARG APP_VERSION=development
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
ARG ENVIRONMENT=development
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_BACKOFFICE_URL=${NEXT_PUBLIC_BACKOFFICE_URL} \
    NEXT_PUBLIC_APP_VERSION=${APP_VERSION} \
    NEXT_PUBLIC_GIT_SHA=${GIT_SHA} \
    NEXT_PUBLIC_BUILD_DATE=${BUILD_DATE} \
    NEXT_PUBLIC_ENVIRONMENT=${ENVIRONMENT} \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN node -e "const value = process.env.NEXT_PUBLIC_API_URL; if (!value) throw new Error('NEXT_PUBLIC_API_URL is required'); const url = new URL(value); if (url.protocol !== 'https:') throw new Error('NEXT_PUBLIC_API_URL must use HTTPS for a production image'); if (['localhost', '127.0.0.1', '::1'].includes(url.hostname)) throw new Error('NEXT_PUBLIC_API_URL must not use loopback for a production image')" \
    && npm run build

FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3100 \
    HOSTNAME=0.0.0.0
RUN addgroup --system --gid 1001 core && adduser --system --uid 1001 --ingroup core operator
COPY --from=builder --chown=operator:core /app/public ./public
COPY --from=builder --chown=operator:core /app/.next/standalone ./
COPY --from=builder --chown=operator:core /app/.next/static ./.next/static
USER operator
EXPOSE 3100
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3100/login', {signal: AbortSignal.timeout(4000)}).then(response => process.exit(response.status === 200 ? 0 : 1)).catch(() => process.exit(1))"]
CMD ["node", "server.js"]
