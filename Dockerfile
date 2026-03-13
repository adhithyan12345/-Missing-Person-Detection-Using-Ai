FROM python:3.10-slim

# Set up a new user named "user" with user ID 1000
RUN useradd -m -u 1000 user

# Switch to the "user" user
USER user

# Set home to the user's home directory
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set the working directory to the user's home directory
WORKDIR $HOME/app

# Copy the current directory contents into the container at $HOME/app setting the owner to the user
COPY --chown=user . $HOME/app

# Install system dependencies if any are needed for basic operations (though we use headless OpenCV)
# If using root, we would apt-get install here, but we are user user. 
# python:3.10-slim usually has what we need for headless OpenCV.
# Switch to root temporarily just in case we need anything, but typically we don't for headless.

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p static/uploads

# Expose the default port for Hugging Face Spaces
EXPOSE 7860

# Run the application using Gunicorn (binding to 0.0.0.0:7860)
CMD ["gunicorn", "-b", "0.0.0.0:7860", "-w", "2", "--timeout", "120", "app:app"]
