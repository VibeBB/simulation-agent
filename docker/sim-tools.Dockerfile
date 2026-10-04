ARG BASE_IMAGE=docker.io/library/ubuntu:26.04@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78
ARG UV_VERSION=0.12.23
ARG UV_DIGEST=sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21

FROM ghcr.io/astral-sh/uv:${UV_VERSION}@${UV_DIGEST} AS uv

FROM ${BASE_IMAGE} AS sim-tools

ARG DEBIAN_FRONTEND=noninteractive
ARG IMAGE_REVISION=unknown

ENV DEBIAN_FRONTEND=${DEBIAN_FRONTEND} \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    PATH=/opt/simulation-agent/.venv/bin:/opt/uv-python/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONPYCACHEPREFIX=/tmp/sim-pycache \
    SIM_REQUIRED_TOOLS=ngspice,ccx

LABEL org.opencontainers.image.source="https://github.com/VibeBB/simulation-agent" \
      org.opencontainers.image.licenses="BSD-3-Clause" \
      org.opencontainers.image.revision="${IMAGE_REVISION}" \
      sim.uv.version="0.12.23"

COPY --from=uv /uv /uvx /usr/local/bin/

RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install --no-install-recommends -y \
        ca-certificates \
        calculix-ccx \
        ngspice \
        python3 \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/simulation-agent
COPY pyproject.toml uv.lock README.md LICENSE /opt/simulation-agent/
COPY src /opt/simulation-agent/src
COPY plugins/sim /opt/simulation-agent/plugins/sim
COPY examples /opt/simulation-agent/examples

# The uv-managed CPython bundles pip with vendored copies of urllib3,
# msgpack, and setuptools that nothing in the image invokes — dependencies
# install via uv and the entrypoint venv is pip-less — so strip the payload
# instead of shipping unused vulnerable vendored packages.
RUN uv python install 3.14 \
    && rm -rf /opt/uv-python/bin/pip* \
              /opt/uv-python/cpython-*/bin/pip* \
              /opt/uv-python/cpython-*/lib/python3.*/site-packages/pip \
              /opt/uv-python/cpython-*/lib/python3.*/site-packages/pip-*.dist-info \
              /opt/uv-python/cpython-*/lib/python3.*/ensurepip \
              /root/.cache/uv \
    && uv sync --frozen --no-dev --no-group sdk-check --python 3.12 \
    && SIM_REQUIRED_TOOLS=ngspice,ccx python -m sim doctor --strict

# Tighten the login.defs umask to 027 (Lynis AUTH-9328): the image has no
# interactive users, so files created at runtime stay group-readable only.
RUN printf 'UMASK 027\n' >> /etc/login.defs

RUN if ! getent group sim >/dev/null; then groupadd --system sim; fi \
    && useradd --system --uid 10001 --gid sim --create-home --shell /usr/sbin/nologin sim \
    && chown -R sim:sim /opt/simulation-agent

WORKDIR /workspace
USER sim
ENTRYPOINT ["python", "-m", "sim"]

FROM ${BASE_IMAGE} AS openems-build

ARG DEBIAN_FRONTEND=noninteractive
ARG OPENEMS_COMMIT=81f32e03d514f270e679b63e8861d24eaa03a7e2

ENV DEBIAN_FRONTEND=${DEBIAN_FRONTEND}

RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install --no-install-recommends -y \
        build-essential \
        ca-certificates \
        cmake \
        git \
        libcgal-dev \
        libboost-all-dev \
        libfftw3-dev \
        libhdf5-dev \
        libopenmpi-dev \
        libreadline-dev \
        libtinyxml-dev \
        libvtk9-dev \
        libxml2-dev \
        python3-dev \
        python3-numpy \
        python3-h5py \
        swig \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/thliebig/openEMS-Project.git /tmp/openEMS-Project \
    && git -C /tmp/openEMS-Project checkout --detach "${OPENEMS_COMMIT}" \
    && git -C /tmp/openEMS-Project submodule update --init --recursive \
    && cmake -S /tmp/openEMS-Project -B /tmp/openEMS-Project/build \
        -DBUILD_APPCSXCAD=NO \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DWITH_MPI=OFF \
    && cmake --build /tmp/openEMS-Project/build --parallel 2 \
    && cmake --install /tmp/openEMS-Project/build

RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install --no-install-recommends -y \
        cython3 \
        python3-pip \
        python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

RUN CSXCAD_INSTALL_PATH=/usr/local \
    OPENEMS_INSTALL_PATH=/usr/local \
    CSXCAD_NOSCM=1 \
    OPENEMS_NOSCM=1 \
    python3 -m pip install --break-system-packages --no-build-isolation --no-deps \
        --no-cache-dir /tmp/openEMS-Project/CSXCAD/python \
    && CSXCAD_INSTALL_PATH=/usr/local \
        OPENEMS_INSTALL_PATH=/usr/local \
        CSXCAD_NOSCM=1 \
        OPENEMS_NOSCM=1 \
        python3 -m pip install --break-system-packages --no-build-isolation --no-deps \
            --no-cache-dir /tmp/openEMS-Project/openEMS/python

FROM sim-tools AS sim-tools-em

ARG DEBIAN_FRONTEND=noninteractive
ARG KICAD_RFSIM_COMMIT=efa0ea9bd34b13f7819c6f2d4c02e78d34b116c3

USER root

RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install --no-install-recommends -y \
        git \
        libboost-program-options1.90.0 \
        libboost-thread1.90.0 \
        libhdf5-310 \
        libtinyxml2.6.2v5 \
        libvtk9.5 \
        python3-numpy \
        python3-h5py \
    && rm -rf /var/lib/apt/lists/*

COPY --from=openems-build /usr/local /usr/local

RUN ldconfig

RUN git init /opt/kicad-rfsim \
    && git -C /opt/kicad-rfsim remote add origin https://github.com/NBalciunas/kicad-rfsim.git \
    && git -C /opt/kicad-rfsim fetch --depth=1 origin "${KICAD_RFSIM_COMMIT}" \
    && git -C /opt/kicad-rfsim checkout --detach FETCH_HEAD

ENV SIM_REQUIRED_TOOLS=ngspice,ccx,openems,kicad_rfsim \
    SIM_OPENEMS_PYTHON=/usr/bin/python3 \
    SIM_RFSIM_RUNNER=/opt/kicad-rfsim/plugins/runner.py

RUN /usr/bin/python3 -c "import CSXCAD, openEMS, numpy, h5py" \
    && python -m sim doctor --strict

USER sim
