class LiveSession:
    """In-memory broker session; cleared when the application closes."""
    client = None
    stream = None
    broker_id = None

    @classmethod
    def connected(cls):
        return cls.client is not None
