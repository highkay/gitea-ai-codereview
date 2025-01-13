import os
from dotenv import load_dotenv
import requests
from codereview.ai import AI
from loguru import logger
import re


class DeepSeek(AI):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("DeepSeek API key is required")
        
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com"
        self.pass_score = int(os.getenv('DEEPSEEK_PASS_SCORE', 70))

    def code_review(self, diff_content: str, model: str = "deepseek-chat") -> str:
        """使用 DeepSeek AI 执行代码审查"""
        review_prompt = f'''你是一个严格的高级代码审查专家。请仔细审查提供的代码差异，并按照以下维度进行严格评估：

1. 代码质量
   - 代码可读性：函数长度（建议不超过100行），代码缩进，空行使用
   - 命名规范：变量/函数/类命名是否符合语言规范，是否具有足够描述性
   - 代码结构：单一职责原则，代码重复度，模块化程度
   - 代码注释：是否包含必要的注释，注释是否清晰准确
   - 异常处理：是否妥善处理各种异常情况

2. 性能优化
   - 时间复杂度：算法选择是否合适，是否存在优化空间
   - 空间复杂度：内存使用是否合理，是否存在内存泄漏风险
   - 并发处理：是否正确处理并发场景，是否存在死锁风险
   - 资源管理：数据库连接、文件句柄等资源是否及时释放
   - 缓存使用：是否合理使用缓存提升性能

3. 安全性
   - 输入验证：是否验证所有外部输入，包括参数类型、范围和格式
   - 安全漏洞：SQL注入、XSS、CSRF等常见安全问题的防范
   - 敏感信息：密码、密钥等敏感信息的处理是否安全
   - 权限控制：是否实施了适当的访问控制和权限检查
   - 数据加密：敏感数据的传输和存储是否加密

4. 最佳实践
   - 设计模式：是否合理使用设计模式，避免反模式
   - 代码规范：是否符合团队/语言的编码规范
   - 测试覆盖：是否包含单元测试，测试是否充分
   - 文档完整性：是否包含必要的文档说明
   - 可维护性：代码是否容易理解和维护

扣分标准（总分100分）：
- Critical: 严重问题，每个问题扣20-25分
- High: 重要问题，每个问题扣10-15分
- Medium: 中等问题，每个问题扣5-8分
- Low: 轻微问题，每个问题扣1-3分

返回格式示例：

1. 得分高于等于{self.pass_score}分且没有High及以上级别问题时：

# 总体评分：85

PASS

2. 得分低于{self.pass_score}分或存在High及以上级别问题时：

# 总体评分：65

## Critical: 函数过长，超过100行

问题：process_data 函数包含了过多的业务逻辑
建议：将数据验证、业务处理、结果格式化拆分为独立函数
示例：

    def validate_input(data):
        # 输入验证逻辑
    
    def process_business(validated_data):
        # 业务处理逻辑
    
    def format_result(result):
        # 结果格式化逻辑

## Medium: 变量命名不规范

问题：使用了 a, b, tmp 等无意义的变量名
建议：使用描述性的命名，反映变量用途
示例：

- 将 tmp_list 改为 processed_items
- 将 a 改为 user_count
- 将 b 改为 total_amount

## High: 嵌套循环导致时间复杂度过高

问题：两层 for 循环遍历查找匹配项
建议：使用哈希表存储查找项，将时间复杂度从 O(n²) 降低到 O(n)
示例：

    # 优化前
    for item in items:
        for target in targets:
            if item.id == target.id:
                # 处理逻辑
    
    # 优化后
    targets_map = {{target.id: target for target in targets}}
    for item in items:
        if item.id in targets_map:
            # 处理逻辑

## Low: 缺少输入验证

问题：直接使用外部输入数据
建议：添加参数类型和范围检查
示例：

    def process_user_data(user_id: int, data: dict):
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("Invalid user_id")
        if not data or not isinstance(data, dict):
            raise ValueError("Invalid data format")

## Medium: 缺少函数文档

问题：关键函数缺少文档说明
建议：添加包含参数说明、返回值、异常说明的 docstring

请严格按照以上格式输出评估结果。对于得分低于{self.pass_score}分的情况，每个问题必须包含：1. 严重程度（Critical/High/Medium/Low）2. 问题描述3. 具体的修复建议4. 示例代码（如适用）'''

        messages = [
            {
                "role": "system",
                "content": review_prompt
            },
            {
                "role": "user",
                "content": f"请审查以下代码差异：\n\n{diff_content}"
            }
        ]

        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        data = {
            "model": model,
            "messages": messages,
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

    def parse_review_result(self, review_content: str) -> dict:
        """解析AI的审查结果
        
        Args:
            review_content (str): AI返回的审查内容
            
        Returns:
            dict: 包含解析结果的字典，格式如下：
            {
                'score': int,                # 总体评分
                'needs_review': bool,        # 是否需要人工审查
                'issues': [                  # 问题列表（仅在需要审查时存在）
                    {
                        'category': str,     # 问题类别（代码质量/性能优化/安全性/最佳实践）
                        'score': int,        # 该类别得分
                        'max_score': int,    # 该类别满分
                        'problems': [        # 该类别下的具体问题
                            {
                                'severity': str,     # 严重程度
                                'description': str,  # 问题描述
                                'suggestion': str,   # 修复建议
                                'example': str,      # 示例代码（可选）
                            }
                        ]
                    }
                ]
            }
        """
        try:
            # 初始化返回结果
            result = {
                'score': 0,
                'needs_review': True,
                'issues': []
            }
            
            # 提取总分
            score_match = re.search(r'总体评分：(\d+)', review_content)
            if not score_match:
                logger.error("未找到总体评分")
                return result
            
            result['score'] = int(score_match.group(1))
            result['needs_review'] = result['score'] < self.pass_score
            
            # 如果是PASS，直接返回
            if 'PASS' in review_content:
                result['needs_review'] = False
                return result
            
            # 解析各个类别的问题
            categories = {
                '代码质量': 30,
                '性能优化': 25,
                '安全性': 25,
                '最佳实践': 20
            }
            
            for category, max_score in categories.items():
                # 匹配类别得分
                category_pattern = rf'{category}：(\d+)/{max_score}'
                category_match = re.search(category_pattern, review_content)
                if not category_match:
                    continue
                
                category_score = int(category_match.group(1))
                
                # 提取该类别下的所有问题
                category_content = re.search(
                    rf'{category}：\d+/{max_score}\n(.*?)(?=\n\n|\Z)', 
                    review_content, 
                    re.DOTALL
                )
                if not category_content:
                    continue
                
                problems = []
                # 匹配问题块
                problem_blocks = re.finditer(
                    r'- (Critical|High|Medium|Low): ([^\n]*)\n(?:\s+\* 问题：([^\n]*)\n)?(?:\s+\* 建议：([^\n]*)\n)?(?:\s+\* 示例：\n```[^\n]*\n(.*?)```)?',
                    category_content.group(1),
                    re.DOTALL
                )
                
                for block in problem_blocks:
                    problem = {
                        'severity': block.group(1),
                        'description': block.group(2).strip(),
                        'suggestion': block.group(4).strip() if block.group(4) else '',
                        'example': block.group(5).strip() if block.group(5) else ''
                    }
                    problems.append(problem)
                
                if problems:
                    result['issues'].append({
                        'category': category,
                        'score': category_score,
                        'max_score': max_score,
                        'problems': problems
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"解析审查结果失败: {str(e)}")
            logger.debug(f"原始内容: {review_content}")
            return {
                'score': 0,
                'needs_review': True,
                'issues': []
            }

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