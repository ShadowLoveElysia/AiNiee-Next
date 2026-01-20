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
                            scan_code = self._getch() # Get the scan code
                            # Convert extended key to readable string
                            extended_key = self._decode_extended_key(scan_code)
                            if extended_key:
                                self.input_queue.put(extended_key)
                        continue

                    # Decode bytes to string
                    try:
                        char_str = char.decode('utf-8', 'ignore')
                    except:
                        char_str = ''

                    # Handle ANSI escape sequences for Unix/Linux
                    if sys.platform != "win32" and char_str == '\x1b':
                        # This might be the start of an escape sequence
                        escape_key = self._read_escape_sequence()
                        if escape_key:
                            self.input_queue.put(escape_key)
                        continue

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

    def _decode_extended_key(self, scan_code):
        """解码Windows扩展键"""
        if sys.platform != "win32":
            return None

        # 将bytes转换为整数
        if isinstance(scan_code, bytes) and len(scan_code) == 1:
            code = ord(scan_code)
        else:
            return None

        # Windows扩展键映射
        extended_keys = {
            # 普通方向键
            0x48: 'up',      # 上箭头 / 小键盘8
            0x50: 'down',    # 下箭头 / 小键盘2
            0x4B: 'left',    # 左箭头 / 小键盘4
            0x4D: 'right',   # 右箭头 / 小键盘6
            # 其他导航键
            0x47: 'home',    # Home键 / 小键盘7
            0x4F: 'end',     # End键 / 小键盘1
            0x49: 'pgup',    # Page Up / 小键盘9
            0x51: 'pgdn',    # Page Down / 小键盘3
            0x52: 'ins',     # Insert / 小键盘0
            0x53: 'del',     # Delete / 小键盘.
            # 小键盘中心键 (5)
            0x4C: 'center',  # 小键盘5 (通常不做特殊处理)
            # 功能键
            0x3B: 'f1',      # F1
            0x3C: 'f2',      # F2
            0x3D: 'f3',      # F3
            0x3E: 'f4',      # F4
            0x3F: 'f5',      # F5
            0x40: 'f6',      # F6
            0x41: 'f7',      # F7
            0x42: 'f8',      # F8
            0x43: 'f9',      # F9
            0x44: 'f10',     # F10
            # F11-F12
            0x57: 'f11',     # F11
            0x58: 'f12',     # F12
        }

        return extended_keys.get(code, None)

    def _read_escape_sequence(self):
        """读取ANSI转义序列 (Linux/Mac)"""
        if sys.platform == "win32":
            return None

        # 尝试读取转义序列的下一部分
        sequence = '\x1b'
        timeout = 0.01  # 10ms timeout for sequence completion

        import time
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            if self._kbhit():
                try:
                    char = self._getch()
                    char_str = char.decode('utf-8', 'ignore')
                    sequence += char_str

                    # 检查常见的完整序列
                    if sequence == '\x1b[A':
                        return 'up'
                    elif sequence == '\x1b[B':
                        return 'down'
                    elif sequence == '\x1b[C':
                        return 'right'
                    elif sequence == '\x1b[D':
                        return 'left'
                    elif sequence == '\x1b[H':
                        return 'home'
                    elif sequence == '\x1b[F':
                        return 'end'
                    elif sequence == '\x1b[1~':
                        return 'home'
                    elif sequence == '\x1b[4~':
                        return 'end'
                    elif sequence == '\x1b[5~':
                        return 'pgup'
                    elif sequence == '\x1b[6~':
                        return 'pgdn'
                    elif sequence == '\x1b[2~':
                        return 'ins'
                    elif sequence == '\x1b[3~':
                        return 'del'
                    elif sequence.startswith('\x1bO'):
                        # Alternative format
                        if sequence == '\x1bOA':
                            return 'up'
                        elif sequence == '\x1bOB':
                            return 'down'
                        elif sequence == '\x1bOC':
                            return 'right'
                        elif sequence == '\x1bOD':
                            return 'left'
                        elif sequence == '\x1bOH':
                            return 'home'
                        elif sequence == '\x1bOF':
                            return 'end'

                    # 如果序列变得太长，停止读取
                    if len(sequence) > 10:
                        break

                except:
                    break
            else:
                time.sleep(0.001)  # 1ms sleep

        # 如果序列不完整，返回None
        return None
