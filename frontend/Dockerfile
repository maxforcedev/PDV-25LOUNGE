FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci


FROM deps AS development

ENV NEXT_TELEMETRY_DISABLED=1

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]


FROM deps AS builder

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_TELEMETRY_DISABLED=1

COPY . .

RUN node -e "const value = process.env.NEXT_PUBLIC_API_URL; if (!value) throw new Error('NEXT_PUBLIC_API_URL is required'); const host = new URL(value).hostname; if (['localhost', '127.0.0.1', '::1'].includes(host)) throw new Error('NEXT_PUBLIC_API_URL must not use loopback for a production image')" \
    && npm run build


FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS production

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

USER node

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/login').then(response => process.exit(response.status < 500 ? 0 : 1)).catch(() => process.exit(1))"]

CMD ["node", "server.js"]
