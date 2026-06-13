CFLAGS := -Wall -Wextra -g -O2 -DFUSE_USE_VERSION=31 $(shell pkg-config --cflags fuse3)
LDFLAGS := $(shell pkg-config --libs fuse3)

SOURCES := src/main.c \
           src/fuse_ops.c \
           src/inode_table.c \
           src/dir_ops.c \
           src/storage_backend.c \
           src/path_utils.c \
           src/permissions.c

OBJECTS := $(SOURCES:.c=.o)
DEPS := $(SOURCES:.c=.d)

TARGET := agentfs

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -MMD -MP -c -o $@ $<

-include $(DEPS)

clean:
	rm -f $(OBJECTS) $(DEPS) $(TARGET)

.PHONY: all clean
