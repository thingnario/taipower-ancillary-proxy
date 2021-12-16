import signal
import time
import iec61850
from model_loader import load_model


class ProxyServer():
    def __init__(self):
        self._running = False
        self._port = 102

    def start(self, model):
        self._model = model
        self._ied_server = iec61850.IedServer_create(model['inst'])

        # MMS server will be instructed to start listening to client connections.
        iec61850.IedServer_start(self._ied_server, self._port)

        if not iec61850.IedServer_isRunning(self._ied_server):
            print("Starting server failed! Exit.\n")
            iec61850.IedServer_destroy(self._ied_server)
            return False

        self._running = True

        def sigint_handler(sig, frame):
            self._running = False

        signal.signal(signal.SIGINT, sigint_handler)
        return True

    def run(self):
        val = 0.0

        print(self._model)
        temp_ts = iec61850.toDataAttribute(
            self._model['SENSORS']['TTMP1']['TmpSv']['t'])
        temp_value = iec61850.toDataAttribute(
            self._model['SENSORS']['TTMP1']['TmpSv']['instMag.f'])
        while (self._running):
            iec61850.IedServer_lockDataModel(self._ied_server)

            iec61850.IedServer_updateUTCTimeAttributeValue(
                self._ied_server, temp_ts, int(time.time() * 1000))
            iec61850.IedServer_updateFloatAttributeValue(
                self._ied_server, temp_value, val)

            iec61850.IedServer_unlockDataModel(self._ied_server)
            val += 0.1

            time.sleep(0.1)

    def stop(self):
        # stop MMS server - close TCP server socket and all client sockets
        iec61850.IedServer_stop(self._ied_server)

        # Cleanup - free all resources
        iec61850.IedServer_destroy(self._ied_server)

        # destroy dynamic data model
        iec61850.IedModel_destroy(self._model['inst'])


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
