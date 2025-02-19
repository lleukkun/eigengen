FROM ubuntu:24.04

WORKDIR /usr/src/app

RUN apt-get update -y && apt-get dist-upgrade -y && apt-get install -y curl git
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"
COPY . .
RUN uv venv
RUN uv pip install -e .

ENTRYPOINT ["/usr/src/app/.venv/bin/egg"]
