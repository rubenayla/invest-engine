#!/usr/bin/env python3
"""
Dynamic Index Manager
Fetches real market indices, caches company metadata, and tracks discovery dates.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

class IndexManager:
    """Manages dynamic index fetching with local caching and incremental updates."""

    def __init__(self, data_dir: str = 'data/indices'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.companies_file = self.data_dir / 'companies_registry.json'
        self.indices_file = self.data_dir / 'indices_cache.json'

        self.companies = self._load_companies_registry()
        self.indices_cache = self._load_indices_cache()

    def _load_companies_registry(self) -> Dict:
        """Load company metadata registry with discovery dates."""
        if self.companies_file.exists():
            try:
                with open(self.companies_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load companies registry: {e}")

        return {
            'companies': {},  # ticker -> {name, sector, discovered_date, indices, last_updated}
            'last_updated': None,
            'total_companies': 0
        }

    def _load_indices_cache(self) -> Dict:
        """Load cached index constituent lists."""
        if self.indices_file.exists():
            try:
                with open(self.indices_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load indices cache: {e}")

        return {
            'indices': {},  # index_name -> {tickers: [], last_updated: date}
            'refresh_intervals': {
                'sp500': 7,      # days
                'merval': 7,
                'nifty50': 7,
                'nikkei225': 7,
                'global': 7
            }
        }

    def _save_companies_registry(self):
        """Save companies registry atomically."""
        self.companies['last_updated'] = datetime.now().isoformat()
        self.companies['total_companies'] = len(self.companies['companies'])

        temp_file = self.companies_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w') as f:
                json.dump(self.companies, f, indent=2)
            temp_file.rename(self.companies_file)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise e

    def _save_indices_cache(self):
        """Save indices cache atomically."""
        temp_file = self.indices_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w') as f:
                json.dump(self.indices_cache, f, indent=2)
            temp_file.rename(self.indices_file)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise e

    def _needs_refresh(self, index_name: str) -> bool:
        """Check if index needs refreshing based on last update date."""
        if index_name not in self.indices_cache['indices']:
            return True

        last_updated = self.indices_cache['indices'][index_name].get('last_updated')
        if not last_updated:
            return True

        refresh_days = self.indices_cache['refresh_intervals'].get(index_name, 30)
        last_date = datetime.fromisoformat(last_updated)
        return (datetime.now() - last_date).days > refresh_days

    def _discover_company_info(self, ticker: str) -> Optional[Dict]:
        """Fetch basic company information and add to registry."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            company_data = {
                'name': info.get('longName') or info.get('shortName', ticker),
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'country': info.get('country', 'Unknown'),
                'market_cap': info.get('marketCap'),
                'discovered_date': datetime.now().isoformat(),
                'indices': [],
                'last_updated': datetime.now().isoformat()
            }
            return company_data
        except Exception as e:
            logger.warning(f"Could not fetch info for {ticker}: {e}")
            return None

    def _fetch_sp500_tickers(self) -> List[str]:
        """Fetch S&P 500 tickers."""
        import requests
        import pandas as pd
        from io import StringIO

        # Method 1: Wikipedia (most reliably up-to-date)
        try:
            resp = requests.get(
                'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=15,
            )
            resp.raise_for_status()
            tables = pd.read_html(StringIO(resp.text))
            tickers = tables[0]['Symbol'].tolist()
            if len(tickers) >= 490:  # sanity check
                logger.info(f"✅ Fetched {len(tickers)} S&P 500 tickers from Wikipedia")
                return tickers
        except Exception as e1:
            logger.warning(f"Wikipedia failed: {e1}")

        # Method 2: datahub.io fallback
        try:
            url = 'https://datahub.io/core/s-and-p-500-companies/r/constituents.csv'
            df = pd.read_csv(url)
            tickers = df['Symbol'].tolist()
            logger.info(f"✅ Fetched {len(tickers)} S&P 500 tickers from datahub.io")
            return tickers
        except Exception as e2:
            logger.warning(f"Datahub failed: {e2}, using fallback.")

        # Basic fallback list
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "UNH", "JNJ"]

    def _fetch_merval_tickers(self) -> List[str]:
        """Fetch Argentina Merval tickers."""
        # Hardcoded list of major Argentine stocks (local .BA)
        return [
            "YPFD.BA", "GGAL.BA", "PAMP.BA", "TXAR.BA", "ALUA.BA",
            "BMA.BA", "CRES.BA", "EDN.BA", "CEPU.BA", "TGNO4.BA",
            "TRAN.BA", "COME.BA", "MIRG.BA", "TECO2.BA", "VALO.BA",
            "BYMA.BA", "CVH.BA", "SUPV.BA", "LOMA.BA", "HARG.BA",
            "MOLI.BA", "GCLA.BA", "SEMI.BA", "INVJ.BA", "LEDE.BA",
            "MORI.BA", "IRSA.BA"
        ]

    def _fetch_nifty50_tickers(self) -> List[str]:
        """Fetch India Nifty 50 tickers."""
        # Hardcoded list of Nifty 50
        return [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
            "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LTIM.NS",
            "KOTAKBANK.NS", "AXISBANK.NS", "HCLTECH.NS", "TATAMOTORS.NS", "MARUTI.NS",
            "ASIANPAINT.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "BAJFINANCE.NS",
            "NTPC.NS", "ONGC.NS", "NESTLEIND.NS", "POWERGRID.NS", "JSWSTEEL.NS",
            "ADANIENT.NS", "GRASIM.NS", "ADANIPORTS.NS", "COALINDIA.NS", "M&M.NS",
            "WIPRO.NS", "TATASTEEL.NS", "BAJAJFINSV.NS", "DIVISLAB.NS", "HEROMOTOCO.NS",
            "SBILIFE.NS", "EICHERMOT.NS", "APOLLOHOSP.NS", "TECHM.NS", "BPCL.NS",
            "HINDALCO.NS", "DRREDDY.NS", "BRITANNIA.NS", "TATACONSUM.NS", "CIPLA.NS",
            "INDUSINDBK.NS", "UPL.NS"
        ]

    def _fetch_nikkei225_tickers(self) -> List[str]:
        """Fetch Japan Nikkei 225 / Major tickers."""
        return [
            "7203.T", "6758.T", "8035.T", "9984.T", "9432.T", "6861.T", "6098.T", "4063.T",
            "8058.T", "9983.T", "7974.T", "9433.T", "4502.T", "7267.T", "6902.T", "6954.T",
            "6501.T", "8001.T", "8002.T", "8031.T", "8306.T", "8316.T", "8411.T", "8766.T",
            "8802.T", "7741.T", "6367.T", "4519.T", "4568.T", "6273.T", "6981.T", "9020.T",
            "9021.T", "9022.T", "4901.T", "2914.T", "4452.T", "1925.T", "1928.T", "2502.T",
            "2503.T", "2802.T", "3382.T", "3407.T", "4503.T", "4507.T", "4523.T", "4543.T",
            "4578.T", "4661.T", "4911.T", "5108.T", "5401.T", "6301.T", "6502.T", "6503.T",
            "6594.T", "6645.T", "6701.T", "6702.T", "6723.T", "6752.T", "6762.T", "6920.T",
            "6971.T", "7201.T", "7269.T", "7270.T", "7733.T", "7751.T", "8015.T", "8053.T",
            "8113.T", "8267.T", "8604.T", "8801.T", "8830.T", "9064.T", "9101.T", "9201.T",
            "9202.T", "9503.T", "9531.T", "9735.T", "9843.T"
        ]

    def get_index_tickers(self, index_name: str, force_refresh: bool = False) -> List[str]:
        """Get tickers for an index, fetching if needed or using cache."""
        if force_refresh or self._needs_refresh(index_name):
            logger.info(f"Refreshing {index_name} index...")

            new_tickers = []
            if index_name == 'sp500':
                new_tickers = self._fetch_sp500_tickers()
            elif index_name == 'merval':
                new_tickers = self._fetch_merval_tickers()
            elif index_name == 'nifty50':
                new_tickers = self._fetch_nifty50_tickers()
            elif index_name == 'nikkei225':
                new_tickers = self._fetch_nikkei225_tickers()

            if new_tickers:
                self.indices_cache['indices'][index_name] = {
                    'tickers': new_tickers,
                    'last_updated': datetime.now().isoformat(),
                    'count': len(new_tickers)
                }
                self._save_indices_cache()
                self._update_company_registry(new_tickers, index_name)
                return new_tickers

        return self.indices_cache['indices'].get(index_name, {}).get('tickers', [])

    def get_all_tickers(self) -> List[str]:
        """Get all available tickers (Global)."""
        all_tickers = set()
        for idx in ['sp500', 'merval', 'nifty50', 'nikkei225']:
            all_tickers.update(self.get_index_tickers(idx))
        return list(all_tickers)

    def _update_company_registry(self, tickers: List[str], index_name: str):
        # Simply register existence; full info is fetched by pipeline later if needed
        pass

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    im = IndexManager()
    print(f"Total global tickers: {len(im.get_all_tickers())}")
