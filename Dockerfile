# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable for production
ENV FLASK_ENV=production
ENV FLASK_APP=app.py

# Run app.py when the container launches using gunicorn (or keep python app.py if using gevent/socketio directly)
# Since you are using socketio with gevent, it's best to run it the same way you do locally
CMD ["python", "app.py"]
