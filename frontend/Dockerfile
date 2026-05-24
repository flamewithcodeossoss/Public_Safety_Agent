FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY package.json ./
RUN npm install

# Copy source
COPY . .

# Expose port
EXPOSE 5173

# Run dev server (accessible from Docker network)
CMD ["npm", "run", "dev"]
