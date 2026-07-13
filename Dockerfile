FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy the compiled docs folder and local_server.py into the container
COPY docs/ /app/docs/
COPY local_server.py /app/

# Create live_data folder and ensure write permissions for the server
RUN mkdir -p /app/live_data && chmod 777 /app/live_data

# Expose port 7860 (Hugging Face default)
EXPOSE 7860

# Run the python server
CMD ["python", "local_server.py"]
