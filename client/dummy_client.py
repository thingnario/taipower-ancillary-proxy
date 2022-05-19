import argparse
import time
import iec61850
from model_loader import load_model, get_mms_loader


class DummyClient():
    def __init__(self, host, port=102):
        self._host = host
        self._port = port
        self._control_blocks = None
        self._is_under_capacity = False
        self._service_status_count = 0

    def read_point(self, point, conn):
        loader = get_mms_loader(point['type'])
        if loader is None:
            print('Cannot find corresponding converter for {}'.format(
                point['type']))
            return

        res = iec61850.IedConnection_readObject_no_gil(
            conn, point['path'], point['fc'])
        if res is None or isinstance(res, int):
            print('Read {} failed, error: {}'.format(point['path'], res))
            return None, res

        mms_value, error = res
        value = loader(mms_value)
        iec61850.MmsValue_delete(mms_value)
        return value, error

    def read_data_set(self, data_set_path, conn):
        res = iec61850.IedConnection_readDataSetValues_no_gil(
            conn, data_set_path, None)
        if res is None or isinstance(res, int):
            print('Read data set {} failed, error: {}'.format(data_set_path, res))
            return None, res

        data_set, error = res
        values = iec61850.ClientDataSet_getValues(data_set)
        if iec61850.MmsValue_getType(values) == iec61850.MMS_ARRAY:
            for i in range(iec61850.MmsValue_getArraySize(values)):
                print('[{}] {}'.format(
                    i,
                    iec61850.MmsValue_printToBuffer(
                        iec61850.MmsValue_getElement(values, i), 1000)[0]))

        iec61850.ClientDataSet_destroy(data_set)
        return data_set, error

    def create_control_blocks(self, conn):
        control_blocks = {
            'capacity': iec61850.ControlObjectClient_create(
                "testmodelASG00001/SPIGAPC01.SPCSO1", conn),
            'start_service': iec61850.ControlObjectClient_create(
                "testmodelASG00001/SPIGAPC02.SPCSO1", conn),
            'stop_service': iec61850.ControlObjectClient_create(
                "testmodelASG00001/SPIGAPC03.SPCSO1", conn)
        }
        iec61850.ControlObjectClient_setOrigin(control_blocks['capacity'], None, 3)
        iec61850.ControlObjectClient_setOrigin(control_blocks['start_service'], None, 3)
        iec61850.ControlObjectClient_setOrigin(control_blocks['stop_service'], None, 3)
        self._control_blocks = control_blocks

    def perfom_control(self):
        if self._control_blocks is None:
            return

        under_capacity = iec61850.MmsValue_newBoolean(self._is_under_capacity)
        iec61850.ControlObjectClient_operate_no_gil(self._control_blocks['capacity'], under_capacity, 0)
        print('Update capacity')

        if self._service_status_count == 0:
            print('start execution')
            iec61850.ControlObjectClient_operate_no_gil(
                self._control_blocks['start_service'], iec61850.MmsValue_newBoolean(True), 0)

        if self._service_status_count == 6:
            print('stop execution')
            iec61850.ControlObjectClient_operate_no_gil(
                self._control_blocks['stop_service'], iec61850.MmsValue_newBoolean(True), 0)

        self._is_under_capacity = not self._is_under_capacity
        self._service_status_count = (self._service_status_count + 1) % 10

    def handle_report(self, parameter, report):
        print('handle report')
        dataset_directory = parameter
        dataset_values = iec61850.ClientReport_getDataSetValues(report)
        print("received report for {} with rptId {}".format(
            iec61850.ClientReport_getRcbReference(report), iec61850.ClientReport_getRptId(report)))

        if iec61850.ClientReport_hasTimestamp(report):
            unix_time = iec61850.ClientReport_getTimestamp(report) / 1000
            print("report contains timestamp {}".format(unix_time))

        if dataset_directory:
            list_size = iec61850.LinkedList_size(dataset_directory)
            for i in range(list_size):
                reason = iec61850.ClientReport_getReasonForInclusion(report, i)
                if reason != iec61850.IEC61850_REASON_NOT_INCLUDED:
                    if dataset_values:
                        value = iec61850.MmsValue_getElement(dataset_values, i)
                        if value:
                            value_str = iec61850.MmsValue_printToBuffer(value, 1024)

                    entry = iec61850.LinkedList_get(dataset_directory, i)
                    entry_name = entry.data
                    print("  {} (included for reason {}): {}".format(entry_name, reason, value_str))

    def setup_reporting(self, conn, dataset_path, rcb_reference):
        [dataset_directory, error] = iec61850.IedConnection_getDataSetDirectory(
            conn, dataset_path, None)
        if error != iec61850.IED_ERROR_OK:
            print("Reading data set directory failed!")
            return error

        [rcb, error] = iec61850.IedConnection_getRCBValues(conn, rcb_reference, None)
        if error != iec61850.IED_ERROR_OK:
            print("getRCBValues service error!")
            return error

        # prepare the parameters of the RCP
        trigger_options =\
            iec61850.TRG_OPT_DATA_CHANGED | iec61850.TRG_OPT_QUALITY_CHANGED | iec61850.TRG_OPT_GI
        iec61850.ClientReportControlBlock_setResv(rcb, True)
        iec61850.ClientReportControlBlock_setTrgOps(rcb, trigger_options)
        iec61850.ClientReportControlBlock_setDataSetReference(rcb, dataset_path.replace('.', '$'))
        iec61850.ClientReportControlBlock_setRptEna(rcb, True)
        iec61850.ClientReportControlBlock_setGI(rcb, True)

        # Configure the report receiver
        context = iec61850.transformReportHandlerContext(
            (self, self.handle_report, dataset_directory, rcb_reference))
        if not context:
            return iec61850.IED_ERROR_UNKNOWN
        report_id = iec61850.ClientReportControlBlock_getRptId(rcb)
        iec61850.IedConnection_installReportHandler(
            conn, rcb_reference, report_id, iec61850.ReportHandlerProxy, context)

        # Write RCB parameters and enable report
        parameters_mask = iec61850.RCB_ELEMENT_RPT_ENA | iec61850.RCB_ELEMENT_GI
        error = iec61850.IedConnection_setRCBValues(conn, rcb, parameters_mask, True)
        if error != iec61850.IED_ERROR_OK:
            print("setRCBValues service error!")
            return error

        return iec61850.IED_ERROR_OK


    def run(self):
        conn = iec61850.IedConnection_create()
        error = iec61850.IedConnection_connect(conn, self._host, self._port)
        if error != iec61850.IED_ERROR_OK:
            print('Failed to connect to {}:{}'.format(self._host, self._port))
            iec61850.IedConnection_destroy(conn)
            return

        print('Connected to {}:{}'.format(self._host, self._port))

        model = load_model('/config/points.json')
        self.create_control_blocks(conn)

        error = self.setup_reporting(
            conn, "testmodelASR00002/LLN0.AISPI", "testmodelASR00002/LLN0.RP.urcb04")

        while error == iec61850.IED_ERROR_OK:
            self.perfom_control()

            for point in model['points']:
                value, error = self.read_point(point, conn)
            for data_set in model['data_sets']:
                self.read_data_set(data_set, conn)

            time.sleep(10)

        error = iec61850.IedConnection_release(conn)
        if error != iec61850.IED_ERROR_OK:
            print('Release returned error: {}'.format(error))
        else:
            while iec61850.IedConnection_getState(conn) !=\
                  iec61850.IED_STATE_CLOSED:
                time.sleep(0.01)

        iec61850.IedConnection_destroy(conn)


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--host', default='localhost', help='host address of the server')
    parser.add_argument(
        '--port', default=102, type=int,
        help='port of the server, default 102')

    return parser.parse_args()


def main():
    args = _parse_args()
    client = DummyClient(args.host, args.port)
    client.run()
    return 0


if __name__ == '__main__':
    main()
