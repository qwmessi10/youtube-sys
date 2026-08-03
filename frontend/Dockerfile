FROM node:22-alpine AS build
WORKDIR /app
COPY package.json .
COPY package-lock.json .
RUN npm ci --fetch-retries=5 --fetch-retry-mintimeout=2000 --fetch-retry-maxtimeout=30000
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
