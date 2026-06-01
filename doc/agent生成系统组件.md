
## agent
langchain 

deepagents 基于langchain，开箱即用构建agent
核心亮点（这就是“Deep”所在）：

- 内置规划工具：[write_todos](https://zhida.zhihu.com/search?content_id=272753771&content_type=Article&match_order=1&q=write_todos&zd_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJ6aGlkYV9zZXJ2ZXIiLCJleHAiOjE3ODAwNDIwNzMsInEiOiJ3cml0ZV90b2RvcyIsInpoaWRhX3NvdXJjZSI6ImVudGl0eSIsImNvbnRlbnRfaWQiOjI3Mjc1Mzc3MSwiY29udGVudF90eXBlIjoiQXJ0aWNsZSIsIm1hdGNoX29yZGVyIjoxLCJ6ZF90b2tlbiI6bnVsbH0.2jc0dD8u_GqNvXAC8H1tndp3Ua2IZk_gz7oV_cVKJTM&zhida_source=entity) —— 自动把大任务拆成 Todo List，并动态调整计划。
- 虚拟文件系统：内置 ls、read_file、write_file、edit_file、grep 等工具，把中间结果“卸载”到文件，避免上下文过长导致 token 溢出。
- Subagents）：通过 task 工具动态生成隔离的子智能体，每个子智能体有独立上下文，不会互相干扰。
- 其他内置：Shell 执行（sandbox 支持）、Skills 系统、上下文压缩、中间件架构、状态后端等。
- create_deep_agent() 一行调用，返回一个预配置好的 Compiled LangGraph，开箱即用却保留了 LangGraph 的所有高级特性（streaming、checkpointer、Studio 等）。

https://zhuanlan.zhihu.com/p/2025282637049151789

claude agent sdk


LangGraph 是由 LangChain 团队开发的一个**低层级 Agent 编排框架**，专为构建有状态（Stateful）、长时运行的 AI 工作流而设计。

与传统的线性 LLM 调用链不同，LangGraph 将工作流建模为**有向图（Directed Graph）**：

- **节点（Node）**：执行具体操作的函数（如调用 LLM、执行工具、处理数据）
- **边（Edge）**：定义节点之间的流转路径，支持条件分支
- **状态（State）**：在整个工作流中共享并传递的数据

![[Pasted image 20260528151153.png]]

https://www.runoob.com/ai-agent/langgraph-quick-start.html
https://docs.langchain.com/oss/python/langgraph/overview

参考架构
```
FilesystemAgentSystem
  ├── Requirement Parser
  │    └── 把自然语言需求转成结构化文件系统规格
  │
  ├── Architecture Planner
  │    └── 设计 inode、directory、storage、journal、FUSE ops
  │
  ├── Code Generator
  │    └── 生成 C/libfuse 或 Rust 文件系统代码
  │
  ├── Build Runner
  │    └── cmake / ninja / cargo build
  │
  ├── Mount Runner
  │    └── 创建临时目录并挂载 FUSE 文件系统
  │
  ├── Test Runner
  │    ├── 基础 POSIX 测试
  │    ├── fio 压测
  │    ├── xfstests generic tests
  │    └── crash / fsync / rename 测试
  │
  ├── Debug Agent
  │    └── 读取日志、定位失败、生成 patch
  │
  └── Report Generator
       └── 输出测试报告、diff、风险说明
```

## benchmark

loop image测试
```shell
mkdir -p ~/fsbench/images ~/fsbench/mnt

truncate -s 16G ~/fsbench/images/candidate.img
truncate -s 16G ~/fsbench/images/ext4.img
truncate -s 16G ~/fsbench/images/ext4noj.img
truncate -s 16G ~/fsbench/images/ext2.img
```
格式化
```shell
# candidate
./mkfs.agentfs ~/fsbench/images/candidate.img

# ext4 default
mkfs.ext4 -F ~/fsbench/images/ext4.img

# ext4 no journal
mkfs.ext4 -F -O ^has_journal ~/fsbench/images/ext4noj.img

# ext2
mkfs.ext2 -F ~/fsbench/images/ext2.img
```
挂载：
```shell
sudo mkdir -p ~/fsbench/mnt/candidate ~/fsbench/mnt/ext4 ~/fsbench/mnt/ext4noj ~/fsbench/mnt/ext2

sudo mount -o loop ~/fsbench/images/candidate.img ~/fsbench/mnt/candidate
sudo mount -o loop ~/fsbench/images/ext4.img ~/fsbench/mnt/ext4
sudo mount -o loop ~/fsbench/images/ext4noj.img ~/fsbench/mnt/ext4noj
sudo mount -o loop ~/fsbench/images/ext2.img ~/fsbench/mnt/ext2
```

filebench
比较老的项目，多年未更新
git源码编译安装，可定义测试负载
官方的负载样例file server：
```shell
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#
#
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

set $dir=/tmp
set $nfiles=10000
set $meandirwidth=20
set $filesize=cvar(type=cvar-gamma,parameters=mean:131072;gamma:1.5)
set $nthreads=50
set $iosize=1m
set $meanappendsize=16k
set $runtime=60

define fileset name=bigfileset,path=$dir,size=$filesize,entries=$nfiles,dirwidth=$meandirwidth,prealloc=80

define process name=filereader,instances=1
{
  thread name=filereaderthread,memsize=10m,instances=$nthreads
  {
    flowop createfile name=createfile1,filesetname=bigfileset,fd=1
    flowop writewholefile name=wrtfile1,srcfd=1,fd=1,iosize=$iosize
    flowop closefile name=closefile1,fd=1
    flowop openfile name=openfile1,filesetname=bigfileset,fd=1
    flowop appendfilerand name=appendfilerand1,iosize=$meanappendsize,fd=1
    flowop closefile name=closefile2,fd=1
    flowop openfile name=openfile2,filesetname=bigfileset,fd=1
    flowop readwholefile name=readfile1,fd=1,iosize=$iosize
    flowop closefile name=closefile3,fd=1
    flowop deletefile name=deletefile1,filesetname=bigfileset
    flowop statfile name=statfile1,filesetname=bigfileset
  }
}

echo  "File-server Version 3.0 personality successfully loaded"

run $runtime
```

用了无journal的ext4和xfs跑评测
ext4noj
```
statfile1            162701ops     2709ops/s   0.0mb/s    0.008ms/op [0.001ms - 558.926ms]
deletefile1          162691ops     2709ops/s   0.0mb/s    0.155ms/op [0.008ms - 652.914ms]
closefile3           162702ops     2709ops/s   0.0mb/s    0.003ms/op [0.000ms - 6.731ms]
readfile1            162702ops     2709ops/s 356.5mb/s    1.048ms/op [0.003ms - 766.823ms]
openfile2            162702ops     2709ops/s   0.0mb/s    0.020ms/op [0.001ms - 131.899ms]
closefile2           162702ops     2709ops/s   0.0mb/s    0.003ms/op [0.001ms - 26.878ms]
appendfilerand1      162703ops     2709ops/s  21.2mb/s    1.585ms/op [0.003ms - 624.052ms]
openfile1            162703ops     2709ops/s   0.0mb/s    0.022ms/op [0.001ms - 104.511ms]
closefile1           162703ops     2709ops/s   0.0mb/s    0.003ms/op [0.001ms - 17.593ms]
wrtfile1             162738ops     2710ops/s 335.8mb/s   13.962ms/op [0.003ms - 1409.943ms]
createfile1          162750ops     2710ops/s   0.0mb/s    0.101ms/op [0.006ms - 127.310ms]
69.127: IO Summary: 1789797 ops 29801.968 ops/s 2709/5419 rd/wr 713.4mb/s 1.537ms/op

```
xfs
```
statfile1            175120ops     2918ops/s   0.0mb/s    0.004ms/op [0.001ms - 5.226ms]
deletefile1          175120ops     2918ops/s   0.0mb/s    0.136ms/op [0.008ms - 208.296ms]
closefile3           175120ops     2918ops/s   0.0mb/s    0.002ms/op [0.001ms - 4.899ms]
readfile1            175121ops     2918ops/s 384.0mb/s    0.450ms/op [0.002ms - 151.408ms]
openfile2            175121ops     2918ops/s   0.0mb/s    0.021ms/op [0.001ms - 92.358ms]
closefile2           175121ops     2918ops/s   0.0mb/s    0.002ms/op [0.001ms - 28.287ms]
appendfilerand1      175121ops     2918ops/s  22.8mb/s    1.341ms/op [0.003ms - 174.442ms]
openfile1            175124ops     2918ops/s   0.0mb/s    0.026ms/op [0.001ms - 93.655ms]
closefile1           175124ops     2918ops/s   0.0mb/s    0.003ms/op [0.001ms - 18.502ms]
wrtfile1             175128ops     2918ops/s 362.4mb/s   13.785ms/op [0.002ms - 335.075ms]
createfile1          175170ops     2919ops/s   0.0mb/s    0.102ms/op [0.005ms - 150.484ms]
62.415: IO Summary: 1926390 ops 32099.856 ops/s 2918/5836 rd/wr 769.1mb/s 1.443ms/op

```

**假如生成的是磁盘文件系统，则需要linux驱动才能挂载**

fuse就不用

## 构建与测试
docker sandbox

https://docs.docker.com/ai/sandboxes/

为ai coding agent系统提供隔离的环境

感觉跟一个container差不多，里面有docker daemon。挂载宿主机工作目录

没有/dev/fuse，用不了