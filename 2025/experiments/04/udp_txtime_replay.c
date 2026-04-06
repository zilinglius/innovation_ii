#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <linux/net_tstamp.h>
#include <netinet/ether.h>
#include <netinet/ip.h>
#include <netinet/udp.h>
#include <pcap/pcap.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#ifndef SO_TXTIME
#error "This sample requires SO_TXTIME support (Linux 5.4+)."
#endif

struct replay_packet {
  uint64_t rel_ns;
  size_t len;
  uint8_t *payload;
};

struct config {
  const char *pcap_path;
  const char *bind_ip;
  const char *dst_ip;
  uint16_t bind_port;
  uint16_t dst_port;
  uint64_t lead_ns;
  clockid_t clock_id;
};

static void usage(const char *prog) {
  fprintf(stderr,
          "Usage: %s --pcap trace.pcap --bind-ip 10.0.12.1 --bind-port 5000 "
          "--dst-ip 10.0.12.2 --dst-port 5000 [--lead-us 200] "
          "[--clock CLOCK_TAI|CLOCK_MONOTONIC]\n",
          prog);
}

static uint64_t timespec_to_ns(const struct timespec *ts) {
  return (uint64_t)ts->tv_sec * 1000000000ull + (uint64_t)ts->tv_nsec;
}

static struct timespec ns_to_timespec(uint64_t ns) {
  struct timespec ts;
  ts.tv_sec = (time_t)(ns / 1000000000ull);
  ts.tv_nsec = (long)(ns % 1000000000ull);
  return ts;
}

static int parse_clock(const char *name, clockid_t *out) {
  if (strcmp(name, "CLOCK_TAI") == 0) {
    *out = CLOCK_TAI;
    return 0;
  }
  if (strcmp(name, "CLOCK_MONOTONIC") == 0) {
    *out = CLOCK_MONOTONIC;
    return 0;
  }
  if (strcmp(name, "CLOCK_REALTIME") == 0) {
    *out = CLOCK_REALTIME;
    return 0;
  }
  return -1;
}

static void sleep_until(clockid_t clk, uint64_t target_ns, uint64_t guard_ns) {
  while (true) {
    struct timespec now;
    if (clock_gettime(clk, &now) != 0) {
      perror("clock_gettime");
      exit(EXIT_FAILURE);
    }
    uint64_t now_ns = timespec_to_ns(&now);
    if (now_ns + guard_ns >= target_ns) {
      break;
    }
    uint64_t remaining = target_ns - guard_ns - now_ns;
    struct timespec req = ns_to_timespec(remaining);
    clock_nanosleep(clk, 0, &req, NULL);
  }
}

static uint16_t parse_port(const char *s) {
  char *end = NULL;
  long v = strtol(s, &end, 10);
  if (!end || *end != '\0' || v <= 0 || v > 65535) {
    fprintf(stderr, "invalid port: %s\n", s);
    exit(EXIT_FAILURE);
  }
  return (uint16_t)v;
}

static uint64_t parse_lead(const char *s) {
  char *end = NULL;
  long long v = strtoll(s, &end, 10);
  if (!end || *end != '\0' || v < 10) {
    fprintf(stderr, "invalid lead microseconds: %s\n", s);
    exit(EXIT_FAILURE);
  }
  return (uint64_t)v * 1000ull;
}

static void parse_args(int argc, char **argv, struct config *cfg) {
  memset(cfg, 0, sizeof(*cfg));
  cfg->lead_ns = 200000ull;  // default 200 us
  cfg->clock_id = CLOCK_TAI;

  for (int i = 1; i < argc; ++i) {
    const char *arg = argv[i];
    if (strcmp(arg, "--pcap") == 0 && i + 1 < argc) {
      cfg->pcap_path = argv[++i];
    } else if (strcmp(arg, "--bind-ip") == 0 && i + 1 < argc) {
      cfg->bind_ip = argv[++i];
    } else if (strcmp(arg, "--dst-ip") == 0 && i + 1 < argc) {
      cfg->dst_ip = argv[++i];
    } else if (strcmp(arg, "--bind-port") == 0 && i + 1 < argc) {
      cfg->bind_port = parse_port(argv[++i]);
    } else if (strcmp(arg, "--dst-port") == 0 && i + 1 < argc) {
      cfg->dst_port = parse_port(argv[++i]);
    } else if (strcmp(arg, "--lead-us") == 0 && i + 1 < argc) {
      cfg->lead_ns = parse_lead(argv[++i]);
    } else if (strcmp(arg, "--clock") == 0 && i + 1 < argc) {
      if (parse_clock(argv[++i], &cfg->clock_id) != 0) {
        fprintf(stderr, "unsupported clock: %s\n", argv[i]);
        exit(EXIT_FAILURE);
      }
    } else {
      usage(argv[0]);
      exit(EXIT_FAILURE);
    }
  }

  if (!cfg->pcap_path || !cfg->bind_ip || !cfg->dst_ip || cfg->bind_port == 0 ||
      cfg->dst_port == 0) {
    usage(argv[0]);
    exit(EXIT_FAILURE);
  }
}

