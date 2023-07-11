import contextlib
import datetime
import time

import fire

import iec61850


@contextlib.contextmanager
def ied_connect(host="localhost", port=102):
    conn = iec61850.IedConnection_create()
    error = iec61850.IedConnection_connect(conn, host, port)
    assert error == iec61850.IED_ERROR_OK

    yield conn

    iec61850.IedConnection_destroy(conn)


def split_timestamp(timestamp_64):
    """Split 64-bit timestamp into high and low 32-bit parts."""
    low = timestamp_64 & 0xFFFFFFFF
    high = timestamp_64 >> 32
    return high, low


def combine_timestamp(high, low):
    """Combine high and low 32-bit parts into 64-bit timestamp."""
    high = high << 32
    timestamp_64 = high | low
    return timestamp_64


def handle_report(dataset_directory, report):
    print(
        "Report Control Block: {}".format(iec61850.ClientReport_getRcbReference(report))
    )
    print("Report ID: {}".format(iec61850.ClientReport_getRptId(report)))
    print(
        "Report Generation Time: {}".format(
            datetime.datetime.fromtimestamp(
                iec61850.ClientReport_getTimestamp(report) / 1000
            )
        )
    )

    dataset_values = iec61850.ClientReport_getDataSetValues(report)

    def read_dataset_entry(i):
        # reason for why this entry is included in the report
        reason_code = iec61850.ClientReport_getReasonForInclusion(report, i)
        reason = {
            iec61850.IEC61850_REASON_DATA_CHANGE: "data change",
            iec61850.IEC61850_REASON_QUALITY_CHANGE: "quality change",
            iec61850.IEC61850_REASON_DATA_UPDATE: "data update",
            iec61850.IEC61850_REASON_INTEGRITY: "integrity",
            iec61850.IEC61850_REASON_GI: "general interrogation",
        }.get(reason_code, "unknown")

        # data reference
        entry = iec61850.LinkedList_get(dataset_directory, i)
        data_reference = iec61850.toCharP(
            entry.data
        )  # ASR00001/SPIMMXU01.TotW.mag.i[MX]

        # value
        attribute = data_reference.split("/")[-1]  # SPIMMXU01.TotW.mag.i[MX]
        mms_value = iec61850.MmsValue_getElement(dataset_values, i)
        value = {
            "SPIMMXU01.TotW.mag.i[MX]": iec61850.MmsValue_toInt32,
            "SPIMMTR01.SupWh.actVal[ST]": iec61850.MmsValue_toInt64,
            "SPIMMTR01.DmdWh.actVal[ST]": iec61850.MmsValue_toInt64,
            "SPIZBAT01.InBatV.mag.i[MX]": iec61850.MmsValue_toInt32,
            "SPIZBAT01.BatSt.stVal[ST]": iec61850.MmsValue_getBoolean,
            "SPIGGIO01.AnIn1.mag.i[MX]": iec61850.MmsValue_toInt32,
            "SPIGGIO01.AnIn2.mag.i[MX]": iec61850.MmsValue_toInt32,
        }[attribute](mms_value)

        return data_reference, value, reason

    result = {
        data_reference: {"value": value, "reason": reason}
        for (data_reference, value, reason) in [
            read_dataset_entry(i)
            for i in range(iec61850.LinkedList_size(dataset_directory))
        ]
    }

    attribute_updated_time = combine_timestamp(
        result["ASR00001/SPIGGIO01.AnIn1.mag.i[MX]"]["value"],
        result["ASR00001/SPIGGIO01.AnIn2.mag.i[MX]"]["value"],
    )
    print(
        "Attribute Updated Time: {}\n".format(
            datetime.datetime.fromtimestamp(attribute_updated_time)
        )
    )

    attribute_notes = {
        "SPIMMXU01.TotW.mag.i[MX]": "瞬時輸出/入總實功率(kW) (int32)",
        "SPIMMTR01.SupWh.actVal[ST]": "瞬時累計輸出/發電電能量(kWh) (int64)",
        "SPIMMTR01.DmdWh.actVal[ST]": "瞬時累計輸入/用電電能量(kWh) (int64)",
        "SPIZBAT01.InBatV.mag.i[MX]": "儲能系統瞬時剩餘電量 SOC(0.01kWh), 自用發電設備 M2 交易表計總實功率 (int32)",
        "SPIZBAT01.BatSt.stVal[ST]": "儲能系統/發電設備狀態, 用戶狀態 (boolean)",
        "SPIGGIO01.AnIn1.mag.i[MX]": "每分鐘時間點[Unix Timestamp-H] (int32)",
        "SPIGGIO01.AnIn2.mag.i[MX]": "每分鐘時間點[Unix Timestamp-L] (int32)",
    }
    for data_reference in result.keys():
        attribute = data_reference.split("/")[-1]
        print(
            f"{attribute_notes[attribute]} because {result[data_reference]['reason']}"
        )
        print(f"{data_reference}: {result[data_reference]['value']}\n")


def report(resource_code=1):
    with ied_connect() as conn:
        # get RCB object from server
        rcb_reference = f"ASR{resource_code:05d}/LLN0.RP.urcb04"
        rcb, _ = iec61850.IedConnection_getRCBValues(conn, rcb_reference, None)

        # install the report handler
        dataset_directory, _ = iec61850.IedConnection_getDataSetDirectory(
            conn, f"ASR{resource_code:05d}/LLN0.AISPI", None
        )
        context = iec61850.transformReportHandlerContext(
            (None, handle_report, dataset_directory, rcb_reference)
        )
        iec61850.IedConnection_installReportHandler(
            conn,
            rcb_reference,
            iec61850.ClientReportControlBlock_getRptId(rcb),
            iec61850.ReportHandlerProxy,
            context,
        )

        # enable the report
        iec61850.ClientReportControlBlock_setRptEna(rcb, True)
        iec61850.ClientReportControlBlock_setGI(rcb, True)
        iec61850.IedConnection_setRCBValues(
            conn,
            rcb,
            iec61850.RCB_ELEMENT_RPT_ENA
            | iec61850.RCB_ELEMENT_GI,  # parameter mast define which parameter to set
            True,
        )

        # wait for reports
        while True:
            time.sleep(10)


if __name__ == "__main__":
    fire.Fire(
        {
            "report": report,
        }
    )
