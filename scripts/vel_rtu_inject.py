"""Apply one transaction-scoped injection on the real RTU PTY byte path."""
import json
import os
import select
import time

from vel_rtu_fault_rules import DELAY, RULES, TIMEOUT, changes, original_request, request_bytes, response_bytes
from vel_rtu_frames import pair
from vel_rtu_session import SessionTransportError, wait_rx_ready


class FaultLink:
    """Single owner of the serial descriptor while a fault exchange is active."""

    def __init__(self, master, audit):
        self.master = master
        self.audit = audit
        self.fd = master.port.fileno()

    def note(self, kind, **fields):
        row = {"kind": kind, **fields}
        self.audit.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.audit.flush()

    @staticmethod
    def complete(data):
        if len(data) < 2:
            return False
        fc = data[1]
        size = 5 if fc & 128 else 8 if fc == 6 else 5 + data[2] if fc == 3 and len(data) >= 3 else None
        return size is not None and len(data) >= size

    def read_until(self, deadline, *, stop_at_frame=False):
        buffer = bytearray()
        first_ns = last_ns = None
        while (remaining := deadline - time.monotonic()) > 0:
            if not select.select([self.fd], [], [], remaining)[0]:
                break
            data = os.read(self.fd, 4096)
            if not data:
                raise ConnectionError("RTU 数据 PTY 已关闭")
            last_ns = time.monotonic_ns()
            if first_ns is None:
                first_ns = last_ns
            buffer.extend(data)
            if stop_at_frame and self.complete(buffer):
                break
        return bytes(buffer), first_ns, last_ns

    def exchange(self, name, original):
        self.master.sequence += 1
        seq = self.master.sequence
        started = time.monotonic_ns()
        outgoing = request_bytes(name, original)
        actual_tx = incoming = delivered = drained = b""
        tx_ns = raw_first = raw_last = rx_ns = quarantine_ns = deadline_ns = None
        error = None
        caught = None
        try:
            wait_rx_ready(self.master.control, sequence=seq)
            if select.select([self.fd], [], [], 0)[0]:
                drained = os.read(self.fd, 4096)
                raise SessionTransportError("注入前存在串口残留，结束会话以避免误配")
            if outgoing:
                tx_ns = time.monotonic_ns()
                actual_tx = outgoing[:self.master.write_bytes(outgoing)]
                if actual_tx != outgoing:
                    raise SessionTransportError("PTY 写入不完整")
            deadline = time.monotonic() + TIMEOUT
            deadline_ns = round(deadline * 1e9)
            incoming, raw_first, raw_last = self.read_until(deadline, stop_at_frame=True)
            if name == "rx_delay" and raw_first is not None:
                # The delayed buffer belongs only to this exchange. Never write it
                # to any later master read, including after the deadline.
                late, _, _ = self.read_until(raw_first / 1e9 + DELAY)
                drained += late
                quarantine_ns = time.monotonic_ns()
            else:
                delivered = response_bytes(name, incoming)
                rx_ns = time.monotonic_ns() if delivered else None
                extra, _, _ = self.read_until(deadline)
                drained += extra
            if drained:
                raise SessionTransportError("故障事务出现额外 PTY 字节，隔离本会话")
        except BaseException as exc:
            caught = exc
            error = str(exc) or type(exc).__name__

        checked = pair(actual_tx, delivered)
        observed = pair(actual_tx, incoming)
        if error is not None:
            status = "CANCELLED" if not isinstance(caught, Exception) else "TRANSPORT_ERROR"
        elif name == "rx_delay" and incoming:
            status = "LATE_RESPONSE"
            error = "220 ms 注入延迟超过 150 ms 接收期限；真实回包隔离于本事务"
        elif not delivered:
            status = "TIMEOUT"
            error = ("代理未转发从站回包" if incoming else
                     "请求未写入从站 PTY" if not actual_tx else "从站 PTY 在期限内无响应")
        else:
            status, error = checked["status"], checked["error"]
            if status == "EXCEPTION":
                error = checked["rx"]["error"]
        tx_changes = changes(original, actual_tx)
        rx_changes = changes(incoming, delivered)
        audit = {"sequence": seq, "rule": name, "direction": RULES[name].direction,
                 "original_tx_hex": original.hex(), "slave_rx_hex": actual_tx.hex(),
                 "slave_tx_hex": incoming.hex(), "master_rx_hex": delivered.hex(),
                 "tx_changes": tx_changes, "rx_changes": rx_changes, "slave_tx_ns": raw_first,
                 "slave_tx_last_ns": raw_last, "host_deadline_ns": deadline_ns, "quarantine_ns": quarantine_ns,
                 "delayed_ms": DELAY * 1000 if name == "rx_delay" else None,
                 "quarantined_hex": incoming.hex() if quarantine_ns is not None else "",
                 "additional_pty_bytes_hex": drained.hex(),
                 "slave_response_status": observed["status"] if incoming else "NO_RESPONSE",
                 "slave_response_crc_ok": observed["rx"]["crc_ok"],
                 "transport_events": [dict(event=kind, monotonic_ns=timestamp) for kind, timestamp in (
                     ("MASTER_TX_ORIGINAL", started), ("SLAVE_PTY_WRITE", tx_ns),
                     ("SLAVE_PTY_RESPONSE", raw_first), ("MASTER_RX", rx_ns),
                     ("LATE_QUARANTINE", quarantine_ns)) if timestamp is not None]}
        checked.update(status=status, error=error, matched=checked["matched"] and status == "PASS",
                       sequence=seq, purpose=RULES[name].label, monotonic_ns=started,
                       tx_ns=tx_ns, rx_ns=rx_ns, finished_ns=time.monotonic_ns(),
                       latency_ms=(rx_ns - tx_ns) / 1e6 if rx_ns is not None and tx_ns is not None else None,
                       injection=audit)
        self.master.record(checked)
        self.note("injection", **audit, status=status, error=error,
                  observed_exception=checked["rx"].get("exception_code"))
        if caught is not None:
            if not isinstance(caught, Exception):
                raise caught
            raise SessionTransportError(error) from caught
        return checked

    def run(self, name):
        call = self.master.call
        holding = call("read_holding_registers", 0, count=8, purpose="注入前状态").registers
        coils = call("read_coils", 0, count=8, purpose="注入前 GPIO").bits[:8]
        failed = self.exchange(name, original_request(name, holding))
        seq = failed["sequence"]
        recovery = self.master.sequence + 1
        state_unchanged = False
        recovered = False
        try:
            actual = call("read_holding_registers", 0, count=8, purpose="故障后 FC03",
                          recovery_of=seq).registers
            verified = call("read_coils", 0, count=8, purpose="故障后 GPIO").bits[:8]
            recovered = True
            state_unchanged = actual == holding and verified == coils
        finally:
            rule = RULES[name]
            expectation = (failed["status"] == rule.status and
                           failed["rx"].get("exception_code") == rule.exception)
            if rule.direction == "rx":
                injected = failed["injection"]
                expectation = (expectation and injected["slave_response_status"] == "PASS"
                               and injected["slave_tx_last_ns"] <= injected["host_deadline_ns"]
                               and bool(injected["rx_changes"]))
            result = {"sequence": seq, "rule": name, "observed": failed["status"],
                      "recovery_sequence": recovery, "recovered": recovered,
                      "state_unchanged": state_unchanged, "expectation_met": expectation}
            self.note("recovery", **result)
        return result
