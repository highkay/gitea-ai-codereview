import os
from dotenv import load_dotenv
import requests
from codereview.ai import AI
from loguru import logger


class DeepSeek(AI):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("DeepSeek API key is required")
        
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com"

    def code_review(self, diff_content: str, model: str = "deepseek-chat") -> str:
        """
        使用 DeepSeek AI 执行代码审查。

        Args:
            diff_content (str): 代码差异的内容
            model (str): 要使用的模型名称，默认为 'deepseek-chat'

        Returns:
            str: AI 的代码审查响应
        """
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        data = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的代码审查助手。请仔细审查提供的代码差异，并提供具体的改进建议。关注代码质量、性能、安全性和最佳实践。"
                },
                {
                    "role": "user",
                    "content": f"{diff_content} 请审查这段代码并提供改进建议"
                }
            ],
            "temperature": 0.1,
            "stream": False
        }

        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                logger.error(f"DeepSeek API 调用失败: {response.text}")
                return f"代码审查失败: {response.text}"
                
        except requests.exceptions.RequestException as e:
            logger.error(f"请求 DeepSeek API 时发生错误: {str(e)}")
            return f"代码审查过程中发生错误: {str(e)}"

    def get_access_token(self, renew: bool = False) -> str:
        """
        获取访问令牌。对于 DeepSeek，直接返回 API key，因为它不需要额外的令牌交换。

        Args:
            renew (bool): 是否更新令牌（对 DeepSeek 无效）

        Returns:
            str: API key
        """
        return self.api_key

    @property
    def banner(self) -> str:
        """
        返回 DeepSeek 的横幅信息。

        Returns:
            str: 横幅 Markdown 文本
        """
        return "## Powered by DeepSeek AI\n" 