# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# We install globally in the container because the container IS an isolated environment.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Make start.sh executable
RUN chmod +x start.sh

# Set environment variables
ENV FLASK_ENV=production
ENV FLASK_APP=app.py
ENV PORT=5000
ENV PYTHONUNBUFFERED=1

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run the startup script
CMD ["./start.sh"]
