import asyncio
import io
import wave
import os
import time
import requests
import pyaudio
import webrtcvad
from typing import Optional, Any, Callable, Awaitable
from kagent.channel.base import BaseChannel


class AudioRecorder:
    """音频录制器，支持语音端点检测(VAD)"""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        padding_duration_ms: int = 1000,
        input_device_index: int = None,
    ):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.padding_duration_ms = padding_duration_ms
        self.input_device_index = input_device_index
        self.vad = webrtcvad.Vad(2)

    def record_until_silence(self, timeout: int = 100) -> bytes:
        """录音直到检测到静音（语音结束）或超时"""
        print("🎤 请开始说话（自动检测语音结束）...")

        audio = pyaudio.PyAudio()
        frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)

        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            input_device_index=self.input_device_index,
            frames_per_buffer=frame_size,
        )

        frames = []
        num_padding_frames = int(self.padding_duration_ms / self.frame_duration_ms)
        ring_buffer = []
        triggered = False
        start_time = time.time()
        trigger_threshold = 1

        try:
            while True:
                if time.time() - start_time > timeout:
                    print("⚠️  录音超时")
                    break

                frame = stream.read(frame_size, exception_on_overflow=False)
                is_speech = self.vad.is_speech(frame, self.sample_rate)

                if not triggered:
                    ring_buffer.append((frame, is_speech))
                    num_voiced = len([f for f, speech in ring_buffer if speech])
                    if len(ring_buffer) >= trigger_threshold and num_voiced >= 1:
                        triggered = True
                        frames.extend([f for f, s in ring_buffer])
                        ring_buffer.clear()
                        print("🔴 开始录音...")
                else:
                    frames.append(frame)
                    ring_buffer.append((frame, is_speech))
                    if len(ring_buffer) > num_padding_frames:
                        ring_buffer.pop(0)
                    
                    num_unvoiced = len([f for f, speech in ring_buffer if not speech])
                    if num_unvoiced >= num_padding_frames:
                        print("⏹️  检测到语音结束")
                        break

        except KeyboardInterrupt:
            print("\n⏹️  手动停止录音")
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()

        return b"".join(frames)


class SiliconFlowASR:
    """SiliconFlow 语音识别客户端"""

    API_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def transcribe(
        self, audio_data: bytes, model: str = "TeleAI/TeleSpeechASR"
    ) -> Optional[str]:
        """识别语音并返回文本"""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"file": ("audio.wav", io.BytesIO(audio_data), "audio/wav")}
        data = {"model": model}

        try:
            print("🤖 正在识别...")
            response = requests.post(
                self.API_URL, headers=headers, files=files, data=data, timeout=30
            )
            response.raise_for_status()
            result = response.json()
            return result.get("text", "")
        except Exception as e:
            print(f"❌ ASR 错误: {e}")
            return None


class AudioChannel(BaseChannel):
    """
    Audio Channel for voice interaction.
    Uses local microphone for input and SiliconFlow for ASR.
    """

    def __init__(self, session_id: str = "audio-user", input_device_index: int = None):
        super().__init__()
        self.session_id = session_id
        self.is_running = False
        self.recorder = AudioRecorder(input_device_index=input_device_index)
        
        api_key = os.environ.get("ASR_API_KEY")
        if not api_key:
            raise ValueError("ASR_API_KEY environment variable is not set")
        
        self.asr = SiliconFlowASR(api_key)
        self.asr_model = os.environ.get("ASR_MODEL", "TeleAI/TeleSpeechASR")

    async def send_message(self, target_id: str, content: str, **kwargs):
        """Print the agent's response to the console."""
        print(f"\n[Agent]: {content}")

    async def _loop(self):
        """Main audio interaction loop."""
        print(f"--- Audio Channel Started (Session: {self.session_id}) ---")
        print("Press Enter to start recording, or type 'q' to quit.")

        while self.is_running:
            try:
                loop = asyncio.get_event_loop()
                user_input = await loop.run_in_executor(
                    None, lambda: input("\n[Press Enter to Speak / 'q' to quit]: ").strip().lower()
                )

                if user_input == "q":
                    self.is_running = False
                    break

                # Recording is blocking, run in executor
                pcm_data = await loop.run_in_executor(
                    None, lambda: self.recorder.record_until_silence(timeout=30)
                )

                if not pcm_data or len(pcm_data) < 1600:  # Minimum 0.1s of audio
                    print("⚠️  未检测到有效语音")
                    continue

                # Convert PCM to WAV
                wav_buffer = io.BytesIO()
                with wave.open(wav_buffer, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(pcm_data)
                wav_data = wav_buffer.getvalue()

                # ASR is blocking (requests), run in executor
                text = await loop.run_in_executor(
                    None, lambda: self.asr.transcribe(wav_data, model=self.asr_model)
                )

                if text:
                    print(f"📝 识别到: {text}")
                    if self.message_handler:
                        response = await self.message_handler(text, self.session_id)
                        await self.send_message(self.session_id, response)
                    else:
                        print("Error: No message handler configured.")
                else:
                    print("❌ 识别失败")

            except Exception as e:
                print(f"Error in audio loop: {e}")

    def start(self):
        """Start the audio interaction loop."""
        self.is_running = True
        try:
            asyncio.run(self._loop())
        except KeyboardInterrupt:
            print("\nAudio channel stopped by user.")
