#!/usr/bin/env python3
import os
import requests
import re
import logging
from typing import List, Dict, Optional

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ChangelogGenerator:
    def __init__(self, current_tag: str, github_token: str, repo_owner: str, repo_name: str):
        self.current_tag = current_tag
        self.github_token = github_token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    def get_all_releases(self) -> List[Dict]:
        """获取所有 releases"""
        logger.info("获取所有 releases...")
        url = f"{self.base_url}/releases"
        releases = []
        page = 1
        
        while True:
            response = requests.get(f"{url}?page={page}&per_page=100", headers=self.headers)
            if response.status_code != 200:
                logger.error(f"获取 releases 失败: {response.status_code} - {response.text}")
                break
            
            page_releases = response.json()
            if not page_releases:
                break
                
            releases.extend(page_releases)
            page += 1
            
            # 安全限制，最多获取10页
            if page > 10:
                logger.warning("达到页面限制，停止获取更多 releases")
                break
        
        logger.info(f"共获取 {len(releases)} 个 releases")
        return releases
    
    def is_formal_version(self, tag: str) -> bool:
        """检查是否为正式版"""
        return bool(re.match(r'^v\d+\.\d+\.\d+$', tag))
    
    def get_current_minor_version(self) -> str:
        """获取当前次版本号（如 v2.3）"""
        match = re.match(r'^(v\d+\.\d+)\.\d+', self.current_tag)
        if match:
            return match.group(1)
        logger.warning(f"无法解析当前版本号: {self.current_tag}")
        return ""
    
    def extract_clean_content(self, body: str) -> str:
        """提取标记之前的内容"""
        if not body:
            return ""
        
        marker = "## 历史版本更新内容"
        marker_pos = body.find(marker)
        
        if marker_pos != -1:
            # 返回标记之前的所有内容
            clean_content = body[:marker_pos].strip()
            logger.info(f"使用标记提取内容，长度: {len(clean_content)}")
            return clean_content
        else:
            # 如果没有标记，返回整个内容（兼容旧版本）
            logger.info("未找到标记，返回完整内容")
            return body.strip()
    
    def extract_version_number(self, version_string: str) -> str:
        """提取纯净版本号"""
        match = re.search(r'v\d+\.\d+\.\d+', version_string)
        return match.group(0) if match else version_string
    
    def parse_version(self, version: str) -> tuple:
        """解析版本号为数字元组"""
        match = re.match(r'v(\d+)\.(\d+)\.(\d+)', version)
        if match:
            return tuple(map(int, match.groups()))
        return (0, 0, 0)
    
    def collect_historical_versions(self) -> List[Dict]:
        """收集当前次版本的历史正式版"""
        logger.info(f"开始收集历史版本，当前版本: {self.current_tag}")
        
        current_minor = self.get_current_minor_version()
        if not current_minor:
            return []
        
        all_releases = self.get_all_releases()
        historical_versions = []
        
        for release in all_releases:
            tag = release['tag_name']
            
            # 跳过当前版本
            if tag == self.current_tag:
                continue
                
            # 只处理正式版
            if not self.is_formal_version(tag):
                continue
            
            # 检查是否属于当前次版本
            if tag.startswith(current_minor + '.'):
                historical_versions.append({
                    'tag': tag,
                    'body': release.get('body', ''),
                    'name': release.get('name', ''),
                    'created_at': release.get('created_at', '')
                })
                logger.info(f"收集到历史版本: {tag}")
        
        # 按版本号排序（从旧到新）
        historical_versions.sort(key=lambda x: self.parse_version(x['tag']))
        
        logger.info(f"最终收集到 {len(historical_versions)} 个历史正式版")
        return historical_versions
    
    def create_folded_block(self, version_info: Dict) -> str:
        """创建折叠块"""
        clean_version = self.extract_version_number(version_info['tag'])
        content = version_info['clean_content']
        
        return f"""<details>
<summary>{clean_version} 版本更新内容</summary>

{content}

</details>"""
    
    def generate_historical_section(self, historical_versions: List[Dict]) -> str:
        """生成历史版本区块"""
        if not historical_versions:
            logger.info("没有历史版本，跳过生成历史区块")
            return ""
        
        # 处理每个版本的内容
        processed_versions = []
        for version in historical_versions:
            clean_content = self.extract_clean_content(version['body'])
            if clean_content:  # 只处理有内容的版本
                version['clean_content'] = clean_content
                processed_versions.append(version)
        
        # 按版本号倒序排列（最新在前）
        processed_versions.sort(key=lambda x: self.parse_version(x['tag']), reverse=True)
        
        # 创建折叠块
        folded_blocks = [self.create_folded_block(version) for version in processed_versions]
        
        historical_section = "## 历史版本更新内容\n\n" + "\n\n".join(folded_blocks)
        logger.info(f"生成历史区块，包含 {len(folded_blocks)} 个版本")
        
        return historical_section
    
    def merge_into_current_changelog(self, current_content: str, historical_section: str) -> str:
        """将历史区块合并到当前 changelog"""
        if not historical_section:
            logger.info("没有历史区块，返回原始内容")
            return current_content
        
        # 查找构建信息的开始位置
        build_info_marker = "**构建信息**:"
        build_info_pos = current_content.find(build_info_marker)
        
        if build_info_pos != -1:
            # 找到构建信息的末尾
            # 假设构建信息后没有其他重要内容，我们在构建信息后插入
            insert_pos = current_content.find('\n', build_info_pos)
            while insert_pos != -1 and insert_pos < len(current_content) - 1:
                # 查找构建信息的结束（空行或新标题）
                next_chars = current_content[insert_pos:insert_pos+10]
                if next_chars.strip() == "" or next_chars.startswith('\n##'):
                    break
                insert_pos = current_content.find('\n', insert_pos + 1)
            
            if insert_pos == -1:
                insert_pos = len(current_content)
            
            logger.info(f"在构建信息后插入历史区块，位置: {insert_pos}")
            return (current_content[:insert_pos] + 
                    "\n\n" + historical_section + 
                    current_content[insert_pos:])
        else:
            # 如果没有构建信息，在CDK链接后插入
            cdk_marker = "[已有 Mirror酱 CDK"
            cdk_pos = current_content.find(cdk_marker)
            
            if cdk_pos != -1:
                # 找到CDK链接的末尾
                cdk_end = current_content.find('\n', cdk_pos)
                if cdk_end == -1:
                    cdk_end = len(current_content)
                
                logger.info(f"在CDK链接后插入历史区块")
                return (current_content[:cdk_end] + 
                        "\n\n" + historical_section + 
                        current_content[cdk_end:])
            else:
                # 作为最后手段，在末尾添加
                logger.info("在末尾插入历史区块")
                return current_content + "\n\n" + historical_section
    
    def generate_comprehensive_changelog(self) -> str:
        """生成完整的 changelog"""
        logger.info("开始生成完整 changelog")
        
        # 读取当前生成的 changelog
        try:
            with open('current_changelog.md', 'r', encoding='utf-8') as f:
                current_content = f.read()
            logger.info(f"读取当前 changelog，长度: {len(current_content)}")
        except FileNotFoundError:
            logger.error("找不到 current_changelog.md 文件")
            return ""
        
        # 收集并处理历史版本
        historical_versions = self.collect_historical_versions()
        historical_section = self.generate_historical_section(historical_versions)
        
        # 合并到当前内容
        final_content = self.merge_into_current_changelog(current_content, historical_section)
        
        logger.info("完整 changelog 生成完成")
        return final_content

def main():
    # 从环境变量获取参数
    current_tag = os.environ.get('CURRENT_TAG')
    github_token = os.environ.get('GITHUB_TOKEN')
    github_repository = os.environ.get('GITHUB_REPOSITORY')
    github_repository_owner = os.environ.get('GITHUB_REPOSITORY_OWNER')
    
    if not all([current_tag, github_token, github_repository]):
        logger.error("缺少必要的环境变量")
        return
    
    # 解析仓库信息
    repo_parts = github_repository.split('/')
    if len(repo_parts) != 2:
        logger.error(f"无效的仓库名称: {github_repository}")
        return
    
    repo_owner = repo_parts[0]
    repo_name = repo_parts[1]
    
    logger.info(f"开始处理: 仓库={github_repository}, 版本={current_tag}")
    
    # 生成完整 changelog
    generator = ChangelogGenerator(current_tag, github_token, repo_owner, repo_name)
    final_content = generator.generate_comprehensive_changelog()
    
    # 写入最终文件
    if final_content:
        with open('CHANGES.md', 'w', encoding='utf-8') as f:
            f.write(final_content)
        logger.info("CHANGES.md 写入成功")
    else:
        logger.error("生成 changelog 失败")

if __name__ == "__main__":
    main()