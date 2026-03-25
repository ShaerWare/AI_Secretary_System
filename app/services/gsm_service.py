"""
GSM Service for SIM7600E-H modem integration.

Handles AT commands, call management, and SMS via serial port.
Auto-switches to mock mode when hardware is not available.

AT port: /dev/ttyUSB2 (115200 baud)
Audio port: /dev/ttyUSB4 (future PR)

Hardware notes (SIM7600E-H):
- SMS and voice only work on 2G/3G (AT+CNMP=14), NOT LTE
- ATH does NOT hangup answered incoming calls — use AT+CHUP
- AT+CSCS="UTF-8" not supported — use PDU mode for Cyrillic SMS
- ModemManager must be disabled: systemctl disable ModemManager
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

# Network mode names from AT+CNSMOD?
NETWORK_MODES = {
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
    15: "LTE-CA",
}


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
    network_mode: Optional[str] = None

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


# ============== PDU Helpers ==============


def _encode_phone_pdu(number: str) -> Tuple[str, int, str]:
    """Encode phone number for PDU format.

    Returns (encoded_number_hex, digit_count, type_byte).
    """
    num = number.lstrip("+")
    num_type = "91" if number.startswith("+") else "81"
    digit_count = len(num)
    if len(num) % 2 == 1:
        num += "F"
    swapped = ""
    for i in range(0, len(num), 2):
        swapped += num[i + 1] + num[i]
    return swapped, digit_count, num_type


def _build_sms_pdu(number: str, message: str) -> Tuple[str, int]:
    """Build SMS-SUBMIT PDU with UCS2 encoding for Cyrillic support.

    Returns (pdu_hex_string, tpdu_length_in_bytes).
    """
    # SCA: 00 = use default SMSC
    pdu = "00"
    # First octet: 11 = SMS-SUBMIT with validity period
    pdu += "11"
    # MR: 00 = message reference
    pdu += "00"

    # Destination Address
    encoded_num, digit_count, num_type = _encode_phone_pdu(number)
    pdu += f"{digit_count:02X}"
    pdu += num_type
    pdu += encoded_num

    # PID: 00
    pdu += "00"
    # DCS: 08 = UCS2 encoding
    pdu += "08"
    # VP: AA = 4 days validity
    pdu += "AA"

    # User Data
    msg_ucs2 = message.encode("utf-16-be").hex().upper()
    udl = len(message) * 2  # UCS2 = 2 bytes per char
    pdu += f"{udl:02X}"
    pdu += msg_ucs2

    # TPDU length = total bytes minus SCA (1 byte = '00')
    tpdu_len = (len(pdu) - 2) // 2
    return pdu, tpdu_len


def _is_ascii_only(text: str) -> bool:
    """Check if text contains only GSM 7-bit compatible characters."""
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _decode_ucs2_hex(hex_str: str) -> str:
    """Decode UCS2 hex string to text."""
    try:
        return bytes.fromhex(hex_str).decode("utf-16-be")
    except (ValueError, UnicodeDecodeError):
        return hex_str


# ============== Main Service ==============


class GSMService:
    """
    GSM Service for SIM7600E-H modem.

    Features:
    - AT command communication via serial port
    - Call management (dial, answer, hangup)
    - SMS sending (PDU mode for Cyrillic, text mode for ASCII)
    - SMS reading from SIM with UCS2 decode
    - DTMF tone sending during calls
    - Background monitoring for incoming calls and SMS
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
                    timeout=2,
                    write_timeout=3,
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

            # Enable verbose error reporting
            await self.execute_at("AT+CMEE=2")

            # Force 2G/3G — SMS and voice don't work on LTE without VoLTE
            await self.execute_at("AT+CNMP=14")
            await asyncio.sleep(3)  # Wait for network re-registration

            # Enable caller ID display
            await self.execute_at("AT+CLIP=1")

            # Extended ring format (shows VOICE/DATA type)
            await self.execute_at("AT+CRC=1")

            # SMS: PDU mode (for UCS2 Cyrillic support)
            await self.execute_at("AT+CMGF=0")

            # Enable new SMS notification via URC
            await self.execute_at("AT+CNMI=2,1,0,0,0")

            # Clean old SMS from SIM to prevent overflow
            await self.execute_at("AT+CMGD=1,4", timeout=10.0)

            self.state = "ready"
            logger.info("✅ GSM modem initialized (hardware mode)")

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
                    ln.startswith("ERROR")
                    or ln.startswith("+CME ERROR")
                    or ln.startswith("+CMS ERROR")
                    for ln in lines
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

            if (
                line in ("OK", "ERROR")
                or line.startswith("+CME ERROR")
                or line.startswith("+CMS ERROR")
            ):
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
                    match = re.search(r'"([^"]+)"', ln)
                    if match:
                        status.network_name = match.group(1)

        # Own phone number
        ok, lines = await self.execute_at("AT+CNUM")
        if ok:
            for ln in lines:
                if "+CNUM:" in ln:
                    match = re.search(r'"(\+?[0-9]+)"', ln)
                    if match:
                        status.phone_number = match.group(1)

        # Module info
        ok, lines = await self.execute_at("ATI")
        if ok:
            info_lines = [ln for ln in lines if ln not in ("OK", "") and not ln.startswith("AT")]
            if info_lines:
                status.module_info = " / ".join(info_lines)

        # Network mode (2G/3G/LTE)
        ok, lines = await self.execute_at("AT+CNSMOD?")
        if ok:
            for ln in lines:
                if "+CNSMOD:" in ln:
                    try:
                        mode_num = int(ln.split(",")[1].strip())
                        status.network_mode = NETWORK_MODES.get(mode_num, f"Unknown({mode_num})")
                    except (ValueError, IndexError):
                        pass

        status.last_error = self.last_error
        return status

    async def get_network_mode(self) -> Optional[str]:
        """Get current network mode string."""
        ok, lines = await self.execute_at("AT+CNSMOD?")
        if ok:
            for ln in lines:
                if "+CNSMOD:" in ln:
                    try:
                        mode_num = int(ln.split(",")[1].strip())
                        return NETWORK_MODES.get(mode_num, f"Unknown({mode_num})")
                    except (ValueError, IndexError):
                        pass
        return None

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
        """Hang up current call. Uses AT+CHUP (ATH doesn't work for answered incoming calls)."""
        logger.info("📞 Завершаем звонок...")
        ok, _ = await self.execute_at("AT+CHUP")

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
    # DTMF
    # ================================================================

    async def send_dtmf(self, digits: str) -> bool:
        """Send DTMF tones during active call."""
        if not self.active_call or self.active_call.state != "active":
            return False

        for digit in digits:
            if digit in "0123456789*#ABCD":
                ok, _ = await self.execute_at(f'AT+VTS="{digit}"', timeout=3.0)
                if not ok:
                    return False
                await asyncio.sleep(0.3)
        return True

    # ================================================================
    # SMS
    # ================================================================

    async def send_sms(self, number: str, text: str) -> Tuple[bool, Optional[str]]:
        """Send SMS. Uses PDU mode for Cyrillic, text mode for ASCII-only.

        Returns (success, error_message).
        """
        logger.info(f"📱 Отправляем SMS на {number}...")

        if self.mock_mode:
            await asyncio.sleep(0.3)
            logger.info("✅ SMS отправлено (mock)")
            return True, None

        # Use PDU mode for all messages (reliable for both Latin and Cyrillic)
        return await self._send_sms_pdu(number, text)

    async def _send_sms_pdu(self, number: str, text: str) -> Tuple[bool, Optional[str]]:
        """Send SMS via PDU mode with UCS2 encoding."""
        # Ensure PDU mode
        await self.execute_at("AT+CMGF=0")

        pdu, tpdu_len = _build_sms_pdu(number, text)

        async with self._serial_lock:
            try:
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, self._serial_send_sms_pdu, pdu, tpdu_len),
                    timeout=30.0,
                )
                if result:
                    logger.info("✅ SMS отправлено (PDU)")
                    return True, None
                else:
                    return False, "SMS отправка не удалась"
            except asyncio.TimeoutError:
                return False, "Таймаут отправки SMS"
            except Exception as e:
                return False, str(e)

    def _serial_send_sms_pdu(self, pdu: str, tpdu_len: int) -> bool:
        """Blocking PDU SMS send (runs in executor)."""
        assert self._serial is not None
        self._serial.reset_input_buffer()

        # Send CMGS with TPDU length
        self._serial.write(f"AT+CMGS={tpdu_len}\r\n".encode("utf-8"))

        # Wait for ">" prompt
        deadline = _time.time() + 5
        while _time.time() < deadline:
            raw = self._serial.readline()
            if b">" in raw:
                break
        else:
            return False

        # Send PDU + Ctrl+Z
        self._serial.write(pdu.encode("ascii") + b"\x1a")

        # Wait for +CMGS: or ERROR
        deadline = _time.time() + 30
        while _time.time() < deadline:
            raw = self._serial.readline()
            line = raw.decode("utf-8", errors="ignore").strip()
            if "+CMGS:" in line:
                return True
            if "ERROR" in line:
                logger.warning(f"SMS PDU error: {line}")
                return False

        return False

    async def read_sms(self, index: int) -> Optional[Dict]:
        """Read a single SMS from SIM by index. Decodes UCS2 if needed."""
        # Switch to text mode for reading (easier parsing)
        await self.execute_at("AT+CMGF=1")
        ok, lines = await self.execute_at(f"AT+CMGR={index}", timeout=5.0)
        # Switch back to PDU mode
        await self.execute_at("AT+CMGF=0")

        if not ok or not lines:
            return None

        header = None
        data_lines = []
        for ln in lines:
            if "+CMGR:" in ln:
                header = ln
            elif ln not in ("OK", "") and header is not None:
                data_lines.append(ln)

        if not header:
            return None

        # Extract number from header
        number_match = re.search(r'"([^"]*)",\s*"([^"]*)"', header)
        number = "unknown"
        status_str = "unknown"
        if number_match:
            status_str = number_match.group(1)
            number = number_match.group(2)

        # Try to decode UCS2 hex content
        text = ""
        for dl in data_lines:
            if all(c in "0123456789ABCDEFabcdef" for c in dl) and len(dl) > 10:
                text += _decode_ucs2_hex(dl)
            else:
                text += dl

        return {
            "index": index,
            "number": number,
            "status": status_str,
            "text": text,
            "raw_header": header,
        }

    async def read_all_sms(self) -> List[Dict]:
        """Read all SMS from SIM."""
        await self.execute_at("AT+CMGF=1")
        ok, lines = await self.execute_at('AT+CMGL="ALL"', timeout=10.0)
        await self.execute_at("AT+CMGF=0")

        if not ok:
            return []

        messages: List[Dict] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("+CMGL:"):
                # Parse index
                idx_match = re.match(r"\+CMGL:\s*(\d+)", line)
                index = int(idx_match.group(1)) if idx_match else -1

                # Parse number
                num_match = re.search(r'"(\+?[0-9]+)"', line)
                number = num_match.group(1) if num_match else "unknown"

                # Next line is text (possibly UCS2 hex)
                text = ""
                if i + 1 < len(lines) and lines[i + 1] not in ("OK", ""):
                    raw_text = lines[i + 1]
                    if all(c in "0123456789ABCDEFabcdef" for c in raw_text) and len(raw_text) > 10:
                        text = _decode_ucs2_hex(raw_text)
                    else:
                        text = raw_text
                    i += 2
                else:
                    i += 1

                messages.append(
                    {
                        "index": index,
                        "number": number,
                        "text": text,
                        "raw_header": line,
                    }
                )
            else:
                i += 1

        return messages

    async def delete_sms(self, index: int) -> bool:
        """Delete SMS from SIM by index."""
        ok, _ = await self.execute_at(f"AT+CMGD={index}")
        return ok

    async def delete_all_sms(self) -> bool:
        """Delete all SMS from SIM."""
        ok, _ = await self.execute_at("AT+CMGD=1,4", timeout=10.0)
        return ok

    async def list_sms_from_modem(self, status: str = "ALL") -> List[Dict]:
        """List SMS stored on modem. Returns parsed list."""
        return await self.read_all_sms()

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
                if self._serial and self._serial.is_open and self._serial.in_waiting > 0:
                    loop = asyncio.get_event_loop()
                    raw = await loop.run_in_executor(None, self._serial.readline)
                    line = raw.decode("utf-8", errors="ignore").strip()

                    if not line:
                        pass
                    elif "RING" in line or "CRING" in line:
                        await self._handle_ring()
                    elif "+CLIP:" in line:
                        self._handle_clip(line)
                    elif "NO CARRIER" in line:
                        await self._handle_no_carrier()
                    elif "+CMTI:" in line:
                        await self._handle_new_sms(line)
                    elif "VOICE CALL: BEGIN" in line:
                        logger.info("📞 Voice call audio channel active")
                    elif "VOICE CALL: END" in line:
                        logger.info(f"📞 {line}")
                    elif "BUSY" in line:
                        logger.info("📞 Remote busy")
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

    async def _handle_new_sms(self, line: str) -> None:
        """Handle +CMTI — new SMS received. Read it and fire callback."""
        logger.info(f"📱 Новое SMS: {line}")

        # Parse index: +CMTI: "SM",0
        match = re.search(r'"[^"]*",\s*(\d+)', line)
        if match:
            index = int(match.group(1))
            sms = await self.read_sms(index)
            if sms:
                logger.info(f"📱 SMS от {sms['number']}: {sms['text'][:50]}")
                # Delete from SIM to prevent overflow
                await self.delete_sms(index)

            if self.on_sms_received:
                try:
                    self.on_sms_received(sms or {"raw": line})
                except Exception as e:
                    logger.error(f"on_sms_received callback error: {e}")

    def _handle_incoming_sms(self, line: str) -> None:
        """Handle +CMT — new SMS received (legacy, kept for compatibility)."""
        logger.info(f"📱 Новое SMS: {line}")
        if self.on_sms_received:
            try:
                self.on_sms_received(line)
            except Exception as e:
                logger.error(f"on_sms_received callback error: {e}")

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
            return True, ['+COPS: 0,0,"MegaFon"', "OK"]
        elif cmd == "AT+CNUM":
            return True, ['+CNUM: "","+79992862779",145', "OK"]
        elif cmd == "ATI":
            return True, ["SIMCOM_SIM7600E-H", "Revision:SIM7600M22_V2.0.1", "OK"]
        elif cmd == "AT+CNSMOD":
            return True, ["+CNSMOD: 0,7", "OK"]
        elif cmd in (
            "AT+CMGF",
            "AT+CSCS",
            "AT+CLIP",
            "AT+CNMP",
            "AT+CMEE",
            "AT+CRC",
            "AT+CNMI",
            "AT+CMGD",
            "AT+CPCMREG",
            "AT+CSDVC",
            "AT+CLVL",
            "AT+CHUP",
        ) or cmd.startswith("ATD"):
            return True, ["OK"]
        elif cmd == "ATA":
            if self.active_call:
                return True, ["OK"]
            return False, ["NO CARRIER"]
        elif cmd == "AT+CLCC":
            if self.active_call:
                d = "1" if self.active_call.direction == "incoming" else "0"
                s = "0" if self.active_call.state == "active" else "4"
                return True, [
                    f'+CLCC: 1,{d},{s},0,0,"{self.active_call.caller_number}",129',
                    "OK",
                ]
            return True, ["OK"]
        elif cmd == "AT+CMGL" or cmd.startswith("AT+CMGS") or cmd == "AT+VTS":
            return True, ["OK"]
        else:
            return True, ["OK"]
