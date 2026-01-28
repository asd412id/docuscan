# ===========================================
# DocuScan Frontend - Production Dockerfile
# Multi-stage build with dynamic nginx config
# ===========================================

# Build arguments
ARG NODE_VERSION=20
ARG VITE_API_URL=

# ===========================================
# Stage 1: Dependencies
# ===========================================
FROM node:${NODE_VERSION}-alpine as deps

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production=false

# ===========================================
# Stage 2: Builder
# ===========================================
FROM node:${NODE_VERSION}-alpine as builder

ARG VITE_API_URL

WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy source code
COPY . .

# Set build-time environment variables
ENV VITE_API_URL=${VITE_API_URL}

# Build application (skip tsc type-check, Vite handles TS transpilation)
# Type-checking should be done in CI/CD pipeline, not during container build
RUN npm exec vite build

# ===========================================
# Stage 3: Production
# ===========================================
FROM nginx:alpine as production

# Labels
LABEL maintainer="DocuScan Team"
LABEL description="DocuScan Frontend SPA"
LABEL version="1.0.0"

# Install envsubst (part of gettext) and curl for healthcheck
RUN apk add --no-cache gettext curl

# Create non-root user
RUN addgroup -g 1000 -S appgroup && \
    adduser -u 1000 -S appuser -G appgroup

# Copy built files
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx template
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Set default environment variables
ENV BACKEND_HOST=backend \
    BACKEND_PORT=8000 \
    CLIENT_MAX_BODY_SIZE=20m

# Create nginx cache directories with proper permissions
RUN mkdir -p /var/cache/nginx /var/run && \
    chown -R appuser:appgroup /var/cache/nginx /var/run /usr/share/nginx/html

# Note: nginx needs to run as root to bind to port 80
# For rootless, would need to use port 8080

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:80 || exit 1

# Use custom entrypoint
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
