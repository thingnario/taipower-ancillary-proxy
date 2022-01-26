from concurrent import futures
import json
import signal
import grpc
import iec61850
import taipower_ancillary_pb2
import taipower_ancillary_pb2_grpc
from model_loader import (UPDATERS,
                          load_model,
                          load_logical_device)


class AncillaryInputsServicer(taipower_ancillary_pb2_grpc.AncillaryInputsServicer):
    def __init__(self, servant):
        self._servant = servant

    def update_point_values(self, request, context):
        self._servant.update_value(json.loads(request.values))
        return taipower_ancillary_pb2.Response(success=True)

    def add_logical_devices(self, request, context):
        self._servant.add_logical_devices(request.devices)
        return taipower_ancillary_pb2.Response(success=True)

    def restart_ied_server(self, request, context):
        self._servant.restart_ied_server()
        return taipower_ancillary_pb2.Response(success=True)


class ProxyServer():
    def __init__(self):
        self._running = False
        self._iec_port = 102
        self._grpc_port = 61850

    def _init_ied_server(self, model):
        self._ied_server = iec61850.IedServer_create(model['inst'])

        # MMS server will be instructed to start listening to client connections.
        iec61850.IedServer_start(self._ied_server, self._iec_port)

        if not iec61850.IedServer_isRunning(self._ied_server):
            print("Starting server failed! Exit.\n")
            iec61850.IedServer_destroy(self._ied_server)
            return False

        return True

    def _destroy_ied_server(self):
        # stop MMS server - close TCP server socket and all client sockets
        iec61850.IedServer_stop(self._ied_server)

        # Cleanup - free all resources
        iec61850.IedServer_destroy(self._ied_server)

    def _init_grpc_server(self):
        self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        taipower_ancillary_pb2_grpc.add_AncillaryInputsServicer_to_server(
            AncillaryInputsServicer(self), self._grpc_server)
        self._grpc_server.add_insecure_port('[::]:{}'.format(self._grpc_port))

    def start(self, model):
        self._model = model
        self._running = self._init_ied_server(model)
        if not self._running:
            return False

        self._init_grpc_server()

        def sigint_handler(sig, frame):
            self._running = False

        signal.signal(signal.SIGINT, sigint_handler)
        return True

    def run(self):
        self._grpc_server.start()
        self._grpc_server.wait_for_termination()
        self._running = False

    def stop(self):
        self._destroy_ied_server()

        # destroy dynamic data model
        iec61850.IedModel_destroy(self._model['inst'])

    def restart_ied_server(self):
        self._destroy_ied_server()
        self._init_ied_server(self._model)

    def update_value(self, values):
        iec61850.IedServer_lockDataModel(self._ied_server)

        for key, value in values.items():
            ld, ln, do, da = key.split('.', 3)
            da_info = self._model[ld][ln][do][da]
            updater = UPDATERS[da_info['data_type']]
            updater(self._ied_server, da_info['inst'], value)

        iec61850.IedServer_unlockDataModel(self._ied_server)

    def add_logical_devices(self, devices):
        for device in devices:
            if device.name in self._model:
                print('Skip existing logical device {}'.format(device.name))
                continue

            config = {
                'name': device.name,
                'logical_nodes': json.loads(device.logical_nodes),
            }
            load_logical_device(self._model, config)


def main():
    '''
       Setup data model
    '''
    model = load_model('config/points.json')

    '''
       run server
    '''
    server = ProxyServer()
    if not server.start(model):
        exit(1)

    server.run()
    server.stop()
    return 0


if __name__ == '__main__':
    main()
