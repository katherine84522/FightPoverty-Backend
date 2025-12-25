# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for building Python packages (like bcrypt)
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev

RUN apt -y autoremove && \
    apt -y autoclean && \
    apt -y clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY ./requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container at /app
COPY . /app/

# Expose port 8000 to allow communication to the Uvicorn server
EXPOSE 3001

# Run server.py when the container launches
# Use --host 0.0.0.0 to make it accessible from outside the container
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3001"]
