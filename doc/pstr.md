下面给你一套**在 Agent 的 Docker sandbox 容器里评测 `passthrough_ll`** 的完整流程。目标是得到一个可复现的 FUSE baseline：

```text
native lowerdir，例如 tmpfs/ext4
  vs
libfuse passthrough_ll 挂载后的目录
  vs
agent 生成的 FUSE FS
```

`passthrough_ll` 是 libfuse 官方 low-level API 示例，用来把 FUSE 请求转发到底层目录；libfuse 本身是 Linux FUSE 用户态库的参考实现。([GitHub](https://github.com/libfuse/libfuse?utm_source=chatgpt.com "libfuse/libfuse: The reference implementation of the Linux ..."))

---

## 1. Sandbox 镜像准备

你的 sandbox Dockerfile 里至少要有这些依赖：

```dockerfile
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential gcc g++ \
    git pkg-config \
    meson ninja-build cmake make \
    fuse3 libfuse3-dev \
    fio filebench \
    strace lsof psmisc procps sysstat \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /workspace /mnt/passthrough /mnt/native /lower /workspace/logs

WORKDIR /workspace

CMD ["sleep", "infinity"]
```

构建：

```bash
docker build -t fs-agent-sandbox:latest -f sandbox/Dockerfile .
```

---

## 2. 启动支持 FUSE 的 sandbox 容器

FUSE 容器需要能访问 `/dev/fuse`，并且需要挂载相关能力。Docker 文档中也给过这类运行方式：`--cap-add SYS_ADMIN` 配合 `--device /dev/fuse`。([Docker Documentation](https://docs.docker.com/engine/containers/run/?utm_source=chatgpt.com "Running containers"))

```bash
RUN_ID=001
mkdir -p runs/$RUN_ID

docker run -d \
  --name fs-agent-run-$RUN_ID \
  --device /dev/fuse \
  --cap-add SYS_ADMIN \
  --security-opt apparmor=unconfined \
  --security-opt seccomp=unconfined \
  --mount type=bind,src="$PWD/runs/$RUN_ID",dst=/workspace \
  fs-agent-sandbox:latest
```

进入容器：

```bash
docker exec -it fs-agent-run-$RUN_ID bash
```

检查 FUSE：

```bash
ls -l /dev/fuse
fusermount3 --version
```

如果 `/dev/fuse` 不存在，先在宿主机确认：

```bash
ls -l /dev/fuse
sudo modprobe fuse
```

---

## 3. 编译 `passthrough_ll`

### 方法 A：直接编译发行版 libfuse 示例

在容器里：

```bash
cd /workspace
git clone https://github.com/libfuse/libfuse.git
cd libfuse/example

gcc -Wall passthrough_ll.c \
  $(pkg-config fuse3 --cflags --libs) \
  -o /workspace/passthrough_ll
```

如果能成功，检查：

```bash
/workspace/passthrough_ll --help
```

### 方法 B：用 meson 编译整个 libfuse

如果方法 A 因源码和系统 libfuse 版本不匹配失败，就在容器里完整构建：

```bash
cd /workspace
git clone https://github.com/libfuse/libfuse.git
cd libfuse

meson setup build
ninja -C build
```

查找可执行文件：

```bash
find build -name 'passthrough_ll*' -type f -executable
```

假设找到：

```text
/workspace/libfuse/build/example/passthrough_ll
```

后续命令把 `/workspace/passthrough_ll` 替换成这个路径即可。

---

## 4. 准备 lowerdir 和 mountpoint

建议先用 **tmpfs lowerdir**，这样主要测 FUSE 路径开销，而不是虚拟磁盘 I/O。

在容器内：

```bash
mkdir -p /lower /mnt/passthrough /mnt/native /workspace/logs
mount -t tmpfs -o size=4G tmpfs /lower
```

准备一些初始文件：

```bash
echo hello > /lower/a.txt
mkdir -p /lower/dir
echo world > /lower/dir/b.txt
```

这时 `/lower` 是 native baseline。

---

## 5. 挂载 `passthrough_ll`

### 默认/auto cache 模式

```bash
/workspace/passthrough_ll \
  -o source=/lower,cache=auto \
  /mnt/passthrough
```

验证：

```bash
mountpoint /mnt/passthrough
ls -la /mnt/passthrough
cat /mnt/passthrough/a.txt
```

### 前台调试模式

如果你想看日志：

```bash
/workspace/passthrough_ll \
  -f \
  -o source=/lower,cache=auto \
  /mnt/passthrough
```

### 后台方式，适合 Agent/SandboxManager

```bash
nohup /workspace/passthrough_ll \
  -f \
  -o source=/lower,cache=auto \
  /mnt/passthrough \
  > /workspace/logs/passthrough_ll.log 2>&1 &

echo $! > /workspace/logs/passthrough_ll.pid

sleep 1
mountpoint /mnt/passthrough
```

`passthrough_ll` 支持 `source=...`、`cache=never/auto/always`、`writeback/no_writeback` 等选项，可用来分别测试不同 FUSE 缓存模式。([GitHub](https://github.com/libfuse/libfuse/blob/master/example/passthrough_ll.c?utm_source=chatgpt.com "libfuse/example/passthrough_ll.c at master")) Linux FUSE I/O 文档也说明 FUSE 有 direct-io、cached write-through、writeback-cache 等模式，这些模式会显著影响读写路径和性能。([Linux Kernel Archives](https://www.kernel.org/doc/Documentation/filesystems/fuse-io.txt?utm_source=chatgpt.com "writeback-cache mode"))

---

## 6. 跑 Filebench

### 6.1 先跑 native tmpfs baseline

创建一个小一点的 workload，避免 Filebench 默认参数太重：

```bash
cat > /workspace/fileserver-native.f <<'EOF'
set $dir=/lower
set $nfiles=1000
set $meandirwidth=20
set $meanfilesize=16k
set $nthreads=4
set $iosize=4k

define fileset name=bigfileset,path=$dir,size=$meanfilesize,entries=$nfiles,dirwidth=$meandirwidth,prealloc=100

define process name=filereader,instances=1
{
  thread name=filereaderthread,instances=$nthreads
  {
    flowop openfile name=openfile1,filesetname=bigfileset,fd=1
    flowop readwholefile name=readfile1,fd=1,iosize=$iosize
    flowop closefile name=closefile1,fd=1
  }
}

run 30
EOF
```

运行：

```bash
sync
echo 3 > /proc/sys/vm/drop_caches

filebench -f /workspace/fileserver-native.f \
  | tee /workspace/logs/filebench-native.log
```

### 6.2 再跑 passthrough_ll

```bash
sed 's#set $dir=/lower#set $dir=/mnt/passthrough#' \
  /workspace/fileserver-native.f \
  > /workspace/fileserver-passthrough.f
```

运行：

```bash
sync
echo 3 > /proc/sys/vm/drop_caches

filebench -f /workspace/fileserver-passthrough.f \
  | tee /workspace/logs/filebench-passthrough.log
```

### 6.3 跑 agent 生成 FS

假设 agent FS 挂在：

```text
/mnt/agentfs
```

```bash
sed 's#set $dir=/lower#set $dir=/mnt/agentfs#' \
  /workspace/fileserver-native.f \
  > /workspace/fileserver-agentfs.f

sync
echo 3 > /proc/sys/vm/drop_caches

filebench -f /workspace/fileserver-agentfs.f \
  | tee /workspace/logs/filebench-agentfs.log
```

---

## 7. 跑 fio，补充微基准

Filebench 偏应用级混合负载，fio 更适合看顺序/随机 I/O。

创建 fio job：

```bash
cat > /workspace/randread.fio <<'EOF'
[global]
ioengine=sync
time_based=1
runtime=30
size=512M
bs=4k
numjobs=4
group_reporting=1

[randread]
rw=randread
directory=/mnt/passthrough
filename=fio-test-file
EOF
```

跑 passthrough：

```bash
fio /workspace/randread.fio | tee /workspace/logs/fio-passthrough-randread.log
```

跑 native：

```bash
sed 's#directory=/mnt/passthrough#directory=/lower#' \
  /workspace/randread.fio > /workspace/randread-native.fio

fio /workspace/randread-native.fio \
  | tee /workspace/logs/fio-native-randread.log
```

跑 agent FS：

```bash
sed 's#directory=/mnt/passthrough#directory=/mnt/agentfs#' \
  /workspace/randread.fio > /workspace/randread-agentfs.fio

fio /workspace/randread-agentfs.fio \
  | tee /workspace/logs/fio-agentfs-randread.log
```

---

## 8. 测不同 passthrough_ll 缓存模式

建议至少跑三组：

### cache=never

```bash
fusermount3 -u /mnt/passthrough || true

nohup /workspace/passthrough_ll \
  -f \
  -o source=/lower,cache=never \
  /mnt/passthrough \
  > /workspace/logs/passthrough-cache-never.log 2>&1 &

echo $! > /workspace/logs/passthrough.pid
sleep 1
mountpoint /mnt/passthrough
```

### cache=auto

```bash
fusermount3 -u /mnt/passthrough || true

nohup /workspace/passthrough_ll \
  -f \
  -o source=/lower,cache=auto \
  /mnt/passthrough \
  > /workspace/logs/passthrough-cache-auto.log 2>&1 &

echo $! > /workspace/logs/passthrough.pid
sleep 1
mountpoint /mnt/passthrough
```

### writeback + cache=always

```bash
fusermount3 -u /mnt/passthrough || true

nohup /workspace/passthrough_ll \
  -f \
  -o source=/lower,writeback,cache=always \
  /mnt/passthrough \
  > /workspace/logs/passthrough-writeback.log 2>&1 &

echo $! > /workspace/logs/passthrough.pid
sleep 1
mountpoint /mnt/passthrough
```

对 agent 生成 FS 做性能比较时，最好也把它的缓存模式记录清楚，否则结果很难解释。

---

## 9. 清理挂载

在容器内：

```bash
set +e

if mountpoint -q /mnt/passthrough; then
  fusermount3 -u /mnt/passthrough || umount -l /mnt/passthrough
fi

if [ -f /workspace/logs/passthrough.pid ]; then
  kill "$(cat /workspace/logs/passthrough.pid)" 2>/dev/null || true
fi
```

清理 lower tmpfs：

```bash
umount /lower || true
```

退出容器后销毁：

```bash
docker rm -f fs-agent-run-$RUN_ID
```

---

## 10. 给 SandboxManager 用的封装命令

你可以把上面的流程封装成几个工具。

### mount_passthrough_ll

```bash
mkdir -p /lower /mnt/passthrough /workspace/logs /workspace/run

mountpoint -q /lower || mount -t tmpfs -o size=4G tmpfs /lower

nohup /workspace/passthrough_ll \
  -f \
  -o source=/lower,cache=auto \
  /mnt/passthrough \
  > /workspace/logs/passthrough_ll.log 2>&1 &

echo $! > /workspace/run/passthrough_ll.pid

sleep 1
mountpoint -q /mnt/passthrough
```

### run_filebench_passthrough

```bash
filebench -f /workspace/fileserver-passthrough.f \
  > /workspace/logs/filebench-passthrough.log 2>&1
```

### cleanup_passthrough_ll

```bash
set +e

if mountpoint -q /mnt/passthrough; then
  fusermount3 -u /mnt/passthrough || umount -l /mnt/passthrough
fi

if [ -f /workspace/run/passthrough_ll.pid ]; then
  kill "$(cat /workspace/run/passthrough_ll.pid)" 2>/dev/null || true
fi
```

---

## 11. 常见问题排查

### `/dev/fuse: Operation not permitted`

通常是容器启动参数不够。确认启动时有：

```bash
--device /dev/fuse
--cap-add SYS_ADMIN
--security-opt apparmor=unconfined
```

### `fusermount3: failed to open /dev/fuse`

宿主机可能没有加载 FUSE：

```bash
sudo modprobe fuse
ls -l /dev/fuse
```

然后重启容器。

### `mountpoint /mnt/passthrough` 失败

看日志：

```bash
cat /workspace/logs/passthrough_ll.log
```

确认 lowerdir 存在：

```bash
ls -la /lower
```

### Filebench 卡住

先在 `/lower` 跑 native，再在 `/mnt/passthrough` 跑。如果 native 正常、passthrough 卡住，用：

```bash
strace -ff -tt -T -o /workspace/logs/fb.strace \
  filebench -f /workspace/fileserver-passthrough.f
```

再检查 FUSE waiting：

```bash
mount -t fusectl none /sys/fs/fuse/connections 2>/dev/null || true

for d in /sys/fs/fuse/connections/*; do
  echo "$d waiting=$(cat "$d/waiting" 2>/dev/null)"
done
```

`waiting` 非零且没有测试进展，通常说明 FUSE daemon 卡住或有请求未返回。

---

## 12. 推荐最终对比表

在同一个 sandbox 里跑完后，报告按这种方式组织：

```text
Environment:
- container image: fs-agent-sandbox:latest
- lowerdir: tmpfs, size=4G
- FUSE baseline: passthrough_ll
- cache mode: cache=auto / cache=never / writeback

Filebench fileserver:
- native /lower:              X ops/s
- passthrough_ll:             Y ops/s
- agent FUSE FS:              Z ops/s

Normalized:
- native:                     100%
- passthrough_ll/native:      Y/X
- agent/passthrough_ll:       Z/Y
- agent/native:               Z/X
```

最关键的解释是：

```text
native → passthrough_ll：FUSE 框架开销
passthrough_ll → agent FS：agent 生成实现的额外开销
```