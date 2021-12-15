import signal
import time
import iec61850


def main():
    tcp_port = 102

    '''
       Setup data model
    '''

    model = iec61850.IedModel_create("testmodel")

    logical_device1 = iec61850.LogicalDevice_create("SENSORS", model)

    logical_node0 = iec61850.LogicalNode_create("LLN0", logical_device1)

    lln0_mod = iec61850.CDC_ENS_create(
        "Mod", iec61850.toModelNode(logical_node0), 0)
    lln0_health = iec61850.CDC_ENS_create(
        "Health", iec61850.toModelNode(logical_node0), 0)

    iec61850.SettingGroupControlBlock_create(logical_node0, 1, 1)

    # Add a temperature sensor LN
    ttmp1 = iec61850.LogicalNode_create("TTMP1", logical_device1)
    ttmp1_tmpsv = iec61850.CDC_SAV_create(
        "TmpSv", iec61850.toModelNode(ttmp1), 0, False)

    temperature_value = iec61850.ModelNode_getChild(
        iec61850.toModelNode(ttmp1_tmpsv), "instMag.f")
    temperature_timestamp = iec61850.ModelNode_getChild(
        iec61850.toModelNode(ttmp1_tmpsv), "t")

    data_set = iec61850.DataSet_create("TmpSv", ttmp1)
    iec61850.DataSetEntry_create(
        data_set, "TTMP1$MX$TmpSv$instMag$f", -1, None)
    iec61850.DataSetEntry_create(data_set, "TTMP1$MX$TmpSv$t", -1, None)

    rpt_options = (iec61850.RPT_OPT_SEQ_NUM |
                   iec61850.RPT_OPT_TIME_STAMP |
                   iec61850.RPT_OPT_REASON_FOR_INCLUSION)

    iec61850.ReportControlBlock_create(
        "events01", logical_node0, "events01", False, None, 1,
        iec61850.TRG_OPT_DATA_CHANGED, rpt_options, 50, 0)
    iec61850.ReportControlBlock_create(
        "events02", logical_node0, "events02", False, None, 1,
        iec61850.TRG_OPT_DATA_CHANGED, rpt_options, 50, 0)

    iec61850.GSEControlBlock_create(
        "gse01", logical_node0, "events01", "events", 1, False, 200, 3000)

    '''
       run server
    '''

    ied_server = iec61850.IedServer_create(model)

    # MMS server will be instructed to start listening to client connections.
    iec61850.IedServer_start(ied_server, tcp_port)

    if not iec61850.IedServer_isRunning(ied_server):
        print("Starting server failed! Exit.\n")
        iec61850.IedServer_destroy(ied_server)
        exit(-1)

    running = True

    def sigint_handler(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, sigint_handler)

    val = 0.0

    while (running):
        iec61850.IedServer_lockDataModel(ied_server)

        iec61850.IedServer_updateUTCTimeAttributeValue(
            ied_server,
            iec61850.toDataAttribute(temperature_timestamp),
            int(time.time() * 1000))
        iec61850.IedServer_updateFloatAttributeValue(
            ied_server, iec61850.toDataAttribute(temperature_value), val)

        iec61850.IedServer_unlockDataModel(ied_server)
        val += 0.1

        time.sleep(0.1)

    # stop MMS server - close TCP server socket and all client sockets
    iec61850.IedServer_stop(ied_server)

    # Cleanup - free all resources
    iec61850.IedServer_destroy(ied_server)

    # destroy dynamic data model
    iec61850.IedModel_destroy(model)
    return 0


if __name__ == '__main__':
    main()
