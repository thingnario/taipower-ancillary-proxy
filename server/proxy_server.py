import json
import signal
import grpc
import iec61850
import os
import taipower_ancillary_pb2
import taipower_ancillary_pb2_grpc

from concurrent import futures
from distutils.command.config import config
from model_loader import (UPDATERS,
                          MMS_LOADERS,
                          load_model,
                          load_logical_device,
                          find_data_attribute,
                          get_data_objects,)
from proto_servicer import AncillaryInputsServicer


class ProxyServer():
    def __init__(self, config_path, ancillary_backend_server_address):
        self._running = False
        self._iec_port = 102
        self._grpc_port = 61850
        self._ancillary_backend_server_address = ancillary_backend_server_address

        self._config_path = config_path
        with open(config_path) as f:
            self._model_config = json.load(f)
        self._model = load_model(self._model_config)

    def _init_ied_server(self):
        self._ied_server = iec61850.IedServer_create(self._model['inst'])
        self._bind_controll_handler()

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
        self._outward_grpc_channel = grpc.insecure_channel(self._ancillary_backend_server_address)
        self._outward_stub = taipower_ancillary_pb2_grpc.AncillaryOutputsStub(self._outward_grpc_channel)

        self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        taipower_ancillary_pb2_grpc.add_AncillaryInputsServicer_to_server(
            AncillaryInputsServicer(self), self._grpc_server)
        self._grpc_server.add_insecure_port('[::]:{}'.format(self._grpc_port))

    def handle_control_cmd(self, action, parameter, mms_value, test):
        do_path = parameter
        da_info = find_data_attribute(self._model, do_path + '.Oper.ctlVal') or\
                  find_data_attribute(self._model, do_path + '.Oper.ctlVal.i')
        if not da_info:
            print('No corresponding control point for {}, skip the control command'.format(do_path))
            return

        loader = MMS_LOADERS[da_info['data_type']]
        value = loader(mms_value)
        response = self._outward_stub.update_point_values(
            taipower_ancillary_pb2.UpdatePointValuesRequest(values=json.dumps({do_path: value})))
        return response
        
        

    def _bind_controll_handler(self):
        for do_info in get_data_objects(self._model):
            if not do_info['controllable']:
                continue

            context = iec61850.transformControlHandlerContext((self, self.handle_control_cmd, do_info['path']))
            if not context:
                break

            iec61850.IedServer_setControlHandler(
                self._ied_server, do_info['inst'], iec61850.ControlHandlerProxy, context)

    def start(self):
        self._running = self._init_ied_server()
        if not self._running:
            return False

        self._init_grpc_server()

        def sigint_handler(sig, frame):
            self.stop()
            self._grpc_server.stop(None)
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
        # Must reload model as it will also be destroyed in _destroy_ied_server
        self._model = load_model(self._model_config)
        self._init_ied_server()

    def update_value(self, values):
        iec61850.IedServer_lockDataModel(self._ied_server)

        for da_path, value in values.items():
            da_info = find_data_attribute(self._model, da_path)
            updater = UPDATERS[da_info['data_type']]
            updater(self._ied_server, da_info['inst'], value)

        iec61850.IedServer_unlockDataModel(self._ied_server)

    def _save_model_config(self):
        with open(self._config_path, 'w') as f:
            json.dump(self._model_config, f, indent=2)

    def add_logical_devices(self, _devices):
        devices = list(filter(lambda d: d['name'] not in self._model['logical_devices'], _devices))
        self._model_config['logical_devices'].extend(devices)
        for device in devices:
            load_logical_device(self._model, device)
        self._save_model_config()

    def reset_logical_devices(self, devices):
        self._model_config['logical_devices'] = devices
        model = load_model(self._model_config)

        self._destroy_ied_server()
        self._model = model
        self._init_ied_server()
        self._save_model_config()


def main():
    ancillary_backend_server_address = os.environ.get('ANCILLARY_BACKEND_SERVER_ADDRESS', 'localhost:61852')
    print('ancillary_backend_server_address: {}'.format(ancillary_backend_server_address))
    server = ProxyServer('config/points.json', ancillary_backend_server_address)
    if not server.start():
        exit(1)

    server.run()
    server.stop()
    return 0


if __name__ == '__main__':
    main()
