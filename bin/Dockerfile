FROM ubuntu:18.04
ARG DEBIAN_FRONTEND=noninteractive
RUN apt update && \
    apt --yes upgrade && \
    apt --yes install \
        autoconf \
        automake \
        build-essential \
        cmake \
        swig \
        python3 \
        python3-dev \
        python3-pip \
        gdb

# Build libiec61850
ADD libiec61850 /libiec61850
ADD patch /patch
RUN find patch -name "*.patch" -type f -exec patch -p1 -i {} \;
RUN mkdir build
WORKDIR /build
RUN cmake ../libiec61850/
RUN make

# Install pyiec61850
WORKDIR /root
RUN cp /build/pyiec61850/_iec61850.so _iec61850.so
RUN cp /build/pyiec61850/iec61850.py iec61850.py

# Install requirements
ADD bin/requirements.txt .
RUN python3 -m pip install --upgrade pip
RUN python3 -m pip install -r requirements.txt

# Add entrypoint
ENV PYTHONIOENCODING utf-8
ADD bin/connection_test.py .
ENTRYPOINT [ "python3", "/root/connection_test.py" ]
