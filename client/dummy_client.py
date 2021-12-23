import argparse
import time
import iec61850
from model_loader import load_model, get_mms_loader


class DummyClient():
    def __init__(self, host, port=102):
        self._host = host
        self._port = port

    def read_point(self, point, conn):
        loader = get_mms_loader(point['type'])
        if loader is None:
            print('Cannot find corresponding converter for {}'.format(
                point['type']))
            return

        res = iec61850.IedConnection_readObject(
            conn, point['path'], point['fc'])
        if res is None:
            print('Read {} failed'.format(point['path']))
            return None, None

        mms_value, error = res
        value = loader(mms_value)
        print('{}: {}'.format(point['path'], value))
        iec61850.MmsValue_delete(mms_value)
        return value, error

    def read_data_set(self, data_set_path, conn):
        res = iec61850.IedConnection_readDataSetValues(
            conn, data_set_path, None)
        if res is None:
            print('Read data set {} failed'.format(data_set_path))
            return None, None

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

    def run(self):
        conn = iec61850.IedConnection_create()
        error = iec61850.IedConnection_connect(conn, self._host, self._port)
        if error != iec61850.IED_ERROR_OK:
            print('Failed to connect to {}:{}'.format(self._host, self._port))
            iec61850.IedConnection_destroy(conn)
            return

        print('Connected to {}:{}'.format(self._host, self._port))

        model = load_model('/config/points.json')
        while error == iec61850.IED_ERROR_OK:
            for point in model['points']:
                value, error = self.read_point(point, conn)
            for data_set in model['data_sets']:
                self.read_data_set(data_set, conn)
            time.sleep(60)

        error = iec61850.IedConnection_releaseAsync(conn)
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
