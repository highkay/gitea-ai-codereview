import json
from time import sleep
from typing import Dict

import requests
from fastapi import FastAPI
from codereview.copilot import Copilot
from codereview.deepseek import DeepSeek
from gitea.client import GiteaClient
from utils.config import Config
from utils.logger import logger, setup_logging

app = FastAPI()
config = Config()
gitea_client = GiteaClient(config.gitea_host, config.gitea_token)

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
async def review_pull_request(request_body: Dict):
    """处理PR的代码审查请求"""
    try:
        # 从请求中提取PR信息
        logger.debug(f"收到请求体: {request_body}")
        
        # 只处理PR打开的事件
        if request_body.get("action") != "opened":
            return {"message": "Ignored non-opened PR event"}
        
        # 提取PR和仓库信息
        pr_info = request_body.get("pull_request")
        repo_info = request_body.get("repository")
        
        if not pr_info or not repo_info:
            raise ValueError("Missing pull_request or repository information")
        
        # 从repository的full_name中提取owner和repo
        repo_full_name = repo_info["full_name"].split("/")
        owner = repo_full_name[0]
        repo = repo_full_name[1]
        pr_number = pr_info["number"]
        
        logger.info(f"开始审查 PR #{pr_number} in {owner}/{repo}")
        logger.info(f"PR标题: {pr_info['title']}")
        logger.info(f"提交者: {pr_info['user']['login']}")

        # 获取PR中的所有commits
        commits = gitea_client.get_pr_commits(owner, repo, pr_number)
        if not commits:
            logger.warning("未找到PR的commits信息")
            return {"message": "No commits found"}

        all_reviews = []
        # 对每个commit进行审查
        for commit in commits:
            # 获取commit的差异内容
            diff_blocks = gitea_client.get_diff_blocks(owner, repo, commit['sha'])
            if not diff_blocks:
                continue

            # 合并所有diff内容
            combined_diff = "\n".join(diff_blocks)
            
            # 使用AI进行代码审查
            review_content = ai.code_review(combined_diff)
            
            # 解析审查结果
            review_result = ai.parse_review_result(review_content)
            # 添加commit信息
            review_result.update({
                'commit_sha': commit['sha'],
                'commit_message': commit.get('commit', {}).get('message', ''),
                'commit_url': commit.get('html_url', '')
            })
            all_reviews.append(review_result)

        # 检查是否所有commit都通过审查
        all_passed = all(not review['needs_review'] for review in all_reviews)
        lowest_score = min(review['score'] for review in all_reviews) if all_reviews else 0
        
        # 使用最低分作为最终评审结果
        final_review = {
            'score': lowest_score,
            'needs_review': not all_passed,
            'issues': [],
            'commit_reviews': [
                {
                    'sha': review['commit_sha'],
                    'message': review['commit_message'],
                    'url': review['commit_url'],
                    'score': review['score'],
                    'passed': not review['needs_review'],
                    'issues': review.get('issues', [])
                }
                for review in all_reviews
            ]
        }
        
        # 收集所有未通过commit的问题并按commit分组
        for review in all_reviews:
            if review['needs_review']:
                final_review['issues'].extend([
                    {
                        **issue,
                        'commit_sha': review['commit_sha'],
                        'commit_message': review['commit_message']
                    }
                    for issue in review.get('issues', [])
                ])
        
        # 修改评论格式化方法以包含commit信息
        gitea_client.add_pr_review_comment(owner, repo, pr_number, final_review)
        
        # 只有当所有commit都通过时才自动合并
        if all_passed:
            logger.info(f"PR #{pr_number} 所有commit都通过代码审查，尝试自动合并")
            if gitea_client.merge_pr(owner, repo, pr_number):
                merge_status = "已自动合并"
            else:
                merge_status = "自动合并失败"
                
            # 发送通知（如果配置了webhook）
            if config.webhook.is_init:
                send_notification(
                    f"PR #{pr_number} 代码审查通过 ({merge_status})\n"
                    f"最低评分：{lowest_score}\n"
                    f"标题：{pr_info['title']}\n"
                    f"提交者：{pr_info['user']['login']}\n"
                    f"链接：{pr_info['html_url']}"
                )
        else:
            logger.info(f"PR #{pr_number} 需要进一步审查，已添加评论")
            
        return {
            "message": "Code review completed",
            "pr_number": pr_number,
            "title": pr_info['title'],
            "submitter": pr_info['user']['login'],
            "score": lowest_score,
            "needs_review": not all_passed,
            "commit_reviews": [
                {
                    "sha": review['commit_sha'],
                    "score": review['score'],
                    "passed": not review['needs_review']
                }
                for review in all_reviews
            ]
        }
        
    except Exception as e:
        logger.error(f"处理PR审查请求时发生错误: {str(e)}")
        return {"error": str(e)}

def send_notification(content: str):
    """发送webhook通知"""
    try:
        headers = {}
        if config.webhook.header_name and config.webhook.header_value:
            headers = {config.webhook.header_name: config.webhook.header_value}

        request_body = json.loads(
            config.webhook.request_body.format(content=content),
            strict=False
        )
        
        requests.post(
            config.webhook.url,
            headers=headers,
            json=request_body,
        )
    except Exception as e:
        logger.error(f"发送通知失败: {str(e)}")

@app.post("/test")
def test(request_body: str):
    """测试AI代码审查功能"""
    logger.info("Testing code review")
    review_content = ai.code_review(request_body)
    review_result = ai.parse_review_result(review_content)
    return review_result

if __name__ == "__main__":
    import uvicorn

    setup_logging()
    
    server = uvicorn.Server(
        uvicorn.Config(
            "main:app",
            host="0.0.0.0",
            port=3008,
            workers=1,
            reload=True
        )
    )
    server.run()
