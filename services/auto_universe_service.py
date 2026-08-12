"""Rate-conscious automatic discovery of liquid NSE F&O stocks."""

from __future__ import annotations

from time import sleep

from core.auto_universe_store import AutoUniverseStore
from engine.auto_universe_engine import rank_fno_universe
from services.option_contract_service import OptionContractService


class AutoUniverseService:
    BATCH_SIZE = 40
    REFRESH_MINUTES = 15
    SELECTION_LIMIT = 5

    def __init__(self, client, contract_service=None, store=None):
        self.client = client
        self.contract_service = contract_service or OptionContractService()
        self.store = store or AutoUniverseStore()

    def discover(self, force: bool = False) -> list[dict]:
        cached = [] if force else self.store.load(self.REFRESH_MINUTES)
        if cached:
            return cached
        universe = self.contract_service.get_stock_option_universe()
        quotes = []
        for start in range(0, len(universe), self.BATCH_SIZE):
            batch = universe[start:start + self.BATCH_SIZE]
            quotes.extend(self.client.get_market_quotes({"NSE": [str(row["token"]) for row in batch]}))
            if start + self.BATCH_SIZE < len(universe):
                sleep(1.05)
        selected = rank_fno_universe(universe, quotes, self.SELECTION_LIMIT)
        if not selected:
            raise RuntimeError("Live F&O universe scan returned no liquid stock candidates.")
        self.store.save(selected)
        return selected
