import os
import json
import httpx
import sys
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
import lark_oapi as lark
from dotenv import load_dotenv
from kagent.channel.base import BaseChannel

load_dotenv()


class LarkChannel(BaseChannel):
    """
    封装飞书长连接客户端，继承自 BaseChannel。
    """

    def __init__(self, app_id: Optional[str] = None, app_secret: Optional[str] = None):
        super().__init__()
        self.app_id = app_id or os.getenv("APP_ID")
        self.app_secret = app_secret or os.getenv("APP_SECRET")

        if not self.app_id or not self.app_secret:
            raise ValueError(
                "APP_ID and APP_SECRET must be provided or set as environment variables"
            )

        self.loop = asyncio.get_event_loop()

    def on_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Any) -> None:
        """
        Override to suppress tool call display for Lark channel.
        Lark channel does not show tool execution details to users.
        """
        pass  # Lark channel doesn't display tool calls in console

        # 1. 创建事件处理器
        self.event_handler = (
            lark.EventDispatcherHandler.builder(self.app_id, self.app_secret)
            .register_p2_im_message_receive_v1(self._do_p2_im_message_receive_v1)
            .register_p2_im_chat_member_bot_added_v1(
                self._do_p2_im_chat_member_bot_added_v1
            )
            .build()
        )

        # 2. 创建长连接客户端
        self.ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=self.event_handler,
            log_level=lark.LogLevel.DEBUG,
        )

    async def get_tenant_access_token(self) -> str:
        """异步获取 tenant_access_token"""
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            if result.get("code", 0) != 0:
                raise Exception(
                    f"failed to get tenant_access_token: {result.get('msg', 'unknown error')}"
                )
            return result["tenant_access_token"]

    async def send_message(
        self,
        target_id: str,
        content: str,
        target_id_type: str = "open_id",
        msg_type: str = "interactive",
    ) -> Dict[str, Any]:
        """异步发送消息，实现 BaseChannel 接口

        所有消息都按 Markdown 格式发送（默认使用 interactive 卡片 2.0 类型）。
        """
        token = await self.get_tenant_access_token()
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        params = {"receive_id_type": target_id_type}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        # 根据消息类型构建不同的内容结构
        if msg_type == "interactive":
            content_obj = self._build_interactive_content(content)
        elif msg_type == "post":
            content_obj = self._build_post_content(content)
        else:
            # 默认强制使用 interactive 以支持高级 Markdown
            msg_type = "interactive"
            content_obj = self._build_interactive_content(content)

        payload = {
            "receive_id": target_id,
            "msg_type": msg_type,
            "content": json.dumps(content_obj, ensure_ascii=False),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                params=params,
                content=json.dumps(payload, ensure_ascii=False),
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    def _build_post_content(self, content: str) -> Dict[str, Any]:
        """构建飞书 post 富文本消息内容格式，支持 Markdown
        参考 test/test_lark.py 中的实现
        """
        return {
            "zh_cn": {
                "title": "Agent 回复",
                "content": [
                    [
                        {
                            "tag": "md",
                            "text": content
                        }
                    ]
                ]
            }
        }

    def _build_interactive_content(self, content: str) -> Dict[str, Any]:
        """构建飞书 interactive 卡片消息内容格式 (JSON 2.0)
        使用 JSON 2.0 结构支持更丰富的 Markdown 渲染。
        参考: https://open.feishu.cn/document/feishu-cards/card-json-v2-structure
        """
        return {
            "schema": "2.0",
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "Agent 回复"
                },
                "template": "blue"
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content
                    }
                ]
            }
        }

    def _do_p2_im_message_receive_v1(
        self, data: lark.im.v1.P2ImMessageReceiveV1
    ) -> None:
        """内部方法：同步桥接异步处理"""
        if self.loop.is_running():
            asyncio.ensure_future(self._async_handle_message(data))
        else:
            asyncio.run(self._async_handle_message(data))

    async def _async_handle_message(
        self, data: lark.im.v1.P2ImMessageReceiveV1
    ) -> None:
        """真正的异步消息处理逻辑"""
        try:
            event = data.event
            message = event.message
            content_raw = json.loads(message.content).get("text", "")
            sender_id = event.sender.sender_id

            # 使用 open_id 或 chat_id 作为 session_id
            receive_id_type = "open_id"
            receive_id = sender_id.open_id if sender_id.open_id else sender_id.user_id

            # 如果是群聊消息，使用 chat_id 作为 session_id
            chat_id = event.message.chat_id
            session_id = chat_id if chat_id else receive_id

            if not receive_id:
                return

            reply_content = ""
            if self.message_handler:
                # 传入 text 和 session_id 给 InteractionManager
                reply_content = await self.message_handler(content_raw, session_id)
            else:
                reply_content = f"已收到消息: {content_raw}。但未设置消息处理器。"

            if reply_content:
                await self.send_message(
                    target_id=receive_id,
                    content=reply_content,
                    target_id_type="open_id" if sender_id.open_id else "user_id",
                )

        except Exception as e:
            print(f"ERROR: processing message: {e}", file=sys.stderr)

    def _do_p2_im_chat_member_bot_added_v1(
        self, data: lark.im.v1.P2ImChatMemberBotAddedV1
    ) -> None:
        """同步桥接异步处理"""
        if self.loop.is_running():
            asyncio.ensure_future(self._async_handle_bot_added(data))
        else:
            asyncio.run(self._async_handle_bot_added(data))

    async def _async_handle_bot_added(
        self, data: lark.im.v1.P2ImChatMemberBotAddedV1
    ) -> None:
        try:
            chat_id = data.event.chat_id
            welcome_text = (
                "您好！我是 Lark Agent Client。连接已建立，我将为您转发消息。 "
            )
            await self.send_message(
                target_id=chat_id, content=welcome_text, target_id_type="chat_id"
            )
        except Exception as e:
            print(f"ERROR: processing bot added event: {e}", file=sys.stderr)

    def start(self):
        """启动长连接"""
        print("Lark Agent Client starting...")
        self.ws_client.start()


if __name__ == "__main__":
    # 示例用法 / 调试
    async def main():
        try:
            client = LarkChannel()

            async def simple_agent(text, event):
                return f"【Agent 回复】您刚才说：{text}"

            client.set_message_handler(simple_agent)
            client.start()
        except Exception as e:
            print(f"Failed to start: {e}")

    asyncio.run(main())
