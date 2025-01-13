import re
import requests
from typing import List, Dict, Optional

from utils.logger import logger


class GiteaClient:
    def __init__(self, host: str, token: str):
        """初始化 Gitea 客户端
        
        Args:
            host (str): Gitea 服务器地址
            token (str): 访问令牌
        """
        self.host = host.rstrip('/')
        self.token = token
        self.headers = {"Authorization": f"token {self.token}"}

    def get_diff_blocks(self, owner: str, repo: str, sha: str) -> str:
        # Get the diff of the commit
        endpoint = f"{self.host}/api/v1/repos/{owner}/{repo}/git/commits/{sha}.diff?access_token={self.token}"
        res = requests.get(endpoint)
        if res.status_code == 200 and res.text != "":
            diff_blocks = re.split("diff --git ", res.text.strip())
            # 去掉空字符串
            diff_blocks = [block for block in diff_blocks if block]
            # 移除 'diff --git ' 前缀
            diff_blocks = [block.replace("diff --git ", "") for block in diff_blocks]
            return diff_blocks
        else:
            logger.error(f"Failed to get diff content: {res.text}")
            return None

    def create_issue(
        self, owner: str, repo: str, title: str, body: str, ref: str, pusher: str
    ):
        endpoint = f"{self.host}/api/v1/repos/{owner}/{repo}/issues?access_token={self.token}"
        data = {
            "assignee": pusher,
            "assignees": [pusher],
            "body": body,
            "closed": False,
            "due_date": None,
            "labels": [],
            "milestone": None,
            "ref": ref,
            "title": title,
        }
        res = requests.post(endpoint, json=data)
        if res.status_code == 201:
            return res.json()
        else:
            logger.error(f"Failed to create issue: {res.text}")
            return None

    def add_issue_comment(self, owner, repo, issue_id, comment):
        endpoint = f"{self.host}/api/v1/repos/{owner}/{repo}/issues/{issue_id}/comments?access_token={self.token}"
        data = {
            "body": comment,
        }
        res = requests.post(endpoint, json=data)
        if res.status_code == 201:
            return res.json()
        else:
            return None

    def extract_info_from_request(request_body):
        full_name = request_body["repository"]["full_name"].split("/")
        owner = full_name[0]
        repo = full_name[1]
        sha = request_body["after"]

        ref = request_body["ref"]
        pusher = request_body["pusher"]["login"]
        full_name = request_body["pusher"]["full_name"]
        title = request_body["commits"][0]["message"]
        commit_url = request_body["commits"][0]["url"]

        return owner, repo, sha, ref, pusher, full_name, title, commit_url

    def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> List[str]:
        """获取PR的所有差异内容，过滤掉SQL文件
        
        Args:
            owner (str): 仓库所有者
            repo (str): 仓库名称
            pr_number (int): PR编号
            
        Returns:
            List[str]: 差异内容列表
        """
        endpoint = f"{self.host}/api/v1/repos/{owner}/{repo}/pulls/{pr_number}.diff"
        
        try:
            response = requests.get(endpoint, headers=self.headers)
            response.raise_for_status()
            
            if response.text:
                diff_blocks = re.split("diff --git ", response.text.strip())
                # 过滤空字符串和SQL文件
                diff_blocks = [
                    block for block in diff_blocks 
                    if block and not any(f.endswith('.sql') for f in block.split('\n', 1))
                ]
                logger.debug(f"获取到 {len(diff_blocks)} 个差异块")
                return diff_blocks
            logger.warning("PR没有差异内容")
            return []
        except Exception as e:
            logger.error(f"获取PR差异失败: {str(e)}")
            return []

    def get_pr_commits(self, owner: str, repo: str, pr_number: int) -> list:
        """获取PR中的所有commit信息
        
        API: GET /repos/{owner}/{repo}/pulls/{index}/commits
        """
        endpoint = f"{self.host}/api/v1/repos/{owner}/{repo}/pulls/{pr_number}/commits"
        
        try:
            response = requests.get(endpoint, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取PR commits失败: {str(e)}")
            return []

    def approve_pr(self, owner: str, repo: str, pr_number: int) -> bool:
        """批准PR
        
        Args:
            owner (str): 仓库所有者
            repo (str): 仓库名称
            pr_number (int): PR编号
            
        Returns:
            bool: 是否成功
        """
        endpoint = f"{self.host}/api/v1/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        data = {
            "body": "代码审查通过",
            "state": "APPROVED"
        }
        
        try:
            response = requests.post(endpoint, headers=self.headers, json=data)
            response.raise_for_status()
            logger.info(f"已批准PR #{pr_number}")
            return True
        except Exception as e:
            logger.error(f"批准PR失败: {str(e)}")
            return False

    def add_pr_review_comment(self, owner: str, repo: str, pr_number: int, review_result: Dict) -> bool:
        """添加PR评论并设置审查状态
        
        Args:
            owner (str): 仓库所有者
            repo (str): 仓库名称
            pr_number (int): PR编号
            review_result (dict): 审查结果
            
        Returns:
            bool: 是否成功
        """
        endpoint = f"{self.host}/api/v1/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        
        comment = self._format_review_comment(review_result)
        
        # 根据审查结果决定状态
        state = "APPROVED" if not review_result['needs_review'] else "COMMENT"
        
        data = {
            "body": comment,
            "state": state
        }
        
        try:
            response = requests.post(endpoint, headers=self.headers, json=data)
            response.raise_for_status()
            logger.info(f"已添加PR #{pr_number} 的评论和状态: {state}")
            return True
        except Exception as e:
            logger.error(f"添加PR评论和状态失败: {str(e)}")
            return False

    def _format_review_comment(self, review_result: Dict) -> str:
        """格式化评论内容
        
        Args:
            review_result (dict): 审查结果
            
        Returns:
            str: 格式化后的评论内容
        """
        # 评审结果部分使用引用块样式
        comment = "> # 📊 代码评审结果\n>\n"
        comment += f"> **总体评分**: {review_result['score']}\n>\n"
        comment += f"> **状态**: {'✅ 通过' if not review_result['needs_review'] else '❌ 需要修改'}\n>\n"
        
        if not review_result['needs_review']:
            comment += "> 🎉 所有提交的代码质量良好，自动通过审查。\n"
        else:
            comment += "> ⚠️ 部分提交需要修改，请查看下方详情。\n"
        
        # 提交详情部分使用普通样式
        comment += "\n---\n\n"
        comment += "# 📝 提交详情\n\n"
        
        for commit_review in review_result['commit_reviews']:
            status_emoji = "✅" if commit_review['passed'] else "❌"
            comment += (
                f"## {status_emoji} Commit [{commit_review['sha'][:7]}]({commit_review['url']})\n\n"
                f"**提交信息**: {commit_review['message']}\n"
                f"**评分**: {commit_review['score']}\n"
                f"**状态**: {'通过' if commit_review['passed'] else '需要修改'}\n\n"
            )
            
            if not commit_review['passed']:
                for issue in commit_review['issues']:
                    comment += f"### 🔍 {issue['category']}：{issue['score']}/{issue['max_score']}\n\n"
                    
                    for problem in issue['problems']:
                        severity_emoji = {
                            'Critical': '🚨',
                            'High': '⚠️',
                            'Medium': '⚡',
                            'Low': 'ℹ️'
                        }.get(problem['severity'], '🔍')
                        
                        comment += f"#### {severity_emoji} {problem['severity']}\n\n"
                        comment += f"**问题**：{problem['description']}\n\n"
                        if problem['suggestion']:
                            comment += f"**建议**：{problem['suggestion']}\n\n"
                        if problem['example']:
                            comment += "**示例**：\n```\n" + problem['example'] + "\n```\n\n"
                    
                    comment += "---\n\n"
                    
        return comment

    def merge_pr(self, owner: str, repo: str, pr_number: int) -> bool:
        """合并PR
        
        Args:
            owner (str): 仓库所有者
            repo (str): 仓库名称
            pr_number (int): PR编号
            
        Returns:
            bool: 是否成功
        """
        # 在合并之前检查PR状态
        pr_endpoint = f"{self.host}/api/v1/repos/{owner}/{repo}/pulls/{pr_number}"
        pr_response = requests.get(pr_endpoint, headers=self.headers)
        pr_info = pr_response.json()

        if not pr_info.get('mergeable'):
            logger.error(f"PR #{pr_number} 当前无法合并")
            return False

        endpoint = f"{self.host}/api/v1/repos/{owner}/{repo}/pulls/{pr_number}/merge"
        
        # 根据API文档,需要提供合并选项
        data = {
            "Do": "merge",  # 可选值: merge, rebase, rebase-merge, squash
            "MergeMessageField": "Automatically merged by code review bot",
            "MergeTitleField": f"Merge pull request #{pr_number}",
            "force_merge": True  # 添加force_merge选项
        }
        
        try:
            response = requests.post(endpoint, headers=self.headers, json=data)
            response.raise_for_status()
            logger.info(f"已合并PR #{pr_number}")
            return True
        except Exception as e:
            logger.error(f"合并PR失败: {str(e)}")
            # 添加更详细的错误日志
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"错误响应: {e.response.text}")
            return False
