# sandbox/Dockerfile
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    clang \
    clang-format \
    clang-tidy \
    cmake \
    ninja-build \
    make \
    pkg-config \
    git \
    python3 \
    python3-pip \
    python3-pytest \
    fuse3 \
    libfuse3-dev \
    fio \
    strace \
    gdb \
    lsof \
    psmisc \
    procps \
    sysstat \
    linux-tools-generic \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /workspace

WORKDIR /workspace

CMD ["sleep", "infinity"]