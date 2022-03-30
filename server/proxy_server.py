from concurrent import futures
from distutils.command.config import config
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

    @staticmethod
    def _load_logical_devices(devices):
        for device in devices:
            yield {
                'name': device.name,
                'logical_nodes': json.loads(device.logical_nodes),
            }

    def update_point_values(self, request, context):
        self._servant.update_value(json.loads(request.values))
        return taipower_ancillary_pb2.Response(success=True)

    def add_logical_devices(self, request, context):
        devices = list(AncillaryInputsServicer._load_logical_devices(request.devices))
        self._servant.add_logical_devices(devices)
        return taipower_ancillary_pb2.Response(success=True)

    def reset_logical_devices(self, request, context):
        devices = list(AncillaryInputsServicer._load_logical_devices(request.devices))
        self._servant.reset_logical_devices(devices)
        return taipower_ancillary_pb2.Response(success=True)

    def restart_ied_server(self, request, context):
        self._servant.restart_ied_server()
        return taipower_ancillary_pb2.Response(success=True)


class ProxyServer():
    def __init__(self, config_path):
        self._running = False
        self._iec_port = 102
        self._grpc_port = 61850

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
        self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        taipower_ancillary_pb2_grpc.add_AncillaryInputsServicer_to_server(
            AncillaryInputsServicer(self), self._grpc_server)
        self._grpc_server.add_insecure_port('[::]:{}'.format(self._grpc_port))

    def handle_control_cmd(self, action, parameter, value, test):
        ctl_num = iec61850.ControlAction_getCtlNum(action)
        print('handle control command: {}, {}, {}, {}'.format(
            ctl_num, parameter, iec61850.MmsValue_getBoolean(value), test))

    def _bind_controll_handler(self):
        def get_data_objects(model_info):
            for ld_name, ld_info in model_info['logical_devices'].items():
                for ln_name, ln_info in ld_info['logical_nodes'].items():
                    for do_name, do_info in ln_info['data_objects'].items():
                        do_info['path'] = '{}.{}.{}'.format(ld_name, ln_name, do_name)
                        yield do_info

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
        self._init_ied_server()

    def update_value(self, values):
        iec61850.IedServer_lockDataModel(self._ied_server)

        for key, value in values.items():
            ld, ln, do, da = key.split('.', 3)
            da_info = self._model[ld][ln][do][da]
            updater = UPDATERS[da_info['data_type']]
            updater(self._ied_server, da_info['inst'], value)

        iec61850.IedServer_unlockDataModel(self._ied_server)

    def _save_model_config(self):
        with open(self._config_path, 'w') as f:
            json.dump(self._model_config, f)

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
    server = ProxyServer('config/points.json')
    if not server.start():
        exit(1)

    server.run()
    server.stop()
    return 0


if __name__ == '__main__':
    main()
