import json
import signal
import grpc
import iec61850
import os
import taipower_ancillary_pb2
import taipower_ancillary_pb2_grpc

from concurrent import futures
from model_loader import (UPDATERS,
                          load_model,
                          load_logical_device,
                          find_data_attribute,
                          get_data_objects,)
from proto_servicer import AncillaryInputsServicer


def read_mms_value(mms_value):
    mms_value_type = iec61850.MmsValue_getTypeString(mms_value)
    if mms_value_type == 'boolean':
        return iec61850.MmsValue_getBoolean(mms_value)
    elif mms_value_type == 'integer':
        return iec61850.MmsValue_toInt32(mms_value)
    elif mms_value_type == 'float':
        return iec61850.MmsValue_toFloat(mms_value)
    elif mms_value_type == 'structure':
        array_size = iec61850.MmsValue_getArraySize(mms_value)
        return [read_mms_value(iec61850.MmsValue_getElement(mms_value, i)) for i in range(array_size)]
    else:
        print(f'Unsupported MMS value type {mms_value_type}')
        return None


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
        print('Start MMS server at port {}'.format(self._iec_port))
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
        print('Stop MMS server')
        # stop MMS server - close TCP server socket and all client sockets
        iec61850.IedServer_stop(self._ied_server)

        # Cleanup - free all resources
        iec61850.IedServer_destroy(self._ied_server)

    def _init_grpc_server(self):
        print('Start gRPC server at port {}'.format(self._grpc_port))
        self._outward_grpc_channel = grpc.insecure_channel(self._ancillary_backend_server_address)
        self._outward_stub = taipower_ancillary_pb2_grpc.AncillaryOutputsStub(self._outward_grpc_channel)

        self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        taipower_ancillary_pb2_grpc.add_AncillaryInputsServicer_to_server(
            AncillaryInputsServicer(self), self._grpc_server)
        self._grpc_server.add_insecure_port('[::]:{}'.format(self._grpc_port))

    def handle_control_cmd(self, action, parameter, mms_value, test):
        # FIXME: the control handler is blocking (process one control command at a time)
        #
        # Since we use gRPC to communicate with the ancillary backend server,
        # the processing time may be too long for some control commands.
        #
        # For example, when 啟動指令 is sent, 執行容量 and other related commands will be sent at the same time.
        #
        # Possible solutions:
        # - Update the code to use ControlHandlerForPython
        do_path = parameter
        print(f'Handle control command for DO: {do_path}')
        try:
            # FIXME: type of orIdentSize should be int*, so 1024 is not correct
            # print(f'Originator Identifier: {iec61850.ControlAction_getOrIdent(action, 1024)}')
            print(f'Originator Category: {iec61850.ControlAction_getOrCat(action)}')
            print(f'Control Number: {iec61850.ControlAction_getCtlNum(action)}')
            print(f'Control Time: {iec61850.ControlAction_getControlTime(action)}')
        except Exception as e:
            print(f'Exception: {e}')

        value = read_mms_value(mms_value)
        print('Control point {} is set to {}'.format(do_path, value))
        response = self._outward_stub.update_point_values(
            taipower_ancillary_pb2.UpdatePointValuesRequest(values=json.dumps({do_path: value})))
        return response
        
        

    def _bind_controll_handler(self):
        print('Bind control handler')
        for do_info in get_data_objects(self._model):
            if not do_info['controllable']:
                continue

            context = iec61850.transformControlHandlerContext((self, self.handle_control_cmd, do_info['path']))
            if not context:
                break

            iec61850.IedServer_setControlHandler(
                self._ied_server, do_info['inst'], iec61850.ControlHandlerProxy, context)

    def start(self):
        print('Initialize proxy server')
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
        print('Run proxy server')
        self._grpc_server.start()
        self._grpc_server.wait_for_termination()
        self._running = False

    def stop(self):
        print('Stop proxy server')
        self._destroy_ied_server()

        # destroy dynamic data model
        iec61850.IedModel_destroy(self._model['inst'])

    def restart_ied_server(self):
        print('Restart IED server')
        self._destroy_ied_server()
        # Must reload model as it will also be destroyed in _destroy_ied_server
        self._model = load_model(self._model_config)
        self._init_ied_server()

    def update_value(self, values):
        print('Update value: {}'.format(values))
        iec61850.IedServer_lockDataModel(self._ied_server)

        for da_path, value in values.items():
            da_info = find_data_attribute(self._model, da_path)
            updater = UPDATERS[da_info['data_type']]
            updater(self._ied_server, da_info['inst'], value)

        iec61850.IedServer_unlockDataModel(self._ied_server)

    def _save_model_config(self):
        print('Save model config to {}'.format(self._config_path))
        with open(self._config_path, 'w') as f:
            json.dump(self._model_config, f, indent=2)

    def add_logical_devices(self, _devices):
        print('Add logical devices: {}'.format(_devices))
        devices = list(filter(lambda d: d['name'] not in self._model['logical_devices'], _devices))
        self._model_config['logical_devices'].extend(devices)
        for device in devices:
            load_logical_device(self._model, device)
        self._save_model_config()

    def reset_logical_devices(self, devices):
        print('Reset logical devices')
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
