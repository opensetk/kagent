import os
import json
import httpx
import sys
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
import lark_oapi as lark
from dotenv import load_dotenv
from kagent.channel.base import BaseChannel
from kagent.interaction.hook import HookAction

load_dotenv()


class LarkChannel(BaseChannel):
    """
    封装飞书长连接客户端，继承自 BaseChannel。
    
    - chat_id: 飞书的聊天标识，用于路由消息（决定发给谁）
    - session_id: Agent 的会话标识，全局共享，可跨渠道访问
    
    每个飞书聊天维护一个"当前 session_id"状态，
    用户可以通过 /switch 切换到任意 session。
    """

    def __init__(
        self, 
        app_id: Optional[str] = None, 
        app_secret: Optional[str] = None,
        show_tool_calls: bool = False
    ):
        super().__init__(show_tool_calls=show_tool_calls)
        self.app_id = app_id or os.getenv("APP_ID")
        self.app_secret = app_secret or os.getenv("APP_SECRET")

        if not self.app_id or not self.app_secret:
            raise ValueError(
                "APP_ID and APP_SECRET must be provided or set as environment variables"
            )

        self.loop = asyncio.get_event_loop()
        
        self.chat_sessions: Dict[str, str] = {}
        self.interaction_manager = None
        
        self.event_handler = (
            lark.EventDispatcherHandler.builder(self.app_id, self.app_secret)
            .register_p2_im_message_receive_v1(self._do_p2_im_message_receive_v1)
            .register_p2_im_chat_member_bot_added_v1(
                self._do_p2_im_chat_member_bot_added_v1
            )
            .build()
        )

        self.ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=self.event_handler,
            log_level=lark.LogLevel.DEBUG,
        )

    def _get_current_session(self, chat_id: str) -> str:
        """获取当前聊天正在使用的 session_id，默认使用 chat_id 作为 session_id"""
        return self.chat_sessions.get(chat_id, chat_id)

    def _set_current_session(self, chat_id: str, session_id: str):
        """设置当前聊天的 session_id"""
        self.chat_sessions[chat_id] = session_id
    
    def set_interaction_manager(self, interaction_manager):
        """Set the interaction manager for the Lark channel."""
        self.interaction_manager = interaction_manager

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
        """异步发送消息，实现 BaseChannel 接口"""
        token = await self.get_tenant_access_token()
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        params = {"receive_id_type": target_id_type}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        if msg_type == "interactive":
            content_obj = self._build_interactive_content(content)
        elif msg_type == "post":
            content_obj = self._build_post_content(content)
        else:
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

            receive_id_type = "open_id"
            receive_id = sender_id.open_id if sender_id.open_id else sender_id.user_id

            chat_id = event.message.chat_id
            chat_id = chat_id if chat_id else receive_id

            if not receive_id:
                return

            session_id = self._get_current_session(chat_id)

            if self.interaction_manager:
                result = await self.interaction_manager.handle_request(
                    content_raw, 
                    session_id,
                    on_message=self.on_message
                )
                reply_content = self._format_result(result, chat_id)
            elif self.message_handler:
                result = await self.message_handler(content_raw, session_id)
                reply_content = self._format_result(result, chat_id)
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

    def _format_result(self, result, chat_id: str) -> str:
        """Format HandleResult for Lark channel, handling actions appropriately."""
        action = getattr(result, 'action', None)
        action_data = getattr(result, 'action_data', {})

        if action == HookAction.SWITCH_SESSION:
            target_session_id = action_data.get("session_id")
            if target_session_id:
                self._set_current_session(chat_id, target_session_id)
                return f"✅ 已切换到会话: {target_session_id}\n\n{result.message}"
        
        elif action == HookAction.REFRESH_SESSIONS:
            new_session_id = action_data.get("new_session_id")
            if new_session_id:
                self._set_current_session(chat_id, new_session_id)
        
        return str(result)

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