static void append_packet(struct replay_packet **items, size_t *count,
                          size_t *cap, uint64_t rel_ns, const uint8_t *payload,
                          size_t len) {
  if (len == 0) {
    return;
  }
  if (*count == *cap) {
    size_t new_cap = *cap ? (*cap * 2) : 64;
    struct replay_packet *tmp =
        realloc(*items, new_cap * sizeof(struct replay_packet));
    if (!tmp) {
      perror("realloc");
      exit(EXIT_FAILURE);
    }
    *items = tmp;
    *cap = new_cap;
  }
  uint8_t *buf = malloc(len);
  if (!buf) {
    perror("malloc");
    exit(EXIT_FAILURE);
  }
  memcpy(buf, payload, len);
  (*items)[*count].rel_ns = rel_ns;
  (*items)[*count].len = len;
  (*items)[*count].payload = buf;
  (*count)++;
}

static void free_packets(struct replay_packet *items, size_t count) {
  for (size_t i = 0; i < count; ++i) {
    free(items[i].payload);
  }
  free(items);
}

int main(int argc, char **argv) {
  struct config cfg;
  parse_args(argc, argv, &cfg);

  char errbuf[PCAP_ERRBUF_SIZE];
  pcap_t *pcap = pcap_open_offline(cfg.pcap_path, errbuf);
  if (!pcap) {
    fprintf(stderr, "pcap_open_offline failed: %s\n", errbuf);
    return EXIT_FAILURE;
  }

  struct replay_packet *packets = NULL;
  size_t count = 0;
  size_t cap = 0;

  const uint8_t *data = NULL;
  struct pcap_pkthdr *hdr = NULL;
  double first_ts = -1.0;
  while (true) {
    int ret = pcap_next_ex(pcap, &hdr, &data);
    if (ret == 0) {
      continue;
    }
    if (ret == PCAP_ERROR_BREAK) {
      break;
    }
    if (ret == PCAP_ERROR) {
      fprintf(stderr, "pcap_next_ex error: %s\n", pcap_geterr(pcap));
      free_packets(packets, count);
      pcap_close(pcap);
      return EXIT_FAILURE;
    }
    if (hdr->caplen < sizeof(struct ether_header)) {
      continue;
    }
    const struct ether_header *eth =
        (const struct ether_header *)data;
    if (ntohs(eth->ether_type) != ETHERTYPE_IP) {
      continue;
    }
    size_t offset = sizeof(struct ether_header);
    if (hdr->caplen < offset + sizeof(struct iphdr)) {
      continue;
    }
    const struct iphdr *iph = (const struct iphdr *)(data + offset);
    size_t ip_header_len = (size_t)iph->ihl * 4;
    if (iph->version != 4 || ip_header_len < sizeof(struct iphdr)) {
      continue;
    }
    if (iph->protocol != IPPROTO_UDP) {
      continue;
    }
    offset += ip_header_len;
    if (hdr->caplen < offset + sizeof(struct udphdr)) {
      continue;
    }
    const struct udphdr *udph = (const struct udphdr *)(data + offset);
    uint16_t udp_len = ntohs(udph->len);
    if (udp_len < sizeof(struct udphdr)) {
      continue;
    }
    size_t payload_len = udp_len - sizeof(struct udphdr);
    offset += sizeof(struct udphdr);
    if (hdr->caplen < offset + payload_len) {
      continue;
    }
    const uint8_t *payload = data + offset;

    double abs_ts = hdr->ts.tv_sec + hdr->ts.tv_usec * 1e-6;
    if (first_ts < 0) {
      first_ts = abs_ts;
    }
    double delta = abs_ts - first_ts;
    if (delta < 0) {
      delta = 0;
    }
    uint64_t rel_ns = (uint64_t)(delta * 1e9);
    append_packet(&packets, &count, &cap, rel_ns, payload, payload_len);
  }
  pcap_close(pcap);

  if (count == 0) {
    fprintf(stderr, "no UDP payloads found in %s\n", cfg.pcap_path);
    free_packets(packets, count);
    return EXIT_FAILURE;
  }

  int fd = socket(AF_INET, SOCK_DGRAM, 0);
  if (fd < 0) {
    perror("socket");
    free_packets(packets, count);
    return EXIT_FAILURE;
  }

  struct sockaddr_in local = {
      .sin_family = AF_INET,
      .sin_port = htons(cfg.bind_port),
  };
  if (inet_pton(AF_INET, cfg.bind_ip, &local.sin_addr) != 1) {
    fprintf(stderr, "invalid bind ip %s\n", cfg.bind_ip);
    free_packets(packets, count);
    close(fd);
    return EXIT_FAILURE;
  }
  if (bind(fd, (struct sockaddr *)&local, sizeof(local)) != 0) {
    perror("bind");
    free_packets(packets, count);
    close(fd);
    return EXIT_FAILURE;
  }

  struct sock_txtime txtime_cfg = {
      .clockid = cfg.clock_id,
      .flags = SOF_TXTIME_REPORT_ERRORS,
  };
  if (setsockopt(fd, SOL_SOCKET, SO_TXTIME, &txtime_cfg,
                 sizeof(txtime_cfg)) != 0) {
    perror("setsockopt(SO_TXTIME)");
    free_packets(packets, count);
    close(fd);
    return EXIT_FAILURE;
  }

  struct sockaddr_in remote = {
      .sin_family = AF_INET,
      .sin_port = htons(cfg.dst_port),
  };
  if (inet_pton(AF_INET, cfg.dst_ip, &remote.sin_addr) != 1) {
    fprintf(stderr, "invalid dst ip %s\n", cfg.dst_ip);
    free_packets(packets, count);
    close(fd);
    return EXIT_FAILURE;
  }

  struct timespec now;
  if (clock_gettime(cfg.clock_id, &now) != 0) {
    perror("clock_gettime");
    free_packets(packets, count);
    close(fd);
    return EXIT_FAILURE;
  }
  uint64_t base_ns = timespec_to_ns(&now) + cfg.lead_ns;
  uint64_t guard_ns = cfg.lead_ns / 2;

  printf("[*] Replaying %zu packets using %s lead=%lu us\n", count,
         (cfg.clock_id == CLOCK_TAI
              ? "CLOCK_TAI"
              : (cfg.clock_id == CLOCK_MONOTONIC ? "CLOCK_MONOTONIC"
                                                 : "CLOCK_REALTIME")),
         (unsigned long)(cfg.lead_ns / 1000ull));

  for (size_t i = 0; i < count; ++i) {
    uint64_t target_ns = base_ns + packets[i].rel_ns;
    sleep_until(cfg.clock_id, target_ns, guard_ns);

    struct iovec iov = {
        .iov_base = packets[i].payload,
        .iov_len = packets[i].len,
    };
    char cbuf[CMSG_SPACE(sizeof(uint64_t))];
    memset(cbuf, 0, sizeof(cbuf));
    struct msghdr msg = {
        .msg_name = &remote,
        .msg_namelen = sizeof(remote),
        .msg_iov = &iov,
        .msg_iovlen = 1,
        .msg_control = cbuf,
        .msg_controllen = sizeof(cbuf),
    };
    struct cmsghdr *cm = CMSG_FIRSTHDR(&msg);
    cm->cmsg_level = SOL_SOCKET;
    cm->cmsg_type = SCM_TXTIME;
    cm->cmsg_len = CMSG_LEN(sizeof(uint64_t));
    memcpy(CMSG_DATA(cm), &target_ns, sizeof(target_ns));

    if (sendmsg(fd, &msg, 0) < 0) {
      perror("sendmsg");
      free_packets(packets, count);
      close(fd);
      return EXIT_FAILURE;
    }
  }

  free_packets(packets, count);
  close(fd);
  return EXIT_SUCCESS;
}
