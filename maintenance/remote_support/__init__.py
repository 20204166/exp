"""Remote transport/protocol support for ``maintenance.remote``.

The public remote surface lives in ``maintenance.remote``; this package holds
the remote-specific lower layers it composes: the versioned HMAC protocol
envelope (``protocol``), the socket/loopback transports (``transport``), and
the listening socket server (``server``).
"""
