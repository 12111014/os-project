"""Robustness probe for the requirement_parser agent.

Feeds a battery of vague / contradictory / English / overloaded / out-of-scope
requests to the parser and prints the normalized IR + confidence + reasoning.
Run:  python -m fs_agent.robustness_probe
"""
import json
import traceback
from dotenv import load_dotenv

load_dotenv(verbose=False)

from fs_agent.agents.requirement_parser_agent import RequirementParserAgent

CASES = {
    "R1_极度模糊": "随便给我做个文件系统就行。",
    "R2_自相矛盾": "我要一个纯内存的临时文件系统，速度越快越好；但是断电、卸载之后数据绝对不能丢失，必须永久保存。",
    "R3_英文_passthrough": "Build a passthrough FUSE filesystem that mirrors an existing host directory. Support extended attributes and symlinks. No journaling needed. It must be production-ready and pass Linux compatibility test suites.",
    "R4_特性全家桶": "我需要一个企业级高性能持久化文件系统：硬链接、符号链接、扩展属性、完整权限、日志与崩溃一致性都要，并且要做高性能基准测试和 Linux 兼容性认证。",
    "R5_越界不可实现": "做一个支持区块链去中心化存储、量子加密和 AI 自动压缩的文件系统，还要能挖矿。",
    "R6_一句话最小": "in-memory fs, just basic file read/write, nothing fancy.",
}


def summarize(r):
    return {
        "success": getattr(r, "success", None),
        "confidence": getattr(r, "confidence", None),
        "language": r.language,
        "storage": r.storage.type,
        "features": {
            "symlink": r.features.symlink,
            "hardlink": r.features.hardlink,
            "xattrs": r.features.xattrs,
            "journaling": r.features.journaling,
            "permissions": r.features.permissions,
        },
        "n_operations": len(r.operations),
        "operations": r.operations,
        "validation": r.validation.model_dump(),
        "reasoning": (r.reasoning or "")[:600],
    }


def main():
    agent = RequirementParserAgent()
    out = {}
    for name, req in CASES.items():
        print(f"\n{'='*70}\n>>> {name}\nREQUEST: {req}\n{'-'*70}")
        try:
            r = agent.perform_task({"user_request": req})
            s = summarize(r)
            out[name] = s
            print("RESULT_JSON " + json.dumps(s, ensure_ascii=False))
        except Exception as e:
            out[name] = {"error": str(e)}
            print("ERROR " + str(e))
            traceback.print_exc()

    print("\n\n##### FINAL_SUMMARY #####")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
