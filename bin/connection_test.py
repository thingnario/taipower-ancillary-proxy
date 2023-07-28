import arrow
import contextlib
import datetime
import random
import re
import threading
import time

import fire

import iec61850


@contextlib.contextmanager
def ied_connect(host, port):
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


def handle_report_group_event(dataset_directory, report):
    rcb_reference = iec61850.ClientReport_getRcbReference(
        report
    )  # ASG90001/LLN0.RP.diurcb04
    report_id = iec61850.ClientReport_getRptId(report)
    generated_time = datetime.datetime.fromtimestamp(
        iec61850.ClientReport_getTimestamp(report) / 1000
    )
    print(f"Report Control Block: {rcb_reference}")
    print(f"Report ID: {report_id}")
    print(f"Report Generation Time: {generated_time}")

    match = re.search(
        r"ASG(?P<group_code>\d+)/LLN0\.RP\.(?P<report_name>.+)", rcb_reference
    )
    group_code = int(match.group("group_code"))
    report_name = match.group("report_name")
    product = {
        "diurcb0301": "SPI",
        "diurcb0401": "SUP",
    }.get(report_name, "Unknown")

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
        reference = iec61850.toCharP(entry.data)

        # value
        mms_value = iec61850.MmsValue_getElement(dataset_values, i)
        value = iec61850.MmsValue_getBoolean(mms_value)

        # note
        note = {
            f"ASG{group_code:05d}/{product}GGIO01.Ind1.stVal[ST]": "履行待命服務開始",
            f"ASG{group_code:05d}/{product}GGIO02.Ind1.stVal[ST]": "履行待命服務結束",
            f"ASG{group_code:05d}/{product}GGIO03.Ind1.stVal[ST]": "回報接獲執行指令",
            f"ASG{group_code:05d}/{product}GGIO04.Ind1.stVal[ST]": "回報接獲結束指令",
            f"ASG{group_code:05d}/{product}GGIO05.Ind1.stVal[ST]": "回報執行結束",
        }[reference]

        return reference, {"value": value, "reason": reason, "note": note}

    result = {
        reference: data
        for reference, data in [
            read_dataset_entry(i)
            for i in range(iec61850.LinkedList_size(dataset_directory))
        ]
    }

    # Print values of the report
    for reference, data in result.items():
        print(f"{data['note']} {reference}: {data['value']} due to {data['reason']}")


