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

            # Enable caller ID display
            await self.execute_at("AT+CLIP=1")
            # SMS text mode
            await self.execute_at("AT+CMGF=1")
            # Set charset UTF-8
            await self.execute_at('AT+CSCS="UTF-8"')

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

    async def send_sms(self, number: str, text: str) -> Tuple[bool, Optional[str]]:
        """Send SMS. Returns (success, error_message)."""
        logger.info(f"📱 Отправляем SMS на {number}...")

        if self.mock_mode:
            await asyncio.sleep(0.3)
            logger.info("✅ SMS отправлено (mock)")
            return True, None

        # Ensure text mode
        await self.execute_at("AT+CMGF=1")

        async with self._serial_lock:
            try:
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, self._serial_send_sms, number, text),
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
                return False, str(e)

    def _serial_send_sms(self, number: str, text: str) -> bool:
        """Blocking SMS send (runs in executor)."""
        assert self._serial is not None
        self._serial.reset_input_buffer()

        # AT+CMGS="number"
        self._serial.write(f'AT+CMGS="{number}"\r\n'.encode("utf-8"))
        # Wait for ">" prompt
        import time

        deadline = time.time() + 5
        while time.time() < deadline:
            raw = self._serial.readline()
            if b">" in raw:
                break
        else:
            return False

        # Send text + Ctrl+Z
        self._serial.write((text + chr(26)).encode("utf-8"))

        # Wait for OK
        deadline = time.time() + 30
        while time.time() < deadline:
            raw = self._serial.readline()
            line = raw.decode("utf-8", errors="ignore").strip()
            if "OK" in line:
                return True
            if "ERROR" in line:
                return False

        return False

    async def list_sms_from_modem(self, status: str = "ALL") -> List[Dict]:
        """List SMS stored on modem. Returns parsed list."""
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
                if self._serial and self._serial.is_open and self._serial.in_waiting > 0:
                    loop = asyncio.get_event_loop()
                    raw = await loop.run_in_executor(None, self._serial.readline)
                    line = raw.decode("utf-8", errors="ignore").strip()

                    if not line:
                        pass
                    elif "RING" in line:
                        await self._handle_ring()
                    elif "+CLIP:" in line:
                        self._handle_clip(line)
                    elif "NO CARRIER" in line:
                        await self._handle_no_carrier()
                    elif "+CMT:" in line:
                        self._handle_incoming_sms(line)

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
        """Read single SMS by index from SIM storage."""
        ok, lines = await self.execute_at(f"AT+CMGR={index}", timeout=5.0)
        if not ok or not lines:
            return None

        for i, ln in enumerate(lines):
            if ln.startswith("+CMGR:"):
                text = lines[i + 1] if i + 1 < len(lines) and lines[i + 1] != "OK" else ""
                sender_match = re.search(r'"(\+?[0-9]+)"', ln)
                sender = sender_match.group(1) if sender_match else "unknown"
                return {
                    "index": index,
                    "sender": sender,
                    "text": text,
                    "raw_header": ln,
                }
        return None

    async def read_all_sms(self) -> List[Dict]:
        """Read all SMS from SIM. Uses text mode listing."""
        await self.execute_at("AT+CMGF=1")
        messages = await self.list_sms_from_modem("ALL")
        await self.execute_at("AT+CMGF=0")
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
