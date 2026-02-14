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
    
    支持虚拟会话：同一个飞书聊天可以有多个独立的会话。
    session_id 格式: {chat_id}:{virtual_session_name}
    """

    VIRTUAL_SESSION_SEPARATOR = ":"
    DEFAULT_VIRTUAL_SESSION = "default"

    def __init__(self, app_id: Optional[str] = None, app_secret: Optional[str] = None):
        super().__init__()
        self.app_id = app_id or os.getenv("APP_ID")
        self.app_secret = app_secret or os.getenv("APP_SECRET")

        if not self.app_id or not self.app_secret:
            raise ValueError(
                "APP_ID and APP_SECRET must be provided or set as environment variables"
            )

        self.loop = asyncio.get_event_loop()
        
        self.chat_virtual_sessions: Dict[str, str] = {}
        
        # 创建事件处理器
        self.event_handler = (
            lark.EventDispatcherHandler.builder(self.app_id, self.app_secret)
            .register_p2_im_message_receive_v1(self._do_p2_im_message_receive_v1)
            .register_p2_im_chat_member_bot_added_v1(
                self._do_p2_im_chat_member_bot_added_v1
            )
            .build()
        )

        # 创建长连接客户端
        self.ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=self.event_handler,
            log_level=lark.LogLevel.DEBUG,
        )

    def _get_current_virtual_session(self, chat_id: str) -> str:
        """获取当前聊天正在使用的虚拟会话名"""
        return self.chat_virtual_sessions.get(chat_id, self.DEFAULT_VIRTUAL_SESSION)

    def _build_session_id(self, chat_id: str, virtual_session: str = None) -> str:
        """构建完整的 session_id"""
        if virtual_session is None:
            virtual_session = self._get_current_virtual_session(chat_id)
        return f"{chat_id}{self.VIRTUAL_SESSION_SEPARATOR}{virtual_session}"

    def _parse_session_id(self, session_id: str) -> tuple:
        """解析 session_id，返回 (chat_id, virtual_session)"""
        if self.VIRTUAL_SESSION_SEPARATOR in session_id:
            parts = session_id.split(self.VIRTUAL_SESSION_SEPARATOR, 1)
            return parts[0], parts[1]
        return session_id, self.DEFAULT_VIRTUAL_SESSION

    def on_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Any) -> None:
        """
        Override to suppress tool call display for Lark channel.
        Lark channel does not show tool call details to users.
        """
        pass

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

            receive_id_type = "open_id"
            receive_id = sender_id.open_id if sender_id.open_id else sender_id.user_id

            chat_id = event.message.chat_id
            base_chat_id = chat_id if chat_id else receive_id

            if not receive_id:
                return

            session_id = self._build_session_id(base_chat_id)
            
            processed_content = self._preprocess_hook_command(content_raw, base_chat_id)

            reply_content = ""
            if self.message_handler:
                result = await self.message_handler(processed_content, session_id)
                reply_content = self._format_result(result, base_chat_id)
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

    def _preprocess_hook_command(self, text: str, chat_id: str) -> str:
        """
        预处理 hook 命令，将虚拟会话名转换为完整的 session_id。
        
        例如: /switch work -> /switch oc_xxx:work
              /new task -> /new oc_xxx:task
        """
        text = text.strip()
        if not text.startswith("/"):
            return text
        
        parts = text.split()
        if not parts:
            return text
        
        hook_name = parts[0].lower()
        
        virtual_session_hooks = {
            "/switch": 1,
            "/new": 1,
            "/delete": 1,
            "/rename": 1,
        }
        
        if hook_name in virtual_session_hooks:
            arg_index = virtual_session_hooks[hook_name]
            
            if hook_name == "/rename":
                if len(parts) >= 3:
                    old_name = parts[1]
                    new_name = parts[2]
                    if self.VIRTUAL_SESSION_SEPARATOR not in old_name:
                        parts[1] = self._build_session_id(chat_id, old_name)
                    if self.VIRTUAL_SESSION_SEPARATOR not in new_name:
                        parts[2] = self._build_session_id(chat_id, new_name)
            else:
                if len(parts) > arg_index:
                    session_name = parts[arg_index]
                    if self.VIRTUAL_SESSION_SEPARATOR not in session_name:
                        parts[arg_index] = self._build_session_id(chat_id, session_name)
        
        return " ".join(parts)

    def _format_result(self, result, chat_id: str) -> str:
        """Format HandleResult for Lark channel, handling actions appropriately."""
        action = getattr(result, 'action', None)
        action_data = getattr(result, 'action_data', {})

        if action == HookAction.SWITCH_SESSION:
            target_session_id = action_data.get("session_id")
            if target_session_id:
                target_chat_id, virtual_session = self._parse_session_id(target_session_id)
                
                if target_chat_id != chat_id:
                    return f"⚠️ 无法切换到其他聊天的会话。\n当前聊天: {chat_id}"
                
                self.chat_virtual_sessions[chat_id] = virtual_session
                return f"✅ 已切换到会话: {virtual_session}\n\n{result.message}"
        
        elif action == HookAction.REFRESH_SESSIONS:
            new_session_id = action_data.get("new_session_id")
            if new_session_id:
                _, virtual_session = self._parse_session_id(new_session_id)
                self.chat_virtual_sessions[chat_id] = virtual_session
        
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
