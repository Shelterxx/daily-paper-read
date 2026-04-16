"""Test collapsible_panel with correct JSON structure from Feishu docs."""

import asyncio
import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.environ.get("FEISHU_APP_ID")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
CHAT_ID = os.environ.get("FEISHU_CHAT_ID")

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"


async def get_token(client: httpx.AsyncClient) -> str:
    resp = await client.post(TOKEN_URL, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
    return resp.json()["tenant_access_token"]


async def send_card(client: httpx.AsyncClient, token: str, card_json: dict, label: str) -> bool:
    resp = await client.post(
        MESSAGE_URL,
        params={"receive_id": CHAT_ID, "receive_id_type": "chat_id"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "receive_id": CHAT_ID,
            "msg_type": "interactive",
            "content": json.dumps(card_json, ensure_ascii=False),
        },
        timeout=15,
    )
    result = resp.json()
    ok = result.get("code") == 0
    if ok:
        print(f"  {label}: OK !!")
    else:
        msg = result.get("msg", "")[:200]
        print(f"  {label}: FAIL - {msg}")
    return ok


async def main():
    if not all([APP_ID, APP_SECRET, CHAT_ID]):
        print("Missing env vars")
        return

    async with httpx.AsyncClient() as client:
        token = await get_token(client)
        print(f"Token: {token[:10]}...\n")

        # Full paper card with collapsible panels
        card = {
            "header": {
                "title": {"tag": "plain_text", "content": "📚 Env-CS Computing（推送 2 篇）"},
                "template": "blue",
            },
            "elements": [
                # Paper 1 — always visible info
                {"tag": "div", "text": {"tag": "lark_md", "content": "**🔥 [9/10] [Deep Neural Network-guided PSO for Air Quality](https://doi.org/10.1016/j.atmosenv.2025.123456)**"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": "👤 Zhang, Wei, Li, Ming +2 | 2025-03-15"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": "📝 提出DNN-PSO混合模型用于城市空气质量追踪，RMSE降低23%。"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": "💡 **核心贡献**：\n  • 提出DNN-PSO混合优化框架\n  • 构建覆盖全球50城市的数据集"}},

                # Collapsible: Applications
                {
                    "tag": "collapsible_panel",
                    "expanded": False,
                    "header": {
                        "title": {"tag": "markdown", "content": "**🔧 潜在应用**"},
                    },
                    "elements": [
                        {"tag": "markdown", "content": "城市空气质量实时监测、太阳能发电量预测、大气污染预警系统"}
                    ],
                },

                # Collapsible: Methodology
                {
                    "tag": "collapsible_panel",
                    "expanded": False,
                    "header": {
                        "title": {"tag": "markdown", "content": "**🔬 方法论评估**"},
                    },
                    "elements": [
                        {"tag": "markdown", "content": "采用ResNet-50骨干网络提取时空特征，结合自适应PSO优化超参数。5-fold交叉验证，消融实验验证模块有效性。"}
                    ],
                },

                # Collapsible: Limitations
                {
                    "tag": "collapsible_panel",
                    "expanded": False,
                    "header": {
                        "title": {"tag": "markdown", "content": "**⚠️ 局限性**"},
                    },
                    "elements": [
                        {"tag": "markdown", "content": "• 模型训练需要大量标注数据\n• PSO优化计算开销较大，实时性有待提升"}
                    ],
                },

                # Collapsible: Future
                {
                    "tag": "collapsible_panel",
                    "expanded": False,
                    "header": {
                        "title": {"tag": "markdown", "content": "**🚀 未来方向**"},
                    },
                    "elements": [
                        {"tag": "markdown", "content": "• 探索Few-shot学习降低数据依赖\n• 引入轻量化网络提升推理速度"}
                    ],
                },

                # Metadata + buttons
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "DOI: 10.1016/j.atmosenv.2025.123456 | 深度学习, PSO, 空气质量"}]},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "查看论文"}, "url": "https://doi.org/10.1016/j.atmosenv.2025.123456", "type": "primary"},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "PDF"}, "url": "https://arxiv.org/pdf/2503.12345", "type": "default"},
                ]},
                {"tag": "hr"},

                # Paper 2
                {"tag": "div", "text": {"tag": "lark_md", "content": "**📄 [8/10] [Transfer Learning for PM2.5](https://doi.org/10.1021/est.2025.07890)**"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": "👤 Park, Kim, Lee | 2025-03-12"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": "📝 跨城市PM2.5迁移学习框架，12城市测试提升18%。"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": "💡 **核心贡献**：\n  • 设计城市间大气污染特征对齐域适应模块\n  • 迁移学习比基线提升18%"}},
                {
                    "tag": "collapsible_panel",
                    "expanded": False,
                    "header": {
                        "title": {"tag": "markdown", "content": "**⚠️ 局限**"},
                    },
                    "elements": [
                        {"tag": "markdown", "content": "仅验证中国城市，跨国家迁移能力未验证"}
                    ],
                },
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "查看论文"}, "url": "https://doi.org/10.1021/est.2025.07890", "type": "primary"},
                ]},
            ],
        }

        print("Sending paper card with collapsible panels...")
        await send_card(client, token, card, "Collapsible card")


if __name__ == "__main__":
    asyncio.run(main())
