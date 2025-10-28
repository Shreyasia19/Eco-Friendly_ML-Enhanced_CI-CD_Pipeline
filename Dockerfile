# Dockerfile
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy only requirements file first (for caching layers)
COPY app/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY app/ .

# Set Flask environment variable
ENV FLASK_APP=app.py

# Expose port 5000 for the app
EXPOSE 5000

# Run the Flask app
CMD ["python", "app.py"]
