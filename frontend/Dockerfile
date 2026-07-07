# 生产前端：Vite 构建 + Nginx 反代（最终阶段基于 node:alpine + apk nginx，兼容 1ms 无 nginx 镜像）
ARG NODE_IMAGE=docker.1ms.run/library/node:22-alpine
ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG ALPINE_MIRROR=mirrors.aliyun.com

FROM ${NODE_IMAGE} AS build
ARG NPM_REGISTRY
ENV NPM_REGISTRY=${NPM_REGISTRY}
WORKDIR /app
RUN npm config set registry "${NPM_REGISTRY}"
COPY package.json package-lock.json* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install
COPY . .
ARG VITE_API_BASE=/ai
ARG VITE_BASE_PATH=/ai/
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
RUN npm run build

FROM ${NODE_IMAGE} AS runtime
ARG ALPINE_MIRROR
ENV ALPINE_MIRROR=${ALPINE_MIRROR:-mirrors.aliyun.com}
RUN sed -i "s/dl-cdn.alpinelinux.org/${ALPINE_MIRROR}/g" /etc/apk/repositories && \
    apk add --no-cache nginx gettext && \
    mkdir -p /run/nginx /etc/nginx/templates && \
    rm -f /etc/nginx/http.d/default.conf
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
ENTRYPOINT ["/docker-entrypoint.sh"]
