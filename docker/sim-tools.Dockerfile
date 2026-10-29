ARG BASE_IMAGE=docker.io/library/ubuntu:26.04@sha256:6a06111c3b0a8600feadb270aec771dc239bf407b25625f93f44ab00e11f4d3c
ARG UV_VERSION=0.13.6
ARG UV_DIGEST=sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0
# ngspice and calculix-ccx track Debian unstable (sid) instead of the
# resolute apt pins so the image ships the newest solver releases; the
# .debs are fetched from the permanent snapshot.debian.org archive and
# verified before install. Their Depends resolve from resolute.
ARG NGSPICE_VERSION=47+ds-1
ARG NGSPICE_DEB_URL=https://snapshot.debian.org/archive/debian/20261007T000000Z/pool/main/n/ngspice/ngspice_47+ds-1_amd64.deb
ARG NGSPICE_DEB_SHA256=fe4e9efa5990cb233addd67cea8f7c919791302bd499613c5ecdb08c67a94a32
ARG CALCULIX_CCX_VERSION=2.23-1
ARG CALCULIX_CCX_DEB_URL=https://snapshot.debian.org/archive/debian/20261007T000000Z/pool/main/c/calculix-ccx/calculix-ccx_2.23-1_amd64.deb
ARG CALCULIX_CCX_DEB_SHA256=709b2d994699168f2754bd16117d51cef3241e268a7dfab185b8f78c98bd02aa

FROM ghcr.io/astral-sh/uv:${UV_VERSION}@${UV_DIGEST} AS uv

# Emscripten SDK stage: the mruby/c WASM leg runs UX .rb sources through
# the mruby/c VM under Node — the same toolchain dashboard-agent uses.
FROM emscripten/emsdk:6.0.13@sha256:fb7864e398acfda863dfcea78b8bc8adad359fa60c6a0bbeb845931de64aa68a AS emscripten

# mruby/mrubyc build stage: mrbc compiles UX .rb sources into bytecode
# linked into the mruby/c WASM VM. Same pins as firmware-agent
# (mruby 4.0.0, mrubyc master for the emscripten HAL).
FROM ${BASE_IMAGE} AS mruby

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG MRUBY_VERSION=4.0.0
ARG MRUBY_SHA256=e2ea271dbed14e9f2b33df773ae447b747dbc242ce2675022c0a57efea85a7b4
ARG MRUBYC_REF=2dec4802b09be1fc12f388d3c9267ffd9dc6c404
ARG MRUBYC_SHA256=0860de6a2b4e8adf682e14f3e0f1df7114abdb8749be23ea39cf0133f5b16b84