def report_group_event(
    group_code=90001, product="SUP", host="localhost", port=102
):  # SPI or SUP
    rcb_reference = {
        "SPI": f"ASG{group_code:05d}/LLN0.RP.diurcb0301",
        "SUP": f"ASG{group_code:05d}/LLN0.RP.diurcb0401",
    }[product]
    dataset_reference = f"ASG{group_code:05d}/LLN0.DI{product}"
    with ied_connect(host, port) as conn:
        # get RCB object from server
        rcb, _ = iec61850.IedConnection_getRCBValues(conn, rcb_reference, None)

        # install the report handler
        dataset_directory, _ = iec61850.IedConnection_getDataSetDirectory(
            conn, dataset_reference, None
        )
        context = iec61850.transformReportHandlerContext(
            (None, handle_report_group_event, dataset_directory, rcb_reference)
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


def handle_report_group(dataset_directory, report):
    rcb_reference = iec61850.ClientReport_getRcbReference(report)
    report_id = iec61850.ClientReport_getRptId(report)
    generated_time = datetime.datetime.fromtimestamp(
        iec61850.ClientReport_getTimestamp(report) / 1000
    )
    print(f"Report Control Block: {rcb_reference}")
    print(f"Report ID: {report_id}")
    print(f"Report Generation Time: {generated_time}")

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
        reference = iec61850.toCharP(entry.data)
        ln_do_da = reference.split("/")[-1]

        # value
        mms_value = iec61850.MmsValue_getElement(dataset_values, i)
        value = {"GROMMTR01.SupWh.actVal[ST]": iec61850.MmsValue_toInt64,}.get(
            ln_do_da, iec61850.MmsValue_toInt32
        )(mms_value)

        # note
        note = {
            "QSEGGIO01.IntIn1.stVal[ST]": "合格交易者代碼",
            "QSEGGIO01.IntIn2.stVal[ST]": "報價代碼",
            "QSEGGIO01.IntIn3.stVal[ST]": "輔助服務商品",
            "GROMMXU01.TotW.mag.i[MX]": "該報價代碼所聚合交易資源之該分鐘加總實功率。。當為用電情形時，此欄位為負值；執行逆送時，此欄位為正值。",
            "GROGGIO01.AnIn1.mag.i[MX]": "Unix Timestamp-H",
            "GROGGIO01.AnIn2.mag.i[MX]": "Unix Timestamp-L",
            # "GROMMXU02.TotW.mag.i[MX]": "即時備轉、補充備轉，此欄位為 0",
            # "GROGGIO02.AnIn1.mag.i[MX]": "Unix Timestamp-H",
            # "GROMMTR01.SupWh.actVal[ST]": "交易資源為未獲同意可執行逆送之需量反應提供者，此欄位為 0",
            "GROMMTR01.DmdWh.actVal[ST]": "報價代碼聚合之所有交易資源加總之累計用電量",
            "GROGGIO11.AnIn1.mag.i[MX]": "執行率計算時間點 Unix Timestamp-H",
            "GROGGIO11.AnIn2.mag.i[MX]": "執行率計算時間點 Unix Timestamp-L",
            "GROGGIO11.AnIn3.mag.i[MX]": "執行率。若輔助服務商品為即時備轉或補充備轉者，當不處於調度事件執行期間，此欄位填入 0 為代表",
        }.get(ln_do_da, "不重要")

        return reference, {"value": value, "reason": reason, "note": note}

    result = {
        reference: data
        for reference, data in [
            read_dataset_entry(i)
            for i in range(iec61850.LinkedList_size(dataset_directory))
        ]
    }

    # Print values of the report
    for reference, data in result.items():
        if reference.endswith("AnIn2.mag.i[MX]"):
            value = (
                arrow.get(data["value"]).to("Asia/Taipei").format("YYYY-MM-DD HH:mm:ss")
            )
        else:
            value = data["value"]
        print(f"{reference}: {value} ({data['reason']}), {data['note']}")


def report_group(group_code=90001, host="localhost", port=102):
    rcb_reference = f"ASG{group_code:05d}/LLN0.RP.urcb0101"
    dataset_reference = f"ASG{group_code:05d}/LLN0.AIGRO"
    with ied_connect(host, port) as conn:
        # get RCB object from server
        rcb, _ = iec61850.IedConnection_getRCBValues(conn, rcb_reference, None)

        # install the report handler
        dataset_directory, _ = iec61850.IedConnection_getDataSetDirectory(
            conn, dataset_reference, None
        )
        context = iec61850.transformReportHandlerContext(
            (None, handle_report_group, dataset_directory, rcb_reference)
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


def handle_report_resource(dataset_directory, report):
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
        attribute_reference = data_reference.split("/")[-1]  # SPIMMXU01.TotW.mag.i[MX]
        attribute_name = attribute_reference.split(".", 1)[1]  # TotW.mag.i[MX]
        mms_value = iec61850.MmsValue_getElement(dataset_values, i)
        value = {
            "TotW.mag.i[MX]": iec61850.MmsValue_toInt32,
            "SupWh.actVal[ST]": iec61850.MmsValue_toInt64,
            "DmdWh.actVal[ST]": iec61850.MmsValue_toInt64,
            "InBatV.mag.i[MX]": iec61850.MmsValue_toInt32,
            "BatSt.stVal[ST]": iec61850.MmsValue_getBoolean,
            "AnIn1.mag.i[MX]": iec61850.MmsValue_toInt32,
            "AnIn2.mag.i[MX]": iec61850.MmsValue_toInt32,
        }[attribute_name](mms_value)

        note = {
            "TotW.mag.i[MX]": "瞬時輸出/入總實功率(kW) (int32)",
            "SupWh.actVal[ST]": "瞬時累計輸出/發電電能量(kWh) (int64)",
            "DmdWh.actVal[ST]": "瞬時累計輸入/用電電能量(kWh) (int64)",
            "InBatV.mag.i[MX]": "儲能系統瞬時剩餘電量 SOC(0.01kWh), 自用發電設備 M2 交易表計總實功率 (int32)",
            "BatSt.stVal[ST]": "儲能系統/發電設備狀態, 用戶狀態 (boolean)",
            "AnIn1.mag.i[MX]": "每分鐘時間點[Unix Timestamp-H] (int32)",
            "AnIn2.mag.i[MX]": "每分鐘時間點[Unix Timestamp-L] (int32)",
        }[attribute_name]

        return data_reference, value, reason, note

    result = {
        data_reference: {"value": value, "reason": reason, "note": note}
        for (data_reference, value, reason, note) in [
            read_dataset_entry(i)
            for i in range(iec61850.LinkedList_size(dataset_directory))
        ]
    }

    # Print values of the report
    for reference, value in result.items():
        print(f"{value['note']} because {value['reason']}")
        print(f"{reference}: {value['value']}\n")

    # Print timestamp of the report
    # 每分鐘時間點[Unix Timestamp-H], endswith AnIn1.mag.i[MX]
    high = [v for k, v in result.items() if k.endswith("AnIn1.mag.i[MX]")][0]["value"]
    # 每分鐘時間點[Unix Timestamp-L], endswith AnIn2.mag.i[MX]
    low = [v for k, v in result.items() if k.endswith("AnIn2.mag.i[MX]")][0]["value"]
    timestamp = combine_timestamp(high=high, low=low)
    print(
        f"每分鐘時機點: {arrow.get(timestamp).to('Asia/Taipei').format('YYYY-MM-DD HH:mm:ss')}"
    )


def report_resource(
    resource_code=1, product="SUP", host="localhost", port=102
):  # SPI or SUP
    rcb_reference = {
        "SPI": f"ASR{resource_code:05d}/LLN0.RP.urcb0401",
        "SUP": f"ASR{resource_code:05d}/LLN0.RP.urcb0501",
    }[product]
    dataset_reference = {
        "SPI": f"ASR{resource_code:05d}/LLN0.AISPI",
        "SUP": f"ASR{resource_code:05d}/LLN0.AISUP",
    }[product]

    with ied_connect(host, port) as conn:
        # get RCB object from server
        rcb, _ = iec61850.IedConnection_getRCBValues(conn, rcb_reference, None)

        # install the report handler
        dataset_directory, _ = iec61850.IedConnection_getDataSetDirectory(
            conn, dataset_reference, None
        )
        context = iec61850.transformReportHandlerContext(
            (None, handle_report_resource, dataset_directory, rcb_reference)
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


def notify(group_code=90001, product="SUP", host="localhost", port=102):  # SPI or SUP
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
    with ied_connect(host, port) as conn:
        send_command(
            "平台通知用電量不足／SOC 準備量不足／機組剩餘可用量不足",
            conn,
            f"ASG{group_code:05d}/{product}GAPC01.SPCSO1",
            True,
        )

        time.sleep(2.5)

        send_command("平台復歸", conn, f"ASG{group_code:05d}/{product}GAPC01.SPCSO1", False)


def activate(
    group_code=90001,
    capacity=1,  # 單位為 MW。乘上 100 倍後發送指令。
    product="SUP",  # SPI or SUP
    host="localhost",
    port=102,
):
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
    with ied_connect(host, port) as conn:
        threads = []

        # AO: 啟動指令發出時間
        command_submit_time = int(time.time())
        _, submit_timestamp_low = split_timestamp(command_submit_time)
        threads.append(
            threading.Thread(
                target=send_command,
                args=(
                    "啟動指令發出時間(Unix Timestamp-L)",
                    conn,
                    f"ASG{group_code:05d}/{product}GGIO01.AnOut2",
                    submit_timestamp_low,
                ),
            )
        )

        # AO: 指令服務開始時間
        start_execute_time = command_submit_time // 3600 * 3600 + 3600  # 下個整點
        _, start_timestamp_low = split_timestamp(start_execute_time)
        threads.append(
            threading.Thread(
                target=send_command,
                args=(
                    "指令服務開始時間(Unix Timestamp-L)",
                    conn,
                    f"ASG{group_code:05d}/{product}GGIO02.AnOut2",
                    start_timestamp_low,
                ),
            )
        )

        # AO: 指令服務結束時間
        end_execute_time = start_execute_time + 3600  # 執行一小時
        _, end_timestamp_low = split_timestamp(end_execute_time)
        threads.append(
            threading.Thread(
                target=send_command,
                args=(
                    "指令服務結束時間(Unix Timestamp-L)",
                    conn,
                    f"ASG{group_code:05d}/{product}GGIO05.AnOut2",
                    end_timestamp_low,
                ),
            )
        )

        # AO: 指令執行容量
        threads.append(
            threading.Thread(
                target=send_command,
                args=(
                    "指令執行容量",
                    conn,
                    f"ASG{group_code:05d}/{product}GGIO03.AnOut1",
                    capacity * 100,  # 單位為 0.01MW。所以乘上 100 倍後發送指令。
                ),
            )
        )

        # DO: 啟動指令
        threads.append(
            threading.Thread(
                target=send_command,
                args=(
                    "啟動指令",
                    conn,
                    f"ASG{group_code:05d}/{product}GAPC02.SPCSO1",
                    True,
                ),
            )
        )

        # 送出指令
        random.shuffle(threads)
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]

        # 確認合格交易者有收到指令
        command_received_reference = f"ASG{group_code:05d}/{product}GGIO03.Ind1.stVal"
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


def deactivate(
    group_code=90001, product="SUP", host="localhost", port=102  # SPI or SUP
):
    """即時備轉結束指令

    平台得發送此調度指令結束該次調度執行事件，報價代碼需接續回覆結束指令接獲回報(相關說明請見 3.2.1)。

    平台得發送此調度指令結束該次調度執行事件，亦將同時通知該報價代碼結束指令發出時間及服務結束時間，
    報價代碼接獲此結束指令時，應至 AO(接收平台通知功能)取得相關資訊(相關說明請見 3.2.4)。

    此欄位值為
    - False: 未發出指令
    - True: 結束指令
    """
    with ied_connect(host, port) as conn:
        threads = []

        # AO: 結束指令發出時間
        command_submit_time = int(time.time())
        _, submit_timestamp_low = split_timestamp(command_submit_time)
        threads.append(
            threading.Thread(
                target=send_command,
                args=(
                    "結束指令發出時間(Unix Timestamp-L)",
                    conn,
                    f"ASG{group_code:05d}/{product}GGIO04.AnOut2",
                    submit_timestamp_low,
                ),
            )
        )

        # AO: 指令服務結束時間
        end_execute_time = command_submit_time  # 馬上結束
        _, end_timestamp_low = split_timestamp(end_execute_time)
        threads.append(
            threading.Thread(
                target=send_command,
                args=(
                    "指令服務結束時間(Unix Timestamp-L)",
                    conn,
                    f"ASG{group_code:05d}/{product}GGIO05.AnOut2",
                    end_timestamp_low,
                ),
            )
        )

        # DO: 結束指令
        threads.append(
            threading.Thread(
                target=send_command,
                args=(
                    "結束指令",
                    conn,
                    f"ASG{group_code:05d}/{product}GAPC03.SPCSO1",
                    True,
                ),
            )
        )

        # 送出指令
        random.shuffle(threads)
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]

        # 確認合格交易者有收到指令
        command_received_reference = f"ASG{group_code:05d}/{product}GGIO04.Ind1.stVal"
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
            "report_group_event": report_group_event,  # 報價代碼事件回報，例如履行待命服務開始、結束
            "report_group": report_group,  # 報價代碼狀態回報，總輸出功率
            "report_resource": report_resource,  # 交易資源狀態回報，例如輸出功率
            "activate": activate,  # 即時備轉啟動指令
            "deactivate": deactivate,  # 即時備轉結束指令
            "notify": notify,  # 電量不足／SOC 準備量不足／機組剩餘可用量不足
        }
    )
