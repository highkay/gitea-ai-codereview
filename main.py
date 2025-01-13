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
                logger.warning("未找到PR的diff信息")
                continue

            # 处理每个diff块
            for diff_block in diff_blocks:
                # 解析文件路径和修改行号范围
                parse_result = gitea_client.parse_diff_location(diff_block)
                if not parse_result or not parse_result[0]:  # 检查文件路径是否存在
                    continue
                    
                filepath, start_line, end_line, is_new_file, is_deleted = parse_result
                
                # 跳过二进制文件
                if start_line == 0 and end_line == 0 and not is_new_file and not is_deleted:
                    logger.info(f"跳过二进制文件: {filepath}")
                    continue
                
                # 获取修改部分的上下文代码
                context_content = gitea_client.get_file_content_around_diff(
                    owner, repo, filepath, commit['sha'],
                    start_line, end_line, context_lines=20,
                    is_new_file=is_new_file, is_deleted=is_deleted
                )
                
                # 准备文件状态信息
                file_status = "新文件" if is_new_file else "删除" if is_deleted else "修改"
                
                # 使用AI进行代码审查
                review_content = ai.code_review(
                    diff_block,
                    context_content=context_content,
                    file_status=file_status
                )
                
                try:
                    # 解析审查结果
                    review_result = ai.parse_review_result(review_content)
                    # 添加文件和commit信息
                    review_result.update({
                        'filepath': filepath,
                        'file_status': file_status,
                        'commit_sha': commit['sha'],
                        'commit_message': commit.get('commit', {}).get('message', ''),
                        'commit_url': commit.get('html_url', '')
                    })
                    all_reviews.append(review_result)
                except Exception as e:
                    logger.error(f"解析审查结果失败: {str(e)}")
                    continue

        # 检查是否所有commit都通过审查，且没有High或Critical级别的问题
        all_passed = all(not review['needs_review'] for review in all_reviews)
        has_high_severity_issues = any(
            any(
                problem['severity'] in ['High', 'Critical']
                for issue in review.get('issues', [])
                for problem in issue.get('problems', [])
            )
            for review in all_reviews
        )
        
        lowest_score = min(review['score'] for review in all_reviews) if all_reviews else 0
        
        # 修改自动合并的条件
        if all_passed and not has_high_severity_issues:
            logger.info(f"PR #{pr_number} 通过代码审查且无严重问题，尝试自动合并")
            if gitea_client.merge_pr(owner, repo, pr_number):
                merge_status = "已自动合并"
            else:
                merge_status = "自动合并失败"
                
            # 发送通知（如果配置了webhook）
            if config.webhook.is_init:
                send_notification(
                    f"PR #{pr_number} 代码审查通过 ({merge_status})\n"
                    f"评分：{lowest_score}\n"
                    f"标题：{pr_info['title']}\n"
                    f"提交者：{pr_info['user']['login']}\n"
                    f"链接：{pr_info['html_url']}"
                )
        else:
            reason = "需要进一步审查" if not all_passed else "存在严重问题"
            logger.info(f"PR #{pr_number} {reason}，已添加评论")

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
