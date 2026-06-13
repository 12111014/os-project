CC       = gcc
CFLAGS   = -Wall -Wextra -O2 -g $(shell pkg-config fuse3 --cflags)
LDFLAGS  = $(shell pkg-config fuse3 --libs) -lpthread

SRCS     = simplefs.c fuse_ops.c inode_table.c dir_ops.c storage_backend.c path_utils.c
OBJS     = $(SRCS:.c=.o)
TARGET   = agentfs

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)
