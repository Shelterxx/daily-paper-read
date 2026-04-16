"""Test App API sending with collapsible_panel using mock data."""

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


def div(content: str) -> dict:
    return {"tag": "div", "text": {"tag": "lark_md", "content": content}}


def collapsible(title: str, content: str, expanded: bool = False) -> dict:
    return {
        "tag": "collapsible_panel",
        "expanded": expanded,
        "title": {"tag": "lark_md", "content": title},
        "content": {
            "elements": [
                {"tag": "markdown", "content": content}
            ]
        },
    }


async def send_card(card_json: dict):
    async with httpx.AsyncClient() as client:
        # Get token
        resp = await client.post(TOKEN_URL, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            print(f"Token error: {data}")
            return False
        token = data["tenant_access_token"]
        print(f"Got token: {token[:10]}...")

        # Send message
        resp = await client.post(
            MESSAGE_URL,
            params={"receive_id": CHAT_ID, "receive_id_type": "chat_id"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "receive_id": CHAT_ID,
                "msg_type": "interactive",
                "content": json.dumps(card_json, ensure_ascii=False),
            },
            timeout=15,
        )
        result = resp.json()
        if result.get("code") == 0:
            print(f"Sent OK: {result.get('data', {}).get('message_id', '')[:20]}")
            return True
        else:
            print(f"Send error: {json.dumps(result, ensure_ascii=False)}")
            return False


async def main():
    if not all([APP_ID, APP_SECRET, CHAT_ID]):
        print("Missing FEISHU_APP_ID, FEISHU_APP_SECRET, or FEISHU_CHAT_ID")
        return

    # Card 1: Test collapsible_panel with one paper
    card = {
        "header": {
            "title": {"tag": "plain_text", "content": "📚 Env-CS Computing（推送 2 篇）"},
            "template": "blue",
        },
        "elements": [
            # Paper 1
            div("**🔥 [9/10] [Deep Neural Network-guided PSO for Air Quality](https://doi.org/10.1016/j.atmosenv.2025.123456)**"),
            div("👤 Zhang, Wei, Li, Ming, Wang, Jun +2 | 2025-03-15"),
            div("📝 提出了一种结合深度神经网络与粒子群优化的混合模型，用于高精度追踪城市空气质量指数。RMSE较传统方法降低了23%。"),
            div("💡 **核心贡献**：\n  • 提出DNN-PSO混合优化框架\n  • 构建覆盖全球50城市的数据集\n  • 证明了混合方法在非线性建模中的优越性"),
            collapsible("🔧 **潜在应用**", "城市空气质量实时监测、太阳能发电量预测、大气污染预警系统"),
            collapsible("🔬 **方法论评估**", "采用ResNet-50作为骨干网络提取时空特征，结合自适应PSO算法优化超参数。实验使用5-fold交叉验证，消融实验验证了各模块有效性。"),
            collapsible("⚠️ **局限性**", "  • 模型训练需要大量标注数据\n  • PSO优化过程计算开销较大"),
            collapsible("🚀 **未来方向**", "  • 探索Few-shot学习降低数据依赖\n  • 引入轻量化网络提升推理速度"),
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "DOI: 10.1016/j.atmosenv.2025.123456 | 🏷 深度学习, PSO, 空气质量, 时空建模"}]},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "查看论文"}, "url": "https://doi.org/10.1016/j.atmosenv.2025.123456", "type": "primary"},
                {"tag": "button", "text": {"tag": "plain_text", "content": "PDF"}, "url": "https://arxiv.org/pdf/2503.12345", "type": "default"},
            ]},
            {"tag": "hr"},

            # Paper 2
            div("**📄 [8/10] [Transfer Learning for Cross-City PM2.5 Prediction](https://doi.org/10.1021/est.2025.07890)**"),
            div("👤 Park, Kim, Lee | 2025-03-12"),
            div("📝 提出跨城市PM2.5浓度预测的迁移学习框架，利用源城市数据辅助目标城市预测。"),
            div("💡 **核心贡献**：\n  • 设计城市间大气污染特征对齐的域适应模块\n  • 12个中国城市测试中迁移学习提升18%"),
            collapsible("🔧 **应用**", "新设监测站点快速部署、区域联防联控决策支持"),
            collapsible("⚠️ **局限**", "仅验证中国城市，跨国家迁移能力未验证"),
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "DOI: 10.1021/est.2025.07890 | 🏷 迁移学习, PM2.5, 域适应"}]},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "查看论文"}, "url": "https://doi.org/10.1021/est.2025.07890", "type": "primary"},
            ]},
        ],
    }

    print("Sending test card with collapsible_panel...")
    await send_card(card)


if __name__ == "__main__":
    asyncio.run(main())
