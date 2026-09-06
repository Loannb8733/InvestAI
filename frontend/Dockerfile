# Development stage
FROM node:20-alpine AS development

WORKDIR /app

COPY package*.json ./
# `npm ci` et non `npm install` : le développement installe exactement ce que la
# CI et la production installent. `npm install` réécrit le lockfile dès qu'une
# version plus récente satisfait une plage — la dérive commence là, et elle ne
# se voit qu'au moment où un test passe ici et échoue en intégration.
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]

# Build stage
FROM node:20-alpine AS build

WORKDIR /app

ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine AS production

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
