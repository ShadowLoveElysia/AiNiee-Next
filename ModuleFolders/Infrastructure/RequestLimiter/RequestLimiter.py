import time
import threading


class RequestLimiter:

    def __init__(self) -> None:
        # TPM相关参数
        self.max_tokens = 0  # 令牌桶最大容量
        self.remaining_tokens = 0  # 令牌桶剩余容量
        self.tokens_rate = 0  # 令牌每秒的恢复速率
        self.last_time = time.time()  # 上次记录时间

        # RPM相关参数 (Token Bucket)
        self.rpm_max_tokens = 0
        self.rpm_remaining_tokens = 0
        self.rpm_fill_rate = 0
        self.last_rpm_time = time.time()
        
        self.lock = threading.Lock()

    # 设置限制器的参数
    def set_limit(self, tpm_limit: int, rpm_limit: int) -> None:
        # 设置限制器的TPM参数
        self.max_tokens = 32000  # 令牌桶最大容量
        self.tokens_rate = tpm_limit / 60  # 令牌每秒的恢复速率
        self.remaining_tokens = 32000  # 令牌桶剩余容量

        # 设置限制器的RPM参数
        self.rpm_fill_rate = rpm_limit / 60
        # 允许一定的突发请求 (例如允许 10 秒量的突发，最小 5 个)
        self.rpm_max_tokens = max(5, int(rpm_limit / 6))
        self.rpm_remaining_tokens = self.rpm_max_tokens
        self.last_rpm_time = time.time()

    def rpm_limiter(self) -> bool:
        now = time.time()
        # 计算恢复的令牌
        delta = now - self.last_rpm_time
        tokens_to_add = delta * self.rpm_fill_rate
        
        # 更新令牌桶
        self.rpm_remaining_tokens = min(self.rpm_max_tokens, self.rpm_remaining_tokens + tokens_to_add)
        self.last_rpm_time = now

        if self.rpm_remaining_tokens >= 1.0:
            self.rpm_remaining_tokens -= 1.0
            return True
        else:
            return False

    def tpm_limiter(self, tokens: int) -> bool:
        now = time.time()  # 获取现在的时间
        tokens_to_add = (now - self.last_time) * self.tokens_rate  # 现在时间减去上一次记录的时间，乘以恢复速率，得出这段时间恢复的tokens数量
        self.remaining_tokens = min(self.max_tokens, self.remaining_tokens + tokens_to_add)  # 计算新的剩余容量，与最大容量比较，谁小取谁值，避免发送信息超过最大容量
        self.last_time = now  # 改变上次记录时间

        # 检查是否超过模型最大输入限制
        if tokens >= self.max_tokens:
            print("[Warning INFO] 该次任务的文本总tokens量已经超过最大输入限制(3w tokens)，请检查原文文件是否有问题或者文本切分量设置过大！！！")
            print("[Warning INFO] 该次任务将进行拆分处理，并进入下一轮任务中....")
            return False

        # 检查是否超过余量
        elif tokens >= self.remaining_tokens:
            return False

        else:
            # print("[DEBUG] 数量足够，剩余tokens：", tokens,'\n' )
            return True

    def check_limiter(self, tokens: int) -> bool:
        # 如果能够发送请求，则扣除令牌桶里的令牌数
        with self.lock:
            if self.rpm_limiter() and self.tpm_limiter(tokens):
                self.remaining_tokens = self.remaining_tokens - tokens
                return True
            else:
                return False