COPY --chmod=0755 docker/apt-sources-fallback /usr/local/bin/
RUN apt-sources-fallback \
        bison \
        build-essential \
        ca-certificates \
        curl \
        ruby \
    && rm -rf /var/lib/apt/lists/*

RUN curl --fail --location --silent --show-error \
        --retry 8 --retry-delay 20 --retry-max-time 600 --retry-all-errors \
        --output /tmp/mruby.tar.gz \
        "https://github.com/mruby/mruby/archive/refs/tags/${MRUBY_VERSION}.tar.gz" \
    && echo "${MRUBY_SHA256}  /tmp/mruby.tar.gz" | sha256sum --check \
    && mkdir -p /opt/mruby-src /opt/mruby/bin \
    && tar -xzf /tmp/mruby.tar.gz -C /opt/mruby-src --strip-components=1 \
    && curl --fail --location --silent --show-error \
        --retry 8 --retry-delay 20 --retry-max-time 600 --retry-all-errors \
        --output /tmp/mrubyc.tar.gz \
        "https://github.com/mrubyc/mrubyc/archive/${MRUBYC_REF}.tar.gz" \
    && echo "${MRUBYC_SHA256}  /tmp/mrubyc.tar.gz" | sha256sum --check \
    && mkdir -p /opt/mrubyc \
    && tar -xzf /tmp/mrubyc.tar.gz -C /opt/mrubyc --strip-components=1 \
    && rm /tmp/mruby.tar.gz /tmp/mrubyc.tar.gz

WORKDIR /opt/mruby-src
RUN ruby ./minirake -j"$(nproc)" && cp build/host/bin/mrbc /opt/mruby/bin/mrbc \
    && PATH=/opt/mruby/bin:$PATH make -C /opt/mrubyc

FROM ${BASE_IMAGE} AS sim-tools

ARG DEBIAN_FRONTEND=noninteractive
ARG IMAGE_REVISION=unknown
# Re-declare the global solver pins so the install layer can use them.
ARG NGSPICE_VERSION
ARG NGSPICE_DEB_URL
ARG NGSPICE_DEB_SHA256
ARG CALCULIX_CCX_VERSION
ARG CALCULIX_CCX_DEB_URL
ARG CALCULIX_CCX_DEB_SHA256
# npm bundled with the emsdk stage's node 24.19.0 vendors undici < 6.29.1
# (CVE-2026-109383, CVE-2026-109869, CVE-2026-87018); patched in place
# below from a sha256-verified registry tarball (npm 12.2.1 still ships
# undici 6.29.0).
ARG UNDICI_VERSION=6.29.1
# sha256 of https://registry.npmjs.org/undici/-/undici-6.29.1.tgz
ARG UNDICI_SHA256=29c4b8e0b2d86cb8795571c1959012ce057a14ecfd34858335f47c31e770a04f

# Fail the build when the left side of a verification pipe (curl|sha256sum)
# breaks instead of silently passing the right side (hadolint DL4006).
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV DEBIAN_FRONTEND=${DEBIAN_FRONTEND} \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    PATH=/opt/simulation-agent/.venv/bin:/opt/uv-python/bin:/opt/mruby/bin:/opt/emsdk:/opt/emsdk/upstream/emscripten:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONPYCACHEPREFIX=/tmp/sim-pycache \
    SIM_MRUBYC_DIR=/opt/mrubyc \
    EMSDK=/opt/emsdk \
    SIM_REQUIRED_TOOLS=ngspice,ccx

LABEL org.opencontainers.image.source="https://github.com/VibeBB/simulation-agent" \
      org.opencontainers.image.licenses="BSD-3-Clause" \
      org.opencontainers.image.revision="${IMAGE_REVISION}" \
      sim.uv.version="0.13.0" \
      sim.ngspice.version="${NGSPICE_VERSION}" \
      sim.calculix-ccx.version="${CALCULIX_CCX_VERSION}"

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=emscripten /emsdk /opt/emsdk
COPY --from=mruby /opt/mruby /opt/mruby
COPY --from=mruby /opt/mrubyc /opt/mrubyc
COPY --chmod=0755 docker/apt-sources-fallback /usr/local/bin/

# Node for the mruby/c WASM leg: the emsdk stage bundles its own node
# under /opt/emsdk/node/*/bin; link it onto PATH.
RUN ln -sf /opt/emsdk/node/*/bin/node /usr/local/bin/node \
    && ln -sf /opt/emsdk/node/*/bin/npm /usr/local/bin/npm \
    && node --version && emcc --version | head -1 && mrbc -h 2>&1 | head -1 || true

# archive.ubuntu.com's port-80 front end has repeated outages (2026-08/09/10);
# apt-sources-fallback swaps the deb822 sources to Canonical's EC2 mirror
# whenever the resolute indexes or package downloads fail to land.
RUN apt-sources-fallback \
        ca-certificates \
        curl \
        python3 \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# The pinned emsdk stage vendors vite 8.3.1 inside the emscripten
