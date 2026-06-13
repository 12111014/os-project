# sandbox/Dockerfile
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update

RUN apt-get install -y ca-certificates --reinstall
RUN update-ca-certificates

RUN cat > /etc/apt/sources.list.d/ubuntu.sources <<'EOF'
Types: deb
URIs: https://mirror.sjtu.edu.cn/ubuntu/
Suites: noble noble-updates noble-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

# Types: deb-src
# URIs: https://mirror.sjtu.edu.cn/ubuntu/
# Suites: noble noble-updates noble-backports
# Components: main restricted universe multiverse
# Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: https://mirror.sjtu.edu.cn/ubuntu/
Suites: noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

# Types: deb-src
# URIs: https://mirror.sjtu.edu.cn/ubuntu/
# Suites: noble-security
# Components: main restricted universe multiverse
# Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

# Types: deb
# URIs: https://mirror.sjtu.edu.cn/ubuntu/
# Suites: noble-proposed
# Components: main restricted universe multiverse
# Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

# Types: deb-src
# URIs: https://mirror.sjtu.edu.cn/ubuntu/
# Suites: noble-proposed
# Components: main restricted universe multiverse
# Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF

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
    fsmark \
    strace \
    gdb \
    lsof \
    psmisc \
    procps \
    sysstat \
    linux-tools-generic \
    rustup \
    && rm -rf /var/lib/apt/lists/*

RUN RUSTUP_DIST_SERVER=https://mirror.sjtu.edu.cn/rust-static \
    RUSTUP_UPDATE_ROOT=https://mirror.sjtu.edu.cn/rust-static/rustup \
    rustup default stable

RUN mkdir -p /workspace

WORKDIR /workspace

CMD ["sleep", "infinity"]