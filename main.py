import json
from time import sleep
from typing import Dict

import requests
from codereview.copilot import Copilot
from codereview.deepseek import DeepSeek
from gitea.client import GiteaClient
from utils.config import Config
from utils.logger import logger, setup_logging
from fastapi import FastAPI

from utils.utils import create_comment, extract_info_from_request

app = FastAPI()

config = Config()

gitea_clinet = GiteaClient(config.gitea_host, config.gitea_token)

# 根据配置动态选择 AI 实例
if config.copilot_token:
    ai = Copilot(config.copilot_token)
    logger.info("Using Copilot for code review")
elif config.deepseek_key:
    ai = DeepSeek(config.deepseek_key)
    logger.info("Using DeepSeek for code review")
else:
    raise ValueError("No AI service configured. Please set either COPILOT_TOKEN or DEEPSEEK_KEY")


@app.post("/codereview")
async def analyze_code(request_body: Dict):

    owner, repo, sha, ref, pusher, full_name, title, commit_url = (
        extract_info_from_request(request_body)
    )

    if "[skip codereview]" in title:
        return {"message": "Skip codereview"}

    diff_blocks = gitea_clinet.get_diff_blocks(owner, repo, sha)
    if diff_blocks is None:
        return {"message": "Failed to get diff content"}

    current_issue_id = None

    ignored_file_suffix = config.ignored_file_suffix.split(",")

    for i, diff_content in enumerate(diff_blocks, start=1):
        file_path = diff_content.split(" ")[0].split("/")
        file_name = file_path[-1]

        # Ignore the file if it's in the ignored list
        if ignored_file_suffix:
            for suffix in ignored_file_suffix:
                if file_name.endswith(suffix):
                    logger.warning(f"File {file_name} is ignored")
                    continue

        # 使用选定的 AI 实例进行代码审查
        response = ai.code_review(diff_content)

        comment = create_comment(file_name, diff_content, response)
        if i == 1:
            issue_res = gitea_clinet.create_issue(
                owner,
                repo,
                f"Code Review {title}",
                f"本次提交：{commit_url} \n\r 提交人：{pusher} \n\r {comment}",
                ref,
                pusher,
            )
            issue_url = issue_res["html_url"]
            current_issue_id = issue_res["number"]

            logger.success(f"The code review: {issue_url}")

            # Send a notification to the webhook
            if config.webhook.is_init:
                headers = {}
                if config.webhook.header_name and config.webhook.header_value:
                    headers = {config.webhook.header_name: config.webhook.header_value}

                content = (
                    f"Code Review: {title}\n{commit_url}\n\n审查结果: \n{issue_url}"
                )
                request_body_str = config.webhook.request_body.format(
                    content=content,
                    mention=full_name,
                )
                request_body = json.loads(request_body_str, strict=False)
                requests.post(
                    config.webhook.url,
                    headers=headers,
                    json=request_body,
                )

        else:
            gitea_clinet.add_issue_comment(
                owner,
                repo,
                current_issue_id,
                comment,
            )

        logger.info("Sleep for 1.5 seconds...")
        sleep(1.5)

    # 添加对应 AI 的横幅
    gitea_clinet.add_issue_comment(
        owner,
        repo,
        current_issue_id,
        ai.banner,
    )

    return {"message": response}


@app.post("/test")
def test(request_body: str):
    logger.success("Test")
    return {"message": ai.code_review(request_body)}


if __name__ == "__main__":
    import uvicorn

    serv_config = uvicorn.Config(
        "main:app",
        host="0.0.0.0",
        port=3008,
        access_log=True,
        workers=1,
        reload=True,
    )
    server = uvicorn.Server(serv_config)

    setup_logging()
    server.run()
