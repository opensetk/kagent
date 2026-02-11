#!/usr/bin/env python3
"""语音驱动 Agent - 终端版"""

import anyio
import io
import wave
import time
import os
import sys
import requests
import pyaudio
import webrtcvad
from typing import Optional

from claude_agent_sdk import query, ClaudeAgentOptions


class AudioRecorder:
    """音频录制器，支持语音端点检测(VAD)"""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        padding_duration_ms: int = 300,
        input_device_index: int = None,
    ):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.padding_duration_ms = padding_duration_ms
        self.input_device_index = input_device_index
        self.vad = webrtcvad.Vad(2)

    @staticmethod
    def list_devices():
        """列出所有可用的音频设备"""
        audio = pyaudio.PyAudio()
        print("\n=== 可用的音频设备 ===")
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                print(f"输入设备 {i}: {info['name']}")
            if info["maxOutputChannels"] > 0:
                print(f"输出设备 {i}: {info['name']}")
        print("=" * 30 + "\n")
        audio.terminate()

    def record_until_silence(self, timeout: int = 100) -> bytes:
        """录音直到检测到静音（语音结束）或超时"""
        print("🎤 请开始说话（自动检测语音结束）...")

        audio = pyaudio.PyAudio()
        frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)

        if self.input_device_index is not None:
            device_info = audio.get_device_info_by_index(self.input_device_index)
            print(f"🎧 使用设备: {device_info['name']}")

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

        pcm_data = b"".join(frames)

        if len(frames) < 10:
            print("⚠️  录音时间太短，未保存")
            return b""

        return pcm_data


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
            text = result.get("text", "")

            if text:
                return text
            else:
                print(f"⚠️  API 返回异常: {result}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"❌ 请求失败: {e}")
            return None
        except Exception as e:
            print(f"❌ 错误: {e}")
            return None


class VoiceAgent:
    """语音驱动的 Claude Agent"""

    def __init__(self, api_key: str, input_device_index: int = None):
        self.recorder = AudioRecorder(
            input_device_index=input_device_index, sample_rate=16000
        )
        self.recorder.vad = webrtcvad.Vad(0)
        self.asr = SiliconFlowASR(api_key)

    async def process_voice_command(self, voice_prompt: str):
        """处理语音命令并通过 Agent 执行"""

        options = ClaudeAgentOptions(
            model="glm-4.7-flash",
            permission_mode="bypassPermissions",
            max_turns=5,
        )

        print(f"\n🤖 Agent 执行中...")
        print("-" * 40)

        async for message in query(prompt=voice_prompt, options=options):
            print(message, end="", flush=True)

        print("\n" + "-" * 40)

    def run(self):
        """主循环"""
        print("\n" + "=" * 50)
        print("🎙️  语音驱动 Agent")
        print("=" * 50)
        print("使用方法:")
        print("1. 按 Enter 开始录音")
        print("2. 对着麦克风说出你的指令")
        print("3. 说完后等待自动停止")
        print("4. Agent 将执行你的指令")
        print("5. 输入 'q' 退出程序")
        print("=" * 50 + "\n")

        while True:
            try:
                user_input = input("按 Enter 开始录音 (输入 q 退出): ").strip().lower()
                if user_input == "q":
                    print("👋 再见!")
                    break

                pcm_data = self.recorder.record_until_silence(timeout=30)

                if not pcm_data:
                    continue

                wav_buffer = io.BytesIO()
                with wave.open(wav_buffer, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(pcm_data)
                wav_data = wav_buffer.getvalue()

                text = self.asr.transcribe(wav_data)

                if text:
                    print(f"\n📝 识别到的指令: {text}")
                    anyio.run(self.process_voice_command, text)
                else:
                    print("\n❌ 未能识别到文字\n")

            except KeyboardInterrupt:
                print("\n👋 程序已终止")
                break
            except Exception as e:
                print(f"\n❌ 发生错误: {e}\n")


def main():
    api_key = os.environ.get(
        "SILICONFLOW_API_KEY", "sk-mzwuunvvjoamyfgslvepqnpkguepjetgiumodtrrtcmirfya"
    )
    input_device = 1
    agent = VoiceAgent(api_key=api_key, input_device_index=input_device)
    agent.run()


if __name__ == "__main__":
    main()
