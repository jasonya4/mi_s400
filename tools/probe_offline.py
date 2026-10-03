"""S400 離線資料試探腳本 (方法 A)

目的：
    嘗試對 S400 送出 MIoT「離線資料」相關請求，並把體脂計回傳的所有解密封包記錄下來，
    用來確認指令格式。

依據：
    1. 官方 MIoT 規格 (home.miot-spec.com/spec/yunmai.scales.ms104)
         siid 9  Offline data : action 1 = Request to report offline data
                                action 2 = End of reception   <-- 本腳本「絕不」送出
                                property 3 = Number of offline data entries
         siid 13 Sync         : action 1 = sync, property 6 = Number of offline messages
    2. 從已收到的 final 幀推測的明文格式（長度欄位已驗證吻合）：
         5d | 20 | 0e 00 | 07 | 08 | 02 00 | 01 | 02 00 | 50 a0 | <80 bytes ascii>
         LL   ?    seq     op   siid  eiid   n    piid    TL(type<<12|len)
       op 0x07 推測為 "event"；本腳本假設 action = 0x05、get_property = 0x00。
       這些都是推測，所以會嘗試多種變體並把結果全部記錄下來。

安全性：
    只送 get_property 與 action（siid 13/1 sync、siid 9/1 request）。
    不送 set_property、不送 siid 9 action 2，因此不會清除秤內暫存資料。

使用方式：
    1. 關閉手機藍牙或米家 App（避免手機先把離線資料同步走）
    2. 執行 probe_offline.bat
    3. 看到「正在搜尋」時站上體脂計喚醒它，量完可以下秤
    4. 結束後把 data/probe_log.txt 的內容貼回來分析
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import yaml
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakBluetoothNotAvailableError, BleakError

from xiaomi_s400_live.auth import login, make_notify_hub
from xiaomi_s400_live.crypto import SessionKeys, decrypt_cmtp, encrypt_for_device
from xiaomi_s400_live.protocol import (
    AVCTP, AVDTP, CMTP, RCV_OK, RCV_RDY, UPNP, VEND1A, VEND1C,
)

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "probe_log.txt"
LISTEN_AFTER_PROBES_SEC = 40

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

OP_NAMES = {
    0x00: "get_property?", 0x01: "get_property_rsp?", 0x02: "set_property?",
    0x03: "set_property_rsp?", 0x04: "property_changed?", 0x05: "action?",
    0x06: "action_rsp?", 0x07: "event?",
}
CHAR_NAMES = {CMTP: "CMTP(1b)", VEND1A: "VEND1A(1a)", VEND1C: "VEND1C(1c)"}


class Logger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "a", encoding="utf-8")
        self.w(f"===== probe start {datetime.now():%Y-%m-%d %H:%M:%S} =====")

    def w(self, msg: str) -> None:
        line = f"[{datetime.now():%H:%M:%S.%f}"[:-3] + f"] {msg}"
        print(line)
        self.f.write(line + "\n")
        self.f.flush()


def describe_plaintext(pt: bytes) -> str:
    """盡力解析明文；格式是推測的，解析失敗也會保留原始 hex。"""
    try:
        if len(pt) < 5:
            return "too short"
        ll, flag, seq, op = pt[0], pt[1], pt[2] | (pt[3] << 8), pt[4]
        out = [f"len={ll}(actual {len(pt)}) flag=0x{flag:02x} seq={seq} "
               f"op=0x{op:02x}({OP_NAMES.get(op, '?')})"]
        if op in (0x05, 0x06, 0x07) and len(pt) >= 9:
            siid, iid, n = pt[5], pt[6] | (pt[7] << 8), pt[8]
            out.append(f"siid={siid} iid={iid} nparam={n}")
            i = 9
            for _ in range(n):
                piid = pt[i] | (pt[i + 1] << 8)
                tl = pt[i + 2] | (pt[i + 3] << 8)
                typ, ln = tl >> 12, tl & 0x0FFF
                val = pt[i + 4:i + 4 + ln]
                txt = val.decode("ascii", "replace") if typ == 0xA else val.hex()
                out.append(f"  piid={piid} type=0x{typ:x} len={ln} value={txt}")
                i += 4 + ln
        return "\n    ".join(out)
    except Exception as exc:  # noqa: BLE001
        return f"parse error: {exc}"


class Prober:
    def __init__(self, client: BleakClient, keys: SessionKeys, log: Logger):
        self.client = client
        self.keys = keys
        self.log = log
        self.acks: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
        self.app_iter = 0
        self.seq = 1
        self.rx_type: int | None = None
        self.decrypted_count = 0

    # ---------- 接收 (device -> app) ----------
    async def pump(self, uuid: str, q: asyncio.Queue[bytes]) -> None:
        name = CHAR_NAMES.get(uuid, uuid[:8])
        expected, buf = 0, b""
        while True:
            data = await q.get()
            if data in (RCV_RDY, RCV_OK):
                self.log.w(f"<- {name} ACK {data.hex()}")
                await self.acks.put((uuid, data))
                continue
            if len(data) >= 6 and data[:3] == b"\x00\x00\x00" and data[5] == 0:
                expected, buf = data[4], b""
                if self.rx_type is None:
                    self.rx_type = data[3]
                self.log.w(f"<- {name} header type=0x{data[3]:02x} frames={expected}")
                await self.client.write_gatt_char(uuid, RCV_RDY, response=False)
                continue
            if len(data) >= 2 and data[1] == 0 and expected > 0:
                buf += data[2:]
                if data[0] >= expected:
                    pt = decrypt_cmtp(self.keys, buf)
                    if pt is None:
                        self.log.w(f"<- {name} DECRYPT FAIL raw={buf.hex()}")
                    else:
                        self.decrypted_count += 1
                        self.log.w(f"<- {name} PLAINTEXT {pt.hex()}\n    {describe_plaintext(pt)}")
                    await self.client.write_gatt_char(uuid, RCV_OK, response=False)
                    expected, buf = 0, b""
                continue
            self.log.w(f"<- {name} OTHER {data.hex()}")

    async def _wait_ack(self, want: bytes, timeout: float) -> bool:
        try:
            while True:
                _, data = await asyncio.wait_for(self.acks.get(), timeout)
                if data == want:
                    return True
        except asyncio.TimeoutError:
            return False

    # ---------- 傳送 (app -> device) ----------
    async def send(self, label: str, body: bytes, uuid: str, flag: int = 0x20,
                   frame_type: int | None = None) -> bool:
        seq = self.seq
        self.seq += 1
        inner = bytes([flag, seq & 0xFF, (seq >> 8) & 0xFF]) + body
        pt = bytes([len(inner) + 1]) + inner
        enc = encrypt_for_device(self.keys, self.app_iter, pt)
        self.app_iter += 1

        ftype = frame_type if frame_type is not None else (self.rx_type or 0x00)
        chunks = [enc[i:i + 18] for i in range(0, len(enc), 18)]
        header = bytes([0, 0, 0, ftype, len(chunks) & 0xFF, (len(chunks) >> 8) & 0xFF])
        name = CHAR_NAMES.get(uuid, uuid[:8])
        self.log.w(f"-> {name} [{label}] plaintext={pt.hex()} header={header.hex()}")

        # 清掉殘留 ack
        while not self.acks.empty():
            self.acks.get_nowait()
        try:
            await self.client.write_gatt_char(uuid, header, response=False)
        except Exception as exc:  # noqa: BLE001
            self.log.w(f"   write header failed: {exc}")
            return False
        if not await self._wait_ack(RCV_RDY, 3.0):
            self.log.w("   no RCV_RDY (device did not accept header)")
            return False
        for n, chunk in enumerate(chunks, start=1):
            await self.client.write_gatt_char(uuid, bytes([n & 0xFF, n >> 8]) + chunk, response=False)
            await asyncio.sleep(0.05)
        ok = await self._wait_ack(RCV_OK, 3.0)
        self.log.w(f"   {'RCV_OK received' if ok else 'no RCV_OK'}")
        return ok


async def connect(mac: str, log: Logger) -> BleakClient:
    last4 = mac.replace(":", "")[-4:].lower()

    def matcher(dev, adv) -> bool:
        if dev.address.upper() == mac:
            return True
        return last4 in (adv.local_name or dev.name or "").lower()

    log.w(f"正在搜尋體脂計 {mac} ... 請現在站上體脂計喚醒它")
    dev = None
    for _ in range(6):  # 最多約 2 分鐘
        dev = await BleakScanner.find_device_by_filter(matcher, timeout=20.0)
        if dev:
            break
        log.w("  尚未找到，繼續搜尋 ...")
    if not dev:
        raise RuntimeError("找不到體脂計")
    client = BleakClient(dev, timeout=35.0)
    await client.connect()
    log.w("已連線")
    return client


async def main() -> None:
    cfg = yaml.safe_load(open(ROOT / "config.yaml", encoding="utf-8"))
    mac = cfg["device"]["mac"].upper()
    token = bytes.fromhex(cfg["device"]["token"])
    log = Logger(LOG_PATH)

    try:
        client = await connect(mac, log)
    except BleakBluetoothNotAvailableError:
        log.w("❌ 錯誤：電腦的 Windows 藍牙尚未開啟！請在 Windows 設定中打開藍牙後再試。")
        log.w("   （提醒：關閉藍牙是指關閉『手機』的藍牙，電腦本身的藍牙必須保持『開啟』）")
        return
    except Exception as exc:
        log.w(f"❌ 連線失敗：{exc}")
        return
    hub = make_notify_hub()
    for uuid in (UPNP, AVDTP, AVCTP, VEND1A, CMTP, VEND1C):
        try:
            await client.start_notify(uuid, hub.make_callback(uuid))
        except Exception as exc:  # noqa: BLE001
            log.w(f"notify {uuid[:8]} failed: {exc}")
    await asyncio.sleep(0.3)

    keys = await login(client, token, hub)
    log.w("登入成功 (session keys derived)")

    prober = Prober(client, keys, log)
    pumps = [asyncio.create_task(prober.pump(u, hub.queue(u))) for u in (CMTP, VEND1A, VEND1C)]

    # 先等 3 秒，收一點秤主動送的幀，順便學到 device 使用的 frame type
    await asyncio.sleep(3)
    log.w(f"device frame type = {prober.rx_type}")

    # 試探清單（全部唯讀／請求類）
    probes = [
        # get_property? : [op][count]([siid][piid LE16])...
        ("get_prop 13.6 + 9.3 (offline count)", bytes([0x00, 0x02, 13, 6, 0, 9, 3, 0])),
        # action? : [op][siid][aiid LE16][nparam]
        ("action 13.1 sync", bytes([0x05, 13, 1, 0, 0])),
        ("action 9.1 request offline data", bytes([0x05, 9, 1, 0, 0])),
    ]

    for uuid in (CMTP, VEND1A):
        for label, body in probes:
            if not client.is_connected:
                break
            await prober.send(label, body, uuid)
            await asyncio.sleep(3)  # 給秤時間回應
        if prober.decrypted_count and not client.is_connected:
            break

    log.w(f"試探送出完畢，持續監聽 {LISTEN_AFTER_PROBES_SEC} 秒 ...")
    for _ in range(LISTEN_AFTER_PROBES_SEC):
        if not client.is_connected:
            log.w("體脂計已斷線")
            break
        await asyncio.sleep(1)

    for t in pumps:
        t.cancel()
    if client.is_connected:
        await client.disconnect()
    log.w(f"===== probe end, decrypted frames = {prober.decrypted_count} =====")
    print(f"\n記錄檔：{LOG_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
