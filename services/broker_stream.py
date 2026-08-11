"""Select the live-price stream matching the connected broker."""


def create_broker_stream(broker_id, client, on_tick, on_status):
    if broker_id == "dhan":
        from services.dhan_stream import DhanStream
        return DhanStream(client, on_tick, on_status)
    from services.angel_one_stream import AngelOneStream
    return AngelOneStream(client, on_tick, on_status)
