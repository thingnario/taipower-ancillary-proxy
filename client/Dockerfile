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
        gdb \
        vim

ADD ./libiec61850 /libiec61850
# Replace CMakeLists.txt with our customized one, for supporting Python
ADD ./patch /patch
RUN find patch -name "*.patch" -type f -exec patch -p1 -i {} \;
RUN mkdir build
WORKDIR /build
RUN cmake ../libiec61850/
RUN make
WORKDIR /
RUN cp build/pyiec61850/_iec61850.so /_iec61850.so
RUN cp build/pyiec61850/iec61850.py /iec61850.py
ADD ./client/*.py /
ADD ./config/*.json /config/
COPY ./client/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT [ "/entrypoint.sh" ]