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


def send_command(annotation, connection, reference, value):
    """Send a command to the IED Server"""
    print(f"{annotation}: {reference} = {value}")
    control_object = iec61850.ControlObjectClient_create(reference, connection)
    iec61850.ControlObjectClient_setOrigin(
        control_object, None, iec61850.CONTROL_ORCAT_REMOTE_CONTROL
    )
    iec61850.ControlObjectClient_operate(
        control_object,
        {
            int: iec61850.MmsValue_newIntegerFromInt32,
            bool: iec61850.MmsValue_newBoolean,
        }[type(value)](value),
        0,
    )


def notify(group_code=1):
    """平台通知用電量不足／SOC 準備量不足／機組剩餘可用量不足

    平台於非調度執行期間，將持續偵測該報價代碼之交易資源準備量，當交易資源之
    - 用電量不足(需量反應態樣)
    - SOC 準備量不足(併網型儲能態樣)
    - 機組剩餘可用量不足(發電機組或自用發電設備態樣)
    時，平台將發送此通知予該報價代碼。

    此欄位值為
    - False: 未發出指令
    - True: 用電量不足/SOC 準備量不足/機組剩餘可用量不足

    每分鐘偵測及發佈
    """
    with ied_connect() as conn:
        send_command(
            "平台通知用電量不足／SOC 準備量不足／機組剩餘可用量不足",
            conn,
            f"ASG{group_code:05d}/SPIGAPC01.SPCSO1",
            True,
        )

        time.sleep(2.5)

        send_command("平台復歸", conn, f"ASG{group_code:05d}/SPIGAPC01.SPCSO1", False)


def activate(group_code=1, capacity=1):  # 單位為 0.01MW。乘上 100 倍後發送指令。
    """即時備轉啟動指令

    當電力系統因事故而有即時備轉輔助服務需求時，平台將發送此調度指令予報價代碼，以啟動即時備轉服務。
    報價代碼需接續回覆執行指令接獲回報(相關說明請見 3.2.1)。

    平台發送此調度指令時，亦將同時通知該報價代碼
    - 啟動指令發出時間
    - 指令服務開始時間
    - 指令服務結束時間
    - 指令執行容量。
    報價代碼接獲此啟動指令時，應至 AO(接收平台通知功能) 取得相關資訊(相關說明請見 3.2.4)。

    此欄位值為
    - False: 未發出指令
    - True: 啟動指令

    Args:
    - group_code: 報價代碼
    - capacity: 指令執行容量，單位為 MW。
    """
    with ied_connect() as conn:
        # AO: 啟動指令發出時間
        command_submit_time = int(time.time())
        high, low = split_timestamp(command_submit_time)
        send_command(
            "啟動指令發出時間(Unix Timestamp-H)",
            conn,
            f"ASG{group_code:05d}/SPIGGIO01.AnOut1",
            high,
        )
        send_command(
            "啟動指令發出時間(Unix Timestamp-L)",
            conn,
            f"ASG{group_code:05d}/SPIGGIO01.AnOut2",
            low,
        )

        # AO: 指令服務開始時間
        start_execute_time = command_submit_time // 3600 * 3600 + 3600  # 下個整點
        high, low = split_timestamp(start_execute_time)
        send_command(
            "指令服務開始時間(Unix Timestamp-H)",
            conn,
            f"ASG{group_code:05d}/SPIGGIO02.AnOut1",
            high,
        )
        send_command(
            "指令服務開始時間(Unix Timestamp-L)",
            conn,
            f"ASG{group_code:05d}/SPIGGIO02.AnOut2",
            low,
        )

        # AO: 指令服務結束時間
        end_execute_time = start_execute_time + 3600  # 執行一小時
        high, low = split_timestamp(end_execute_time)
        send_command(
            "指令服務結束時間(Unix Timestamp-H)",
            conn,
            f"ASG{group_code:05d}/SPIGGIO05.AnOut1",
            high,
        )
        send_command(
            "指令服務結束時間(Unix Timestamp-L)",
            conn,
            f"ASG{group_code:05d}/SPIGGIO05.AnOut2",
            low,
        )

        # AO: 指令執行容量。單位為 0.01MW。乘上 100 倍後發送指令。
        send_command("指令執行容量", conn, f"ASG{group_code:05d}/SPIGGIO03.AnOut1", capacity)

        # DO: 啟動指令
        send_command("啟動指令", conn, f"ASG{group_code:05d}/SPIGAPC02.SPCSO1", True)

        # 確認合格交易者有收到指令
        command_received_reference = f"ASG{group_code:05d}/SPIGGIO03.Ind1.stVal"
        mms_value, _ = iec61850.IedConnection_readObject(
            conn, command_received_reference, iec61850.IEC61850_FC_ST
        )
        value = iec61850.MmsValue_getBoolean(mms_value)
        assert value is True, "回報接獲執行指令狀態異常，應為 True"

        time.sleep(3)

        # 確認 2.5 秒後，合格交易者有 reset 表示已收到指令的狀態
        mms_value, _ = iec61850.IedConnection_readObject(
            conn, command_received_reference, iec61850.IEC61850_FC_ST
        )
        value = iec61850.MmsValue_getBoolean(mms_value)
        assert value is False, "回報接獲執行指令在 2.5 秒後未被復歸，應為 False"


