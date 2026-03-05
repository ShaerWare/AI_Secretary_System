"""
GSM Service for SIM7600E-H modem integration.

Handles AT commands, call management, and SMS via serial port.
Auto-switches to mock mode when hardware is not available.

AT port: /dev/ttyUSB2 (115200 baud)
Audio port: /dev/ttyUSB4 (future PR)
"""

import asyncio
import logging
import re
import time as _time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


try:
    import serial
    import serial.tools.list_ports

    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False


logger = logging.getLogger(__name__)


# ============== Data Classes ==============


@dataclass
class CallInfo:
    """Active call tracking."""

    id: str
    direction: str  # incoming / outgoing
    caller_number: str
    state: str  # ringing / active / completed / missed / failed
    started_at: datetime
    answered_at: Optional[datetime] = None


@dataclass
class GSMStatus:
    """GSM module status snapshot."""

    state: str = "disconnected"
    signal_strength: Optional[int] = None  # 0-31, 99=unknown
    signal_percent: Optional[int] = None
    sim_status: Optional[str] = None
    network_name: Optional[str] = None
    network_registered: bool = False
    phone_number: Optional[str] = None
    module_info: Optional[str] = None
    last_error: Optional[str] = None
    mock_mode: bool = False
    network_mode: Optional[str] = None  # GSM, HSDPA, LTE, etc

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "signal_strength": self.signal_strength,
            "signal_percent": self.signal_percent,
            "sim_status": self.sim_status,
            "network_name": self.network_name,
            "network_registered": self.network_registered,
            "phone_number": self.phone_number,
            "module_info": self.module_info,
            "last_error": self.last_error,
            "mock_mode": self.mock_mode,
            "network_mode": self.network_mode,
        }


# ============== Main Service ==============


