"""Opt-in real model smoke. Uses account quota; creates no permanent project."""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Workbench


def main():
    parser=argparse.ArgumentParser(description='真实 Codex 适配器验收（消耗少量账号额度）')
    parser.add_argument('--live',action='store_true',help='明确执行一次真实模型调用')
    if not parser.parse_args().live:
        parser.error('请用 --live 显式开启；常规测试无需运行本脚本。')
    with tempfile.TemporaryDirectory(prefix='product-workbench-smoke-') as directory:
        bench=Workbench(directory)
        p=bench.create_project('适配器验收','只使用虚构测试输入')
        job=bench.prepare(p['id'],'product/framework','只验证连接')
        job['prompt']='这是软件连接测试。不使用任何工具，不搜索，不读取文件。只输出以下中文文本：产品工作台连接验证成功。此文本仅为测试结果，不代表任何产品结论。'
        output=bench.run_codex(job)
        if '产品工作台连接验证成功' not in output:
            raise RuntimeError('模型未返回约定测试标记')
        print('LIVE CODEX PASS: isolated document runner returned expected Chinese output.')


if __name__=='__main__':
    main()
