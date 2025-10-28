"""
Timer defaults for the teaching-oriented OSPF implementation.

The values intentionally keep the protocol responsive while avoiding excessive
spamming when running multiple instances on a laptop.  They can be tuned from
the topology file's defaults to emulate larger deployments.
"""

HELLO_INTERVAL = 5
DEAD_INTERVAL = 20
LS_REFRESH_TIME = 30 * 60  # seconds
SPF_INITIAL_DELAY = 0.2
SPF_HOLD_TIME = 2.0
NEIGHBOR_TICK = 1.0
