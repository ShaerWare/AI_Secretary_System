# Self-hosted WhatsApp provider (Baileys multi-device)
FROM node:20-alpine

WORKDIR /app

# Install dependencies first so a source-only change doesn't re-run npm ci
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev || npm install --omit=dev

COPY src/ ./src/

# Linked-device credentials live here — mount a volume, or every restart
# demands a fresh QR scan.
ENV WHATSAPP_BRIDGE_DATA=/data
ENV WHATSAPP_BRIDGE_HOST=0.0.0.0
ENV WHATSAPP_BRIDGE_PORT=8005
RUN mkdir -p /data

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.WHATSAPP_BRIDGE_PORT||8005)+'/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "src/index.js"]
