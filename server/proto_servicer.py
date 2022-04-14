import json
import taipower_ancillary_pb2
import taipower_ancillary_pb2_grpc


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
