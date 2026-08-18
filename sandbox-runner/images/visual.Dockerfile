# Heavier sandbox image for render_animation (Phase 4 Part C: visual tutoring,
# tier 2). Kept separate from the base sandbox-runner image and from the
# small matplotlib "plot" image - this one is genuinely large (LaTeX alone
# is hundreds of MB) and slow to build, so it's built once, explicitly,
# rather than on every sandbox-runner startup:
#
#   docker compose build sandbox-visual-image
#
# Scoped LaTeX install (texlive-latex-extra + texlive-fonts-recommended +
# dvisvgm), not texlive-full - texlive-full is 5GB+ of packages Manim never
# needs. build-essential/libcairo2-dev/libpango1.0-dev are there to compile
# manimpango/pycairo, not needed at runtime but simplest to leave in place
# rather than a multi-stage build for an image that's already this size.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential pkg-config \
    libcairo2-dev libpango1.0-dev \
    texlive-latex-extra texlive-fonts-recommended dvisvgm \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir manim
