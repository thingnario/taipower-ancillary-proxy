FROM ubuntu:18.04
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
        python3-pip

# Do remeber to upgrade pip or grpcio will take forever
ADD ./server/requirements.txt /requirements.txt
RUN python3 -m pip install --upgrade pip
RUN python3 -m pip install -r requirements.txt

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
ADD ./protos /protos
ADD ./server/*.py /
ADD ./server/proto.sh /
ADD ./config/*.json /config/
COPY ./server/entrypoint.sh /entrypoint.sh
RUN chmod +x /proto.sh
RUN /proto.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT [ "/entrypoint.sh" ]