import time
import logging
import serial
import serial.tools.list_ports

logger = logging.getLogger("turmo.lcd")

ORIENTATION_PORTRAIT = 0
ORIENTATION_LANDSCAPE = 1

def list_ports_text():
    ports = serial.tools.list_ports.comports()
    out = []
    for port in ports:
        v = f"{port.vid:04x}" if port.vid is not None else "none"
        p = f"{port.pid:04x}" if port.pid is not None else "none"
        out.append(f"{port.device:<20} vid:pid={v}:{p}")
    return "\n".join(out)

def find_port():
    """Find the TURMO display; never return a random serial port.

    Previously, if the display was not enumerated at boot, the program
    attached to the first port (e.g. /dev/ttyS0) and stayed there.
    """
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if p.vid == 0x1a86 and p.pid == 0x5722:
            return p.device
    for p in ports:
        info = f"{p.serial_number or ''} {p.description or ''}".upper()
        if "USB35INCH" in info or "TURMO" in info or "TURING" in info or "USBMONITOR" in info:
            return p.device
    return None

class TuringRevA:
    def __init__(self, port=None, baudrate=115200, baud=None, orientation=ORIENTATION_PORTRAIT):
        self._auto = not port or port == "auto"
        self.port = None if self._auto else port
        b = baud if baud is not None else baudrate
        self.baudrate = 115200 if b == 115200 else b
        self.orientation = orientation
        self.ser = None
        self.model = "Turing Smart Screen 3.5"

    def connect(self):
        # With "auto", look for the display on every attempt: this also
        # works when USB appears after the service starts or changes name.
        if self._auto:
            self.port = find_port()
        if not self.port:
            raise ConnectionError("No serial port found for the display.")
        logger.info(f"Opened port {self.port} at {self.baudrate} baud")
        self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
        return True

    def open(self):
        return self.connect()

    def reconnect(self):
        self.close()
        time.sleep(0.5)
        return self.connect()

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def get_width(self):
        if self.orientation in (ORIENTATION_LANDSCAPE, 2, 3):
            return 480
        return 320

    def get_height(self):
        if self.orientation in (ORIENTATION_LANDSCAPE, 2, 3):
            return 320
        return 480

    def hello(self):
        if self.ser:
            try:
                self.ser.write(b"\x01\x01\x01\x01\x01\x01")
                self.ser.flush()
                time.sleep(0.05)
            except Exception:
                pass

    def set_brightness(self, brightness: int):
        if not self.ser:
            return
        val = int(255 - ((max(0, min(100, brightness)) / 100.0) * 255))
        try:
            self.ser.write(bytearray([110, val, 0, 0, 0, 0]))
            self.ser.flush()
        except Exception:
            pass

    def set_orientation(self, orientation: int):
        self.orientation = orientation

    def display_image(self, image, x=0, y=0):
        if not self.ser:
            return
        
        # Use the exact screen dimensions for the current orientation
        max_w = self.get_width()
        max_h = self.get_height()
        
        # Fit the image exactly to the screen resolution
        if image.size != (max_w, max_h):
            image = image.resize((max_w, max_h))
            
        img = image.convert("RGB")
        width, height = img.size
            
        x0, y0 = 0, 0
        x1, y1 = width - 1, height - 1
        
        # 5-byte coordinate packet for the controller
        byteBuffer = bytearray(5)
        byteBuffer[0] = (x0 >> 2)
        byteBuffer[1] = (((x0 & 3) << 6) + (y0 >> 4))
        byteBuffer[2] = (((y0 & 15) << 4) + (x1 >> 6))
        byteBuffer[3] = (((x1 & 63) << 2) + (y1 >> 8))
        byteBuffer[4] = (y1 & 255)
        
        header = bytearray([197]) + byteBuffer
        
        pixels = img.load()
        buf = bytearray()
        for h in range(height):
            for w in range(width):
                r, g, b = pixels[w, h]
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                buf.append(rgb565 & 0xFF)
                buf.append((rgb565 >> 8) & 0xFF)
                
        try:
            self.ser.write(header)
            self.ser.write(buf)
            self.ser.flush()
            time.sleep(0.002)
        except Exception as e:
            logger.error(f"Send error: {e}")
