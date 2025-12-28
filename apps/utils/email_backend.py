import socket
from django.core.mail.backends.smtp import EmailBackend

class ForceIPv4EmailBackend(EmailBackend):
    """
    Custom EmailBackend that forces IPv4 connection.
    Fixes [Errno 101] Network is unreachable on servers with broken IPv6 (e.g. Railway).
    """
    def open(self):
        # Store original getaddrinfo
        original_getaddrinfo = socket.getaddrinfo
        
        def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            # Force AF_INET (IPv4)
            return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
            
        try:
            # Patch socket.getaddrinfo for the duration of the connection attempt
            socket.getaddrinfo = ipv4_getaddrinfo
            return super().open()
        finally:
            # Restore original getaddrinfo
            socket.getaddrinfo = original_getaddrinfo
