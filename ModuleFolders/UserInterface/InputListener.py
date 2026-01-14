import sys
import threading
import queue
import time

class InputListener:
    def __init__(self):
        self.input_queue = queue.Queue()
        self.running = False
        self.thread = None
        self.disabled = False
        try:
            self._setup_platform()
        except Exception as e:
            self.disabled = True
            # We cannot print directly here as it might interfere with the UI.
            # The main CLI module will check the 'disabled' flag and inform the user.
            
    def _setup_platform(self):
        """屏蔽多系统差异，统一底层实现"""
        if sys.platform == "win32":
            import msvcrt
            self._getch = msvcrt.getch
            self._kbhit = msvcrt.kbhit
        else:
            # Linux/Mac implementation using termios/tty
            import tty
            import termios
            
            # Check if stdin is a tty
            if not sys.stdin.isatty():
                raise IOError("Not a TTY, disabling input listener.")

            import select
            
            def _unix_getch():
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                try:
                    tty.setraw(sys.stdin.fileno())
                    # Check for input before blocking
                    if _unix_kbhit():
                        ch = sys.stdin.read(1)
                    else:
                        ch = ''
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                return ch.encode('utf-8') # Consistent bytes return

            def _unix_kbhit():
                dr, dw, de = select.select([sys.stdin], [], [], 0)
                return dr != []

            self._getch = _unix_getch
            self._kbhit = _unix_kbhit

    def start(self):
        if self.running or self.disabled: return
        self.running = True
        self.thread = threading.Thread(target=self._input_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)

    def _input_loop(self):
        while self.running:
            try:
                if self._kbhit():
                    char = self._getch()
                    
                    # Windows extended keys (0x00 or 0xE0) are followed by a scan code
                    if sys.platform == "win32" and char in (b'\x00', b'\xe0'):
                        if self._kbhit():
                            self._getch() # Consume the scan code
                        continue

                    # Decode bytes to string
                    try:
                        char_str = char.decode('utf-8', 'ignore')
                    except:
                        char_str = ''
                    
                    if char_str:
                        self.input_queue.put(char_str.lower()) # Standardize to lowercase
                else:
                    time.sleep(0.05) # Reduce CPU usage
            except Exception:
                pass

    def get_key(self):
        """Non-blocking get key"""
        try:
            return self.input_queue.get_nowait()
        except queue.Empty:
            return None

    def clear(self):
        with self.input_queue.mutex:
            self.input_queue.queue.clear()
