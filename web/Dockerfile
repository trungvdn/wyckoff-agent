# Giao diện Next.js cho server. Xem docs/deploy.md.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN mkdir -p public

# Rewrite /api/* trong next.config.ts và mã mặc định được chốt lúc build
ARG WYCKOFF_API_URL=http://api:8000
ARG NEXT_PUBLIC_DEFAULT_SYMBOL=HPG
ENV WYCKOFF_API_URL=$WYCKOFF_API_URL \
    NEXT_PUBLIC_DEFAULT_SYMBOL=$NEXT_PUBLIC_DEFAULT_SYMBOL \
    NEXT_OUTPUT_STANDALONE=1 \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:3000/icon.svg').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
