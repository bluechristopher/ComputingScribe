FROM python:3.11-slim

# Prevent interactive prompts during apt-get
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"
ENV PORT=8501

# Install every LaTeX collection required by the bundled templates. Do not rely on
# on-demand package installation: Cloud Run builds must be deterministic.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-pictures \
    lmodern \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency definition and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Run Streamlit on container startup with dynamic port support for Cloud Run
CMD streamlit run frontend/app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.enableCORS=false --server.enableXsrfProtection=false