# toolchain (CVE-2026-112942, fixed in 8.3.5) and undici < 6.29.1 inside
# its bundled npm; patch both — vite via npm --prefix (same pattern as
# dashboard-agent's emsdk patches), undici via a sha256-verified tarball
# swap — and fail the build if a landed version is still vulnerable.
RUN npm --prefix /opt/emsdk/upstream/emscripten install --no-save --no-audit --no-fund vite@8.3.5 \
    && node -p "require('/opt/emsdk/upstream/emscripten/node_modules/vite/package.json').version" | grep -qx '8.3.5' \
    && for npm_root in /opt/emsdk/node/*/lib/node_modules/npm/node_modules; do \
        test -d "$npm_root/undici" \
        && curl --fail --location --silent --show-error \
            --retry 8 --retry-delay 20 --retry-max-time 600 --retry-all-errors \
            --output /tmp/undici.tgz \
            "https://registry.npmjs.org/undici/-/undici-${UNDICI_VERSION}.tgz" \
        && echo "${UNDICI_SHA256}  /tmp/undici.tgz" | sha256sum --check \
        && rm -rf "${npm_root}/undici" \
        && mkdir -p "${npm_root}/undici" \
        && tar -xzf /tmp/undici.tgz -C "${npm_root}/undici" --strip-components=1 \
        && rm -f /tmp/undici.tgz \
        && grep -F "\"version\": \"${UNDICI_VERSION}\"" "${npm_root}/undici/package.json"; \
    done

# Solvers (GPL; run as unmodified subprocesses) from the checksum-pinned
# Debian sid .debs: the sid pins reach ngspice 47 and CalculiX 2.23 while
# the resolute apt channel is at ngspice 45.2 / calculix-ccx 2.21.
RUN curl --fail --location --silent --show-error \
        --retry 8 --retry-delay 20 --retry-max-time 600 --retry-all-errors \
        --output /tmp/ngspice.deb \
        "${NGSPICE_DEB_URL}" \
    && curl --fail --location --silent --show-error \
        --retry 8 --retry-delay 20 --retry-max-time 600 --retry-all-errors \
        --output /tmp/calculix-ccx.deb \
        "${CALCULIX_CCX_DEB_URL}" \
    && echo "${NGSPICE_DEB_SHA256}  /tmp/ngspice.deb" | sha256sum --check \
    && echo "${CALCULIX_CCX_DEB_SHA256}  /tmp/calculix-ccx.deb" | sha256sum --check \
    && apt-sources-fallback /tmp/ngspice.deb /tmp/calculix-ccx.deb \
    # Apply every Debian/Ubuntu security fix published after the pinned
    # base digest so the publish Trivy gate cannot trip on fixable
    # findings (apt always pulls the latest published fix).
    && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update \
    && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* /tmp/ngspice.deb /tmp/calculix-ccx.deb \
    && mkdir -p /usr/share/doc/solvers \
    && printf '%s\n' \
        "source=Debian unstable pool via snapshot.debian.org" \
        "ngspice=${NGSPICE_VERSION} sha256=${NGSPICE_DEB_SHA256}" \
        "calculix-ccx=${CALCULIX_CCX_VERSION} sha256=${CALCULIX_CCX_DEB_SHA256}" \
        > /usr/share/doc/solvers/SOURCE \
    && (ngspice --version || true) 2>&1 | head -1 \
    && (ccx -v || true) 2>&1 | head -2

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
    && uv sync --frozen --no-dev --no-group sdk-check --python 3.12 \
    && rm -rf /opt/uv-python/bin/pip* \
              /opt/uv-python/cpython-*/bin/pip* \
              /opt/uv-python/cpython-*/lib/python3.*/site-packages/pip \
              /opt/uv-python/cpython-*/lib/python3.*/site-packages/pip-*.dist-info \
              /opt/uv-python/cpython-*/lib/python3.*/ensurepip \
              /root/.cache/uv \
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
ARG OPENEMS_COMMIT=38da98d592f6f9b772cf984a411470e0feb9a114

ENV DEBIAN_FRONTEND=${DEBIAN_FRONTEND}

COPY --chmod=0755 docker/apt-sources-fallback /usr/local/bin/

RUN apt-sources-fallback \
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

RUN apt-sources-fallback \
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
ARG KICAD_RFSIM_COMMIT=5143601169b81980f046620fad4b1c74815c586a

USER root

RUN apt-sources-fallback \
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
