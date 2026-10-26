# ActiveSite app image: dashboard + agents. Judges: `docker build -t activesite . && docker run --rm -p 8088:8088 activesite`
# Default is SAMPLE_MODE=true: every agent runs for real; the chemistry engine step replays recorded real sander output
# (labelled "cached engine output" in the UI and report). For live engine runs see README "Live engine".

# build stage: parmed has no prebuilt wheel on some platforms (e.g. linux/arm64) and needs a C++ compiler
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

# runtime stage: no compiler, same paths so the virtualenv stays valid
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/
WORKDIR /app
COPY --from=build /app /app
ENV PYTHONUNBUFFERED=1 SAMPLE_MODE=true CATALOG_OFFLINE=1
EXPOSE 8088
CMD ["uv", "run", "--no-sync", "python", "run.py", "--server"]