class GSMService:
    """
    GSM Service for SIM7600E-H modem.

    Features:
    - AT command communication via serial port
    - Call management (dial, answer, hangup)
    - SMS sending and listing
    - Background monitoring for incoming calls (RING detection)
    - Mock mode when hardware unavailable
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB2",
        baud_rate: int = 115200,
        mock_mode: bool = False,
    ):
        self.port = port
        self.baud_rate = baud_rate
        self._force_mock = mock_mode

        # Serial connection (sync pyserial, wrapped in executor for async)
        self._serial: Optional["serial.Serial"] = None
        self._serial_lock = asyncio.Lock()

        # State
        self.state: str = "disconnected"
        self.active_call: Optional[CallInfo] = None
        self.last_error: Optional[str] = None

        # Background monitor
        self._monitor_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        # Callbacks (set by router/orchestrator)
        self.on_incoming_call: Optional[Callable] = None
        self.on_call_ended: Optional[Callable] = None
        self.on_sms_received: Optional[Callable] = None

        logger.info(f"📞 GSMService created: port={port}, baud={baud_rate}")

    @property
    def mock_mode(self) -> bool:
        """True when running without real hardware."""
        return self._force_mock or not PYSERIAL_AVAILABLE or self._serial is None

    # ================================================================
    # Lifecycle
    # ================================================================

    async def initialize(self) -> bool:
        """Initialize GSM modem. Returns True on success."""
        logger.info("📞 Initializing GSM modem...")
        self.state = "initializing"

        if self._force_mock or not PYSERIAL_AVAILABLE:
            reason = "forced" if self._force_mock else "pyserial not installed"
            logger.info(f"📞 GSM mock mode ({reason})")
            self.state = "ready"
            return True

        # Check port exists
        if not Path(self.port).exists():
            logger.warning(f"⚠️ Serial port {self.port} not found — mock mode")
            self.state = "ready"
            return True

        # Open serial port
        try:
            loop = asyncio.get_event_loop()
            self._serial = await loop.run_in_executor(
                None,
                lambda: serial.Serial(
                    port=self.port,
                    baudrate=self.baud_rate,
                    timeout=1,
                    write_timeout=2,
                ),
            )

            await asyncio.sleep(0.5)  # Let port settle

            # Test basic AT command
            ok, _ = await self.execute_at("AT")
            if not ok:
                logger.error("❌ Modem not responding to AT")
                self.state = "error"
                self.last_error = "Modem not responding"
                return False

            # Verbose error messages
            await self.execute_at("AT+CMEE=2")
            # Enable caller ID display
            await self.execute_at("AT+CLIP=1")
            # Extended ring format (+CRING instead of RING)
            await self.execute_at("AT+CRC=1")
            # Force 2G/3G — SMS and voice do NOT work on LTE
            await self.execute_at("AT+CNMP=14")
            # Operator name format: long alphanumeric
            await self.execute_at("AT+COPS=3,0")
            # SMS PDU mode (required for Cyrillic UCS2)
            await self.execute_at("AT+CMGF=0")
            # New SMS notification to TE
            await self.execute_at("AT+CNMI=2,1,0,0,0")
            # Clean old SMS from SIM (only 15 slots!)
            await self.execute_at("AT+CMGD=1,4")

            self.state = "ready"
            logger.info("✅ GSM modem initialized")

            # Start background monitor
            self._start_monitor()
            return True

        except Exception as e:
            logger.error(f"❌ GSM init failed: {e}")
            self.state = "error"
            self.last_error = str(e)
            return False

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("📞 Shutting down GSM service...")
        self._stop_event.set()

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if self._serial and self._serial.is_open:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._serial.close)

        self.state = "disconnected"
        logger.info("✅ GSM service shut down")

    # ================================================================
    # AT Command Layer
    # ================================================================

    async def execute_at(
        self,
        command: str,
        timeout: float = 5.0,
    ) -> Tuple[bool, List[str]]:
        """
        Send AT command and read response.

        Returns (success, response_lines).
        """
        if self.mock_mode:
            return await self._mock_at(command)

        async with self._serial_lock:
            try:
                loop = asyncio.get_event_loop()
                lines = await asyncio.wait_for(
                    loop.run_in_executor(None, self._serial_send, command),
                    timeout=timeout,
                )
                success = any("OK" in ln for ln in lines)
                has_error = any(
                    ln.startswith("ERROR") or ln.startswith("+CME ERROR") for ln in lines
                )

                if has_error:
                    success = False

                logger.debug(f"AT [{command}] → {lines}")
                return success, lines

            except asyncio.TimeoutError:
                logger.warning(f"AT timeout: {command}")
                return False, [f"TIMEOUT after {timeout}s"]
            except Exception as e:
                logger.error(f"AT error: {e}")
                return False, [f"ERROR: {e}"]

    def _serial_send(self, command: str) -> List[str]:
        """Blocking serial send+receive (runs in executor)."""
        assert self._serial is not None
        # Flush input buffer
        self._serial.reset_input_buffer()

        # Send command
        self._serial.write((command + "\r\n").encode("utf-8"))

        # Read response lines until OK/ERROR
        lines: List[str] = []
        while True:
            raw = self._serial.readline()
            if not raw:
                break  # Timeout (no more data)

            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            lines.append(line)

            if line in ("OK", "ERROR") or line.startswith("+CME ERROR"):
                break

        return lines

    # ================================================================
    # Status
    # ================================================================

    async def get_status(self) -> GSMStatus:
        """Query modem for current status."""
        status = GSMStatus(state=self.state, mock_mode=self.mock_mode)

        if self.state not in ("ready", "incoming_call", "in_call"):
            status.last_error = self.last_error
            return status

        # SIM status
        ok, lines = await self.execute_at("AT+CPIN?")
        if ok:
            for ln in lines:
                if "+CPIN:" in ln:
                    status.sim_status = ln.split(":")[1].strip()

        # Signal strength
        ok, lines = await self.execute_at("AT+CSQ")
        if ok:
            for ln in lines:
                if "+CSQ:" in ln:
                    try:
                        rssi = int(ln.split(":")[1].split(",")[0].strip())
                        if rssi != 99:
                            status.signal_strength = rssi
                            status.signal_percent = min(int((rssi / 31) * 100), 100)
                    except (ValueError, IndexError):
                        pass

        # Network registration
        ok, lines = await self.execute_at("AT+CREG?")
        if ok:
            for ln in lines:
                if "+CREG:" in ln:
                    try:
                        parts = ln.split(",")
                        if len(parts) >= 2:
                            stat = int(parts[1].strip())
                            status.network_registered = stat in (1, 5)
                    except (ValueError, IndexError):
                        pass

        # Operator name
        ok, lines = await self.execute_at("AT+COPS?")
        if ok:
            for ln in lines:
                if "+COPS:" in ln:
                    # Try quoted: +COPS: 0,0,"MegaFon",2
                    match = re.search(r'"([^"]+)"', ln)
                    if match:
                        status.network_name = match.group(1)
                    else:
                        # Unquoted: +COPS: 0,0,MegaFon,2
                        parts = ln.split(",")
                        if len(parts) >= 3:
                            status.network_name = parts[2].strip()

        # Own phone number
        ok, lines = await self.execute_at("AT+CNUM")
        if ok:
            for ln in lines:
                if "+CNUM:" in ln:
                    # Find phone number (second quoted field usually)
                    numbers = re.findall(r'"(\+?[0-9]+)"', ln)
                    if numbers:
                        status.phone_number = numbers[0]

        # Module info
        ok, lines = await self.execute_at("ATI")
        if ok:
            info_lines = [ln for ln in lines if ln not in ("OK", "") and not ln.startswith("AT")]
            if info_lines:
                status.module_info = " / ".join(info_lines)

        # Network mode (GSM/HSDPA/LTE)
        status.network_mode = await self.get_network_mode()

        status.last_error = self.last_error
        return status

    # ================================================================
    # Call Management
    # ================================================================

    async def dial(self, number: str) -> Tuple[bool, str]:
        """
        Dial a number. Returns (success, call_id_or_error).
        """
        if self.active_call:
            return False, "Уже есть активный звонок"

        logger.info(f"📞 Набираем {number}...")
        ok, lines = await self.execute_at(f"ATD{number};", timeout=30.0)

        if ok:
            call_id = f"call_{uuid.uuid4().hex[:12]}"
            self.active_call = CallInfo(
                id=call_id,
                direction="outgoing",
                caller_number=number,
                state="ringing",
                started_at=datetime.utcnow(),
            )
            self.state = "in_call"
            logger.info(f"✅ Звонок инициирован: {call_id}")
            return True, call_id
        else:
            error = " ".join(lines) if lines else "Не удалось позвонить"
            logger.warning(f"❌ Не удалось позвонить на {number}: {error}")
            return False, error

    async def answer(self) -> bool:
        """Answer incoming call."""
        if not self.active_call or self.active_call.state != "ringing":
            return False

        logger.info(f"📞 Отвечаем на звонок от {self.active_call.caller_number}...")
        ok, _ = await self.execute_at("ATA")

        if ok:
            self.active_call.state = "active"
            self.active_call.answered_at = datetime.utcnow()
            self.state = "in_call"
            logger.info("✅ Звонок принят")
            return True

        return False

    async def hangup(self) -> bool:
        """Hang up current call."""
        logger.info("📞 Завершаем звонок...")
        ok, _ = await self.execute_at("ATH")

        if ok and self.active_call:
            ended_call = self.active_call
            self.active_call = None
            self.state = "ready"
            logger.info("✅ Звонок завершён")

            if self.on_call_ended:
                try:
                    self.on_call_ended(ended_call)
                except Exception as e:
                    logger.error(f"on_call_ended callback error: {e}")
            return True

        return ok

    def get_active_call(self) -> Optional[Dict]:
        """Get active call info as dict."""
        if not self.active_call:
            return None

        now = datetime.utcnow()
        duration = int((now - self.active_call.started_at).total_seconds())
        return {
            "id": self.active_call.id,
            "direction": self.active_call.direction,
            "caller_number": self.active_call.caller_number,
            "state": self.active_call.state,
            "started_at": self.active_call.started_at.isoformat(),
            "duration_seconds": duration,
            "transcript": [],
        }

    # ================================================================
    # SMS
    # ================================================================

    # GSM 7-bit default alphabet characters (basic set)
    _GSM7_CHARS = set(
        "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ ÆæßÉ"
        " !\"#¤%&'()*+,-./0123456789:;<=>?"
        "¡ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "ÄÖÑÜabcdefghijklmnopqrstuvwxyz"
        "äöñüà§"
    )

    # GSM 7-bit default alphabet for decoding (128 entries, index = septet value)
    _GSM7_DECODE_TABLE = (
        "@£$¥èéùìòÇ\nØø\rÅå"
        "Δ_ΦΓΛΩΠΨΣΘΞ ÆæßÉ"
        " !\"#¤%&'()*+,-./0123456789:;<=>?"
        "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
        "¿abcdefghijklmnopqrstuvwxyzäöñüà"
    )

    @staticmethod
    def _is_gsm7(text: str) -> bool:
        """Check if text can be encoded in GSM 7-bit alphabet."""
        return all(c in GSMService._GSM7_CHARS for c in text)

    @staticmethod
    def _encode_phone_pdu(number: str) -> Tuple[str, str]:
        """
        Encode phone number for PDU.
        Returns (type_byte_hex, encoded_number_hex).
        """
        if number.startswith("+"):
            type_byte = "91"  # International
            digits = number[1:]
        else:
            type_byte = "81"  # National/unknown
            digits = number

        # Swap nibbles: "79826312267" → "97286132267F"
        if len(digits) % 2 != 0:
            digits += "F"
        swapped = ""
        for i in range(0, len(digits), 2):
            swapped += digits[i + 1] + digits[i]
        return type_byte, swapped

    @staticmethod
    def _build_sms_pdu(number: str, text: str) -> Tuple[str, int]:
        """
        Build SMS-SUBMIT PDU with UCS2 encoding.
        Returns (full_pdu_hex, tpdu_length).
        """
        # SCA (Service Center Address) — use default (00)
        sca = "00"

        # PDU type: SMS-SUBMIT, VPF=00 (no validity period)
        pdu_type = "01"
        # Message reference (auto)
        mr = "00"

        # Destination address
        raw_number = number.lstrip("+")
        addr_len = f"{len(raw_number):02X}"
        type_byte, encoded_number = GSMService._encode_phone_pdu(number)

        # Protocol ID
        pid = "00"
        # Data Coding Scheme: UCS2 (16-bit)
        dcs = "08"

        # User Data: encode text as UCS2 (big-endian UTF-16)
        ud_bytes = text.encode("utf-16-be")
        ud_len = f"{len(ud_bytes):02X}"
        ud_hex = ud_bytes.hex().upper()

        # Build TPDU (everything after SCA)
        tpdu = pdu_type + mr + addr_len + type_byte + encoded_number + pid + dcs + ud_len + ud_hex

        # Full PDU = SCA + TPDU
        full_pdu = sca + tpdu

        # TPDU length in octets (bytes) = len(tpdu) / 2
        tpdu_len = len(tpdu) // 2

        return full_pdu, tpdu_len

    async def send_sms(self, number: str, text: str) -> Tuple[bool, Optional[str]]:
        """Send SMS. Uses text mode + UCS2 charset for Cyrillic, plain text mode for ASCII."""
        logger.info(f"📱 Отправляем SMS на {number}...")

        if self.mock_mode:
            await asyncio.sleep(0.3)
            logger.info("✅ SMS отправлено (mock)")
            return True, None

        use_ucs2 = not self._is_gsm7(text)

        async with self._serial_lock:
            try:
                loop = asyncio.get_event_loop()
                if use_ucs2:
                    logger.info(f"📱 Text mode + CSCS=UCS2 ({len(text)} chars)")
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, self._serial_send_sms_ucs2, number, text),
                        timeout=30.0,
                    )
                else:
                    logger.info("📱 Text mode (GSM7)")
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, self._serial_send_sms_text, number, text),
                        timeout=30.0,
                    )

                if result:
                    logger.info("✅ SMS отправлено")
                    return True, None
                else:
                    return False, "SMS отправка не удалась"
            except asyncio.TimeoutError:
                return False, "Таймаут отправки SMS"
            except Exception as e:
                logger.error(f"SMS error: {e}")
                return False, str(e)

    def _serial_send_sms_text(self, number: str, text: str) -> bool:
        """Send SMS in text mode (ASCII only). Runs in executor."""
        assert self._serial is not None
        self._serial.reset_input_buffer()

        # Switch to text mode
        self._serial.write(b"AT+CMGF=1\r\n")
        _time.sleep(0.3)
        self._serial.reset_input_buffer()

        self._serial.write(f'AT+CMGS="{number}"\r\n'.encode("utf-8"))

        deadline = _time.time() + 5
        while _time.time() < deadline:
            raw = self._serial.readline()
            if b">" in raw:
                break
        else:
            return False

        self._serial.write((text + chr(26)).encode("utf-8"))

        deadline = _time.time() + 30
        while _time.time() < deadline:
            raw = self._serial.readline()
            line = raw.decode("utf-8", errors="ignore").strip()
            if "OK" in line or "+CMGS:" in line:
                return True
            if "ERROR" in line:
                return False

        return False

    def _serial_send_sms_ucs2(self, number: str, text: str) -> bool:
        """Send SMS in text mode with UCS2 charset (for Cyrillic/CJK). Runs in executor."""
        assert self._serial is not None
        self._serial.reset_input_buffer()

        # Switch to text mode
        self._serial.write(b"AT+CMGF=1\r\n")
        _time.sleep(0.3)
        self._serial.reset_input_buffer()

        # Set UCS2 character set
        self._serial.write(b'AT+CSCS="UCS2"\r\n')
        _time.sleep(0.3)
        self._serial.reset_input_buffer()

        # Encode phone number as UCS2 hex: "+79..." → "002B0037003900..."
        ucs2_number = number.encode("utf-16-be").hex().upper()
        logger.info(f"📱 UCS2 number: {ucs2_number}")

        self._serial.write(f'AT+CMGS="{ucs2_number}"\r\n'.encode("utf-8"))

        deadline = _time.time() + 5
        while _time.time() < deadline:
            raw = self._serial.readline()
            line = raw.decode("utf-8", errors="ignore").strip()
            logger.debug(f"📱 CMGS response: {line!r}")
            if b">" in raw:
                break
        else:
            logger.error("UCS2 SMS: no '>' prompt received")
            # Reset charset back to GSM
            self._serial.write(b'AT+CSCS="GSM"\r\n')
            _time.sleep(0.2)
            return False

        # Encode text as UCS2 hex: "Тест" → "0422043504410442"
        ucs2_text = text.encode("utf-16-be").hex().upper()
        logger.info(f"📱 UCS2 text ({len(ucs2_text)} hex chars): {ucs2_text[:40]}...")

        # Send UCS2-encoded text + Ctrl+Z
        self._serial.write((ucs2_text + chr(26)).encode("utf-8"))

        deadline = _time.time() + 30
        while _time.time() < deadline:
            raw = self._serial.readline()
            line = raw.decode("utf-8", errors="ignore").strip()
            if line:
                logger.debug(f"📱 Send response: {line!r}")
            if "+CMGS:" in line or "OK" in line:
                # Reset charset back to GSM
                self._serial.write(b'AT+CSCS="GSM"\r\n')
                _time.sleep(0.2)
                return True
            if "ERROR" in line or "+CMS ERROR" in line:
                logger.error(f"UCS2 SMS error: {line}")
                self._serial.write(b'AT+CSCS="GSM"\r\n')
                _time.sleep(0.2)
                return False

        # Timeout — reset charset
        self._serial.write(b'AT+CSCS="GSM"\r\n')
        _time.sleep(0.2)
        return False

    def _serial_send_sms_pdu(self, pdu_hex: str, tpdu_len: int) -> bool:
        """Send SMS in PDU mode (UCS2 for Cyrillic). Runs in executor."""
        assert self._serial is not None
        self._serial.reset_input_buffer()

        # Ensure PDU mode
        self._serial.write(b"AT+CMGF=0\r\n")
        _time.sleep(0.3)
        self._serial.reset_input_buffer()

        # Send AT+CMGS=<tpdu_length>
        self._serial.write(f"AT+CMGS={tpdu_len}\r\n".encode("utf-8"))

        deadline = _time.time() + 5
        while _time.time() < deadline:
            raw = self._serial.readline()
            if b">" in raw:
                break
        else:
            logger.error("PDU SMS: no '>' prompt received")
            return False

        # Send PDU hex + Ctrl+Z
        self._serial.write((pdu_hex + chr(26)).encode("utf-8"))

        deadline = _time.time() + 30
        while _time.time() < deadline:
            raw = self._serial.readline()
            line = raw.decode("utf-8", errors="ignore").strip()
            if "+CMGS:" in line or "OK" in line:
                return True
            if "ERROR" in line or "+CMS ERROR" in line:
                logger.error(f"PDU SMS error: {line}")
                return False

        return False

    @staticmethod
    def _unpack_gsm7(data: bytes, num_chars: int) -> str:
        """Unpack GSM 7-bit packed data into a string."""
        result = []
        bit_pos = 0
        for _ in range(num_chars):
            byte_idx = bit_pos // 8
            bit_shift = bit_pos % 8
            if byte_idx >= len(data):
                break
            if bit_shift <= 1:
                char_code = (data[byte_idx] >> bit_shift) & 0x7F
            else:
                char_code = data[byte_idx] >> bit_shift
                if byte_idx + 1 < len(data):
                    char_code |= data[byte_idx + 1] << (8 - bit_shift)
                char_code &= 0x7F
            bit_pos += 7
            if 0 <= char_code < len(GSMService._GSM7_DECODE_TABLE):
                result.append(GSMService._GSM7_DECODE_TABLE[char_code])
            else:
                result.append("?")
        return "".join(result)

    @staticmethod
    def _decode_sms_pdu(pdu_hex: str) -> Dict:
        """
        Decode an SMS-DELIVER PDU hex string.
        Returns dict with 'number', 'text', and optionally 'timestamp'.
        """
        data = bytes.fromhex(pdu_hex)
        pos = 0

        # SCA (Service Center Address) — skip
        sca_len = data[pos]
        pos += 1 + sca_len

        # PDU type byte
        pos += 1

        # Originating Address — number of digits
        oa_digit_count = data[pos]
        pos += 1
        oa_type = data[pos]
        pos += 1

        # Decode phone number (BCD swap-nibble)
        oa_byte_count = (oa_digit_count + 1) // 2
        number_digits = ""
        for b in data[pos : pos + oa_byte_count]:
            lo = b & 0x0F
            hi = (b >> 4) & 0x0F
            number_digits += str(lo)
            if hi != 0x0F:
                number_digits += str(hi)
        number = ("+" if oa_type == 0x91 else "") + number_digits
        pos += oa_byte_count

        # PID
        pos += 1

        # DCS (Data Coding Scheme)
        dcs = data[pos]
        pos += 1

        # SCTS — 7 bytes BCD timestamp
        scts = data[pos : pos + 7]
        pos += 7

        def bcd_byte(b: int) -> int:
            return (b & 0x0F) * 10 + ((b >> 4) & 0x0F)

        try:
            timestamp = datetime(
                2000 + bcd_byte(scts[0]),
                bcd_byte(scts[1]),
                bcd_byte(scts[2]),
                bcd_byte(scts[3]),
                bcd_byte(scts[4]),
                bcd_byte(scts[5]),
            ).isoformat()
        except Exception:
            timestamp = None

        # UDL (User Data Length)
        udl = data[pos]
        pos += 1

        # UD (User Data)
        ud_bytes = data[pos:]

        # Decode based on DCS bits 3-2 (encoding)
        encoding_bits = (dcs >> 2) & 0x03
        if encoding_bits == 2:  # UCS2
            text = ud_bytes[:udl].decode("utf-16-be", errors="replace")
        elif encoding_bits == 0:  # GSM 7-bit
            text = GSMService._unpack_gsm7(ud_bytes, udl)
        else:  # 8-bit or other
            text = ud_bytes[:udl].decode("latin-1", errors="replace")

        result: Dict = {"number": number, "text": text}
        if timestamp:
            result["timestamp"] = timestamp
        return result

    async def list_sms_from_modem(self, status: str = "ALL") -> List[Dict]:
        """List SMS stored on modem (text mode). Returns parsed list."""
        ok, lines = await self.execute_at(f'AT+CMGL="{status}"', timeout=10.0)
        if not ok:
            return []

        messages: List[Dict] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("+CMGL:"):
                # +CMGL: index,"status","number","name","date"
                text = lines[i + 1] if i + 1 < len(lines) else ""
                match = re.search(r'"(\+?[0-9]+)"', line)
                number = match.group(1) if match else "unknown"
                messages.append(
                    {
                        "number": number,
                        "text": text,
                        "raw_header": line,
                    }
                )
                i += 2
            else:
                i += 1

        return messages

    # ================================================================
    # Background Monitor
    # ================================================================

    def _start_monitor(self) -> None:
        """Start background serial monitor."""
        if not self._monitor_task or self._monitor_task.done():
            self._stop_event.clear()
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            logger.info("📡 GSM background monitor started")

    async def _monitor_loop(self) -> None:
        """Read serial port for unsolicited messages (RING, SMS, etc.)."""
        while not self._stop_event.is_set():
            try:
                # Skip reading while an AT command holds the lock
                if self._serial_lock.locked():
                    await asyncio.sleep(0.1)
                    continue

                if self._serial and self._serial.is_open and self._serial.in_waiting > 0:
                    loop = asyncio.get_event_loop()
                    raw = await loop.run_in_executor(None, self._serial.readline)
                    line = raw.decode("utf-8", errors="ignore").strip()

                    if not line:
                        pass
                    elif "RING" in line or "+CRING:" in line:
                        await self._handle_ring()
                    elif "+CLIP:" in line:
                        self._handle_clip(line)
                    elif "NO CARRIER" in line:
                        await self._handle_no_carrier()
                    elif "+CMT:" in line or "+CMTI:" in line:
                        self._handle_incoming_sms(line)
                    elif "VOICE CALL: END" in line:
                        await self._handle_no_carrier()

                await asyncio.sleep(0.2)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(1)

    async def _handle_ring(self) -> None:
        """Handle incoming RING."""
        if self.active_call and self.active_call.state == "ringing":
            return  # Already tracking this call

        call_id = f"call_{uuid.uuid4().hex[:12]}"
        self.active_call = CallInfo(
            id=call_id,
            direction="incoming",
            caller_number="Unknown",
            state="ringing",
            started_at=datetime.utcnow(),
        )
        self.state = "incoming_call"
        logger.info(f"📞 Входящий звонок: {call_id}")

        if self.on_incoming_call:
            try:
                self.on_incoming_call(self.active_call)
            except Exception as e:
                logger.error(f"on_incoming_call callback error: {e}")

    def _handle_clip(self, line: str) -> None:
        """Handle +CLIP (caller ID) — update active call number."""
        if self.active_call and self.active_call.caller_number == "Unknown":
            match = re.search(r'"(\+?[0-9]+)"', line)
            if match:
                self.active_call.caller_number = match.group(1)
                logger.info(f"📞 Caller ID: {self.active_call.caller_number}")

    async def _handle_no_carrier(self) -> None:
        """Handle NO CARRIER — call ended by remote side."""
        if self.active_call:
            ended_call = self.active_call
            was_ringing = ended_call.state == "ringing"
            self.active_call = None
            self.state = "ready"

            state = "missed" if was_ringing else "completed"
            logger.info(f"📞 Звонок завершён (NO CARRIER): {state}")

            if self.on_call_ended:
                ended_call.state = state
                try:
                    self.on_call_ended(ended_call)
                except Exception as e:
                    logger.error(f"on_call_ended callback error: {e}")

    def _handle_incoming_sms(self, line: str) -> None:
        """Handle +CMT — new SMS received."""
        logger.info(f"📱 Новое SMS: {line}")
        if self.on_sms_received:
            try:
                self.on_sms_received(line)
            except Exception as e:
                logger.error(f"on_sms_received callback error: {e}")

    # ================================================================
    # SMS Read/Delete from SIM + DTMF + Network Mode
    # ================================================================

    NETWORK_MODES: Dict[int, str] = {
        0: "No service",
        1: "GSM",
        2: "GPRS",
        3: "EGPRS (EDGE)",
        4: "WCDMA",
        5: "HSDPA",
        6: "HSUPA",
        7: "HSDPA+HSUPA",
        8: "LTE",
        9: "TDS-CDMA",
        10: "TDS-HSDPA",
        11: "TDS-HSUPA",
        12: "TDS-HSDPA+HSUPA",
        13: "CDMA",
        14: "EVDO",
        15: "CDMA/EVDO",
        16: "CDMA/LTE",
        17: "EVDO/LTE",
        18: "CDMA/EVDO/LTE",
    }

    async def get_network_mode(self) -> Optional[str]:
        """Get current network access mode (GSM, HSDPA, LTE, etc)."""
        ok, lines = await self.execute_at("AT+CNSMOD?")
        if ok:
            for ln in lines:
                if "+CNSMOD:" in ln:
                    try:
                        mode_num = int(ln.split(",")[1].strip())
                        return self.NETWORK_MODES.get(mode_num, f"Unknown({mode_num})")
                    except (ValueError, IndexError):
                        pass
        return None

    async def read_sms(self, index: int) -> Optional[Dict]:
        """Read single SMS by index from SIM storage (PDU mode)."""
        await self.execute_at("AT+CMGF=0")
        ok, lines = await self.execute_at(f"AT+CMGR={index}", timeout=5.0)
        if not ok or not lines:
            return None

        for i, ln in enumerate(lines):
            if ln.startswith("+CMGR:"):
                if i + 1 < len(lines) and lines[i + 1] not in ("OK", ""):
                    pdu_hex = lines[i + 1].strip()
                    try:
                        msg = self._decode_sms_pdu(pdu_hex)
                        msg["index"] = index
                        return msg
                    except Exception as e:
                        logger.warning(f"Failed to decode PDU at index {index}: {e}")
                break
        return None

    async def read_all_sms(self) -> List[Dict]:
        """Read all SMS from SIM. Uses PDU mode for proper Cyrillic decoding."""
        await self.execute_at("AT+CMGF=0")
        # 4 = "ALL" in PDU mode
        ok, lines = await self.execute_at("AT+CMGL=4", timeout=10.0)
        if not ok:
            return []

        messages: List[Dict] = []
        i = 0
        while i < len(lines):
            if lines[i].startswith("+CMGL:"):
                if i + 1 < len(lines) and lines[i + 1] not in ("OK", ""):
                    pdu_hex = lines[i + 1].strip()
                    try:
                        msg = self._decode_sms_pdu(pdu_hex)
                        messages.append(msg)
                    except Exception as e:
                        logger.warning(f"Failed to decode PDU: {e}")
                i += 2
            else:
                i += 1

        return messages

    async def delete_sms(self, index: int) -> bool:
        """Delete a single SMS by index from SIM."""
        ok, _ = await self.execute_at(f"AT+CMGD={index}")
        return ok

    async def delete_all_sms(self) -> bool:
        """Delete all SMS from SIM storage."""
        ok, _ = await self.execute_at("AT+CMGD=1,4", timeout=10.0)
        return ok

    async def send_dtmf(self, digits: str) -> bool:
        """Send DTMF tones during an active call."""
        if not self.active_call or self.active_call.state != "active":
            return False

        for digit in digits:
            if digit in "0123456789*#ABCD":
                ok, _ = await self.execute_at(f'AT+VTS="{digit}"')
                if not ok:
                    return False
                await asyncio.sleep(0.3)
        return True

    # ================================================================
    # Mock AT Responses
    # ================================================================

    async def _mock_at(self, command: str) -> Tuple[bool, List[str]]:
        """Simulated AT responses for development without hardware."""
        await asyncio.sleep(0.05)
        cmd = command.upper().split("=")[0].split("?")[0]

        if cmd == "AT":
            return True, ["OK"]
        elif cmd == "AT+CPIN":
            return True, ["+CPIN: READY", "OK"]
        elif cmd == "AT+CSQ":
            return True, ["+CSQ: 22,0", "OK"]
        elif cmd == "AT+CREG":
            return True, ["+CREG: 0,1", "OK"]
        elif cmd == "AT+COPS":
            return True, ['+COPS: 0,0,"MTS RUS"', "OK"]
        elif cmd == "AT+CNUM":
            return True, ['+CNUM: "","+79001234567",145', "OK"]
        elif cmd == "ATI":
            return True, ["SIMCOM_SIM7600E-H", "Revision:LE20B04SIM7600M22", "OK"]
        elif cmd in ("AT+CMGF", "AT+CSCS", "AT+CLIP") or cmd.startswith("ATD"):
            return True, ["OK"]
        elif cmd == "ATA":
            if self.active_call:
                return True, ["OK"]
            return False, ["NO CARRIER"]
        elif cmd == "ATH":
            return True, ["OK"]
        elif cmd == "AT+CLCC":
            if self.active_call:
                d = "1" if self.active_call.direction == "incoming" else "0"
                s = "0" if self.active_call.state == "active" else "4"
                return True, [
                    f'+CLCC: 1,{d},{s},0,0,"{self.active_call.caller_number}",129',
                    "OK",
                ]
            return True, ["OK"]
        elif cmd == "AT+CMGL" or cmd.startswith("AT+CMGS"):
            return True, ["OK"]
        else:
            return True, ["OK"]
