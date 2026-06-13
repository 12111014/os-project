# Build the agentfs binary using Cargo

.PHONY: all clean

all: agentfs

agentfs: target/release/agentfs
	cp target/release/agentfs agentfs

target/release/agentfs: Cargo.toml src/main.rs src/inode.rs src/directory.rs src/filesystem.rs src/path_mod.rs src/permissions_mod.rs src/symlink_mod.rs src/xattr.rs
	cargo build --release

clean:
	cargo clean
	rm -f agentfs
