"""Decode and pair captured Modbus RTU ADUs without a serial or GUI dependency."""
FC_NAMES = {1: "读取线圈", 2: "读取离散输入", 3: "读取保持寄存器", 4: "读取输入寄存器",
            5: "写单个线圈", 6: "写单个寄存器", 15: "写多个线圈", 16: "写多个寄存器"}
EXCEPTIONS = {1: "非法功能码", 2: "非法数据地址", 3: "非法数据值",
              4: "从站设备故障", 5: "确认", 6: "设备忙", 8: "存储奇偶校验错误",
              10: "网关路径不可用", 11: "目标设备未响应"}


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def decode(data, request, context=None):
    """Return fields with offsets even when a captured frame is invalid."""
    raw = bytes(data)
    frame = {"direction": "TX" if request else "RX", "raw_hex": raw.hex(),
             "byte_length": len(raw), "slave_id": raw[0] if raw else None,
             "function_code": raw[1] if len(raw) > 1 else None,
             "decoded_fields": [], "crc_ok": None, "crc_received": None,
             "crc_computed": None, "status": "OK", "error": None}
    fields = frame["decoded_fields"]

    def field(offset, length, name, value=None):
        chunk = raw[offset:offset + length]
        fields.append({"offset": offset, "length": length, "name": name,
                       "raw_hex": chunk.hex(), "value": int.from_bytes(chunk, "big") if value is None else value})
        return fields[-1]["value"]

    def invalid(status, message):
        frame.update(status=status, error=message)

    if raw:
        field(0, 1, "从站地址")
    if len(raw) >= 2:
        field(1, 1, "功能码")
    if len(raw) < 4:
        invalid("PARTIAL", "ADU 不完整")
        if len(raw) > 2:
            field(2, len(raw) - 2, "未解析字节")
        return frame
    if len(raw) > 256:
        invalid("LENGTH_ERROR", "ADU 超过 256 字节")
        return frame

    unit, fc = raw[:2]
    data_end = len(raw) - 2
    exception = not request and bool(fc & 0x80)
    required = None
    if exception:
        required = 5
    elif fc in FC_NAMES:
        if request and fc in (15, 16):
            if len(raw) >= 9:
                required = 9 + raw[6]
            else:
                required = 9
        elif not request and fc <= 4:
            required = 5 + raw[2] if len(raw) >= 5 else 5
        else:
            required = 8
    if required is not None and len(raw) < required:
        # An early stop can contain a complete malformed frame with valid CRC.
        if crc16(raw[:-2]) != int.from_bytes(raw[-2:], "little"):
            invalid("PARTIAL", f"应收 {required} 字节，实收 {len(raw)} 字节")
            if len(raw) > 2:
                field(2, len(raw) - 2, "未解析字节")
            return frame

    frame["crc_received"] = int.from_bytes(raw[-2:], "little")
    frame["crc_computed"] = crc16(raw[:-2])
    frame["crc_ok"] = frame["crc_received"] == frame["crc_computed"]

    def payload(offset, count, coils, address, quantity):
        values = []
        for index in range(count):
            if coils:
                byte = raw[offset + index]
                bits = [{"address": address + index * 8 + bit, "value": (byte >> bit) & 1}
                        for bit in range(min(8, quantity - index * 8))]
                field(offset + index, 1, "线圈 / DI 位数据（低位先）", bits)
                values.extend(v["value"] for v in bits)
            else:
                values.append(field(offset + index * 2, 2, f"寄存器 {address + index}"))
        return values

    if required is not None and len(raw) != required:
        invalid("LENGTH_ERROR", f"根据功能码与 Byte Count 应为 {required} 字节，实收 {len(raw)} 字节")
    elif not 0 <= unit <= 247:
        invalid("VALUE_ERROR", "无效从站地址")
    elif exception:
        code = field(2, 1, "异常码")
        frame.update(exception_code=code)
        invalid("EXCEPTION", EXCEPTIONS.get(code, "未知异常码"))
    elif fc not in FC_NAMES:
        invalid("UNKNOWN_FUNCTION", "未知功能码")
    elif request or fc >= 5:
        address = field(2, 2, "起始地址" if fc not in (5, 6) else "地址")
        value = field(4, 2, "线圈编码" if fc == 5 else "寄存器值" if fc == 6 else "数量")
        frame["address"] = address
        if fc in (5, 6):
            frame["values"] = [value]
            if fc == 5 and value not in (0, 0xFF00):
                invalid("VALUE_ERROR", "线圈写入编码应为 0xFF00 或 0x0000")
        else:
            frame["quantity"] = value
            limit = {1: 2000, 2: 2000, 3: 125, 4: 125, 15: 1968, 16: 123}[fc]
            if not 1 <= value <= limit or address + value > 65536:
                invalid("VALUE_ERROR", "地址或数量超出协议范围")
            if request and fc in (15, 16):
                count = field(6, 1, "Byte Count")
                if count != ((value + 7) // 8 if fc == 15 else value * 2):
                    invalid("LENGTH_ERROR", "数量与 Byte Count 不一致")
                else:
                    frame["values"] = payload(7, count if fc == 15 else value, fc == 15, address, value)
    else:
        count = field(2, 1, "Byte Count")
        coils = fc in (1, 2)
        address = (context or {}).get("address", 0)
        quantity = (context or {}).get("quantity", count * 8 if coils else count // 2)
        if not count or count > 250 or (not coils and count % 2):
            invalid("LENGTH_ERROR", "无效 Byte Count")
        elif context and count != ((quantity + 7) // 8 if coils else quantity * 2):
            invalid("LENGTH_ERROR", "响应 Byte Count 与请求数量不一致")
        else:
            frame["values"] = payload(3, count if coils else count // 2, coils, address, quantity)
    if data_end > 2 and not any(item["offset"] >= 2 for item in fields):
        field(2, data_end - 2, "未解析数据")
    elif fields and fields[-1]["offset"] + fields[-1]["length"] < data_end:
        offset = fields[-1]["offset"] + fields[-1]["length"]
        field(offset, data_end - offset, "未解析数据")

    field(data_end, 1, "CRC Lo")
    field(data_end + 1, 1, "CRC Hi")
    if not frame["crc_ok"]:
        invalid("CRC_ERROR", "CRC16-Modbus 不匹配")
    return frame


def pair(tx, rx):
    request = decode(tx, True)
    response = decode(rx, False, request)
    fc = request["function_code"]
    can_match = request["status"] == "OK" or (
        request["crc_ok"] and response["status"] == "EXCEPTION")
    matched = (can_match and response["status"] in ("OK", "EXCEPTION") and
               request["slave_id"] == response["slave_id"] and
               response["function_code"] == (fc | 0x80 if response["status"] == "EXCEPTION" else fc))
    if matched and fc >= 5 and response["status"] == "OK":
        matched = tx[2:6] == rx[2:6]
    status = ("EXCEPTION" if matched and response["status"] == "EXCEPTION" else
              request["status"] if request["status"] != "OK" else
              "TIMEOUT" if not rx else
              "MISMATCH" if response["status"] in ("OK", "EXCEPTION") and not matched else
              "PASS" if response["status"] == "OK" else response["status"])
    error = response["error"] if status == "EXCEPTION" else request["error"] or response["error"]
    if status == "TIMEOUT":
        error = "未收到响应"
    elif status == "MISMATCH":
        error = "从站地址、功能码或写入回显与请求不一致"
    return {"tx": request, "rx": response, "matched": matched, "status": status, "error": error}