def deactivate(group_code=1):
    """即時備轉結束指令

    平台得發送此調度指令結束該次調度執行事件，報價代碼需接續回覆結束指令接獲回報(相關說明請見 3.2.1)。

    平台得發送此調度指令結束該次調度執行事件，亦將同時通知該報價代碼結束指令發出時間及服務結束時間，
    報價代碼接獲此結束指令時，應至 AO(接收平台通知功能)取得相關資訊(相關說明請見 3.2.4)。

    此欄位值為
    - False: 未發出指令
    - True: 結束指令
    """
    with ied_connect() as conn:
        # AO: 結束指令發出時間
        command_submit_time = int(time.time())
        high, low = split_timestamp(command_submit_time)
        send_command(
            "結束指令發出時間(Unix Timestamp-H)",
            conn,
            f"ASG{group_code:05d}/SPIGGIO04.AnOut1",
            high,
        )
        send_command(
            "結束指令發出時間(Unix Timestamp-L)",
            conn,
            f"ASG{group_code:05d}/SPIGGIO04.AnOut2",
            low,
        )

        # DO: 結束指令
        send_command("啟動指令", conn, f"ASG{group_code:05d}/SPIGAPC03.SPCSO1", True)

        # 確認合格交易者有收到指令
        command_received_reference = f"ASG{group_code:05d}/SPIGGIO04.Ind1.stVal"
        mms_value, _ = iec61850.IedConnection_readObject(
            conn, command_received_reference, iec61850.IEC61850_FC_ST
        )
        value = iec61850.MmsValue_getBoolean(mms_value)
        assert value is True, "回報接獲結束指令狀態異常，應為 True"

        time.sleep(3)

        # 確認 2.5 秒後，合格交易者有 reset 表示已收到指令的狀態
        mms_value, _ = iec61850.IedConnection_readObject(
            conn, command_received_reference, iec61850.IEC61850_FC_ST
        )
        value = iec61850.MmsValue_getBoolean(mms_value)
        assert value is False, "回報接獲結束指令在 2.5 秒後未被復歸，應為 False"
        print(f"{command_received_reference}: {value}")


if __name__ == "__main__":
    fire.Fire(
        {
            "report": report,
            "activate": activate,  # 即時備轉啟動指令
            "deactivate": deactivate,  # 即時備轉結束指令
            "notify": notify,  # 電量不足／SOC 準備量不足／機組剩餘可用量不足
        }
    )
