#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <linux/net_tstamp.h>
#include <netinet/in.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

struct rx_config {
  const char *bind_ip;
  uint16_t port;
  size_t max_samples;
};

static void rx_usage(const char *prog) {
  fprintf(stderr,
          "Usage: %s --bind-ip 10.0.3.11 --port 5000 [--count 1000]\n"
          "CSV is written to stdout; redirect to capture.\n",
          prog);
}

static uint16_t rx_parse_port(const char *s) {
  char *end = NULL;
  long v = strtol(s, &end, 10);
  if (!end || *end != '\0' || v <= 0 || v > 65535) {
    fprintf(stderr, "invalid port: %s\n", s);
    exit(EXIT_FAILURE);
  }
  return (uint16_t)v;
}

static size_t rx_parse_count(const char *s) {
  char *end = NULL;
  long v = strtol(s, &end, 10);
  if (!end || *end != '\0' || v < 0) {
    fprintf(stderr, "invalid count: %s\n", s);
    exit(EXIT_FAILURE);
  }
  return (size_t)v;
}

static void rx_parse_args(int argc, char **argv, struct rx_config *cfg) {
  memset(cfg, 0, sizeof(*cfg));
  for (int i = 1; i < argc; ++i) {
    const char *arg = argv[i];
    if (strcmp(arg, "--bind-ip") == 0 && i + 1 < argc) {
      cfg->bind_ip = argv[++i];
    } else if (strcmp(arg, "--port") == 0 && i + 1 < argc) {
      cfg->port = rx_parse_port(argv[++i]);
    } else if (strcmp(arg, "--count") == 0 && i + 1 < argc) {
      cfg->max_samples = rx_parse_count(argv[++i]);
    } else {
      rx_usage(argv[0]);
      exit(EXIT_FAILURE);
    }
  }
  if (!cfg->bind_ip || cfg->port == 0) {
    rx_usage(argv[0]);
    exit(EXIT_FAILURE);
  }
}

static uint64_t ts_to_ns(const struct timespec *ts) {
  return (uint64_t)ts->tv_sec * 1000000000ull + (uint64_t)ts->tv_nsec;
}

int main(int argc, char **argv) {
  struct rx_config cfg;
  rx_parse_args(argc, argv, &cfg);

  int fd = socket(AF_INET, SOCK_DGRAM, 0);
  if (fd < 0) {
    perror("socket");
    return EXIT_FAILURE;
  }

  int ts_flags = SOF_TIMESTAMPING_RX_SOFTWARE | SOF_TIMESTAMPING_SOFTWARE |
                 SOF_TIMESTAMPING_SYS_HARDWARE | SOF_TIMESTAMPING_RAW_HARDWARE;
  if (setsockopt(fd, SOL_SOCKET, SO_TIMESTAMPING, &ts_flags,
                 sizeof(ts_flags)) != 0) {
    perror("setsockopt(SO_TIMESTAMPING)");
    close(fd);
    return EXIT_FAILURE;
  }

  int enable = 1;
  setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &enable, sizeof(enable));

  struct sockaddr_in addr = {
      .sin_family = AF_INET,
      .sin_port = htons(cfg.port),
  };
  if (inet_pton(AF_INET, cfg.bind_ip, &addr.sin_addr) != 1) {
    fprintf(stderr, "invalid bind ip %s\n", cfg.bind_ip);
    close(fd);
    return EXIT_FAILURE;
  }
  if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
    perror("bind");
    close(fd);
    return EXIT_FAILURE;
  }

  printf("seq,wire_len,payload_len,kernel_realtime_ns,mono_raw_ns\n");
  fflush(stdout);

  size_t seq = 0;
  while (cfg.max_samples == 0 || seq < cfg.max_samples) {
    uint8_t buf[2048];
    struct iovec iov = {
        .iov_base = buf,
        .iov_len = sizeof(buf),
    };
    char cbuf[512];
    struct msghdr msg = {
        .msg_iov = &iov,
        .msg_iovlen = 1,
        .msg_control = cbuf,
        .msg_controllen = sizeof(cbuf),
    };
    ssize_t n = recvmsg(fd, &msg, 0);
    if (n < 0) {
      if (errno == EINTR) {
        continue;
      }
      perror("recvmsg");
      close(fd);
      return EXIT_FAILURE;
    }

    struct timespec stamp[3];
    memset(stamp, 0, sizeof(stamp));
    for (struct cmsghdr *cm = CMSG_FIRSTHDR(&msg); cm;
         cm = CMSG_NXTHDR(&msg, cm)) {
      if (cm->cmsg_level == SOL_SOCKET &&
          cm->cmsg_type == SO_TIMESTAMPING &&
          cm->cmsg_len >= CMSG_LEN(sizeof(stamp))) {
        memcpy(&stamp, CMSG_DATA(cm), sizeof(stamp));
        break;
      }
    }
    struct timespec mono_now;
    clock_gettime(CLOCK_MONOTONIC_RAW, &mono_now);
    uint64_t realtime_ns = ts_to_ns(&stamp[2]);
    uint64_t mono_ns = ts_to_ns(&mono_now);
    size_t payload_len = (size_t)n;
    size_t wire_len = payload_len + 42;  // rough Ethernet/IP/UDP header estimate

    printf("%zu,%zu,%zu,%llu,%llu\n", seq, wire_len, payload_len,
           (unsigned long long)realtime_ns,
           (unsigned long long)mono_ns);
    fflush(stdout);
    seq++;
  }

  close(fd);
  return EXIT_SUCCESS;
}
